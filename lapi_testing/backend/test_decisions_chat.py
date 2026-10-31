"""Where Lapi uses the OpenAI Decisions API: answer support checks in both chats, the
Dashboard chat's knowledge routing and the set-up chat's fixed choices. Without a Decisions
Default each keeps its previous behaviour, and the recorded status says what actually ran."""
import json

import pytest
from lapi_app import agent_model, setup_assist
from lapi_app.lapi_models import decisions
from test_dataset_models import system, post
from test_workspace_knowledge_chat import setup, body
from test_user_management import accounts, login
from test_chat_agent import prepared, activate
from test_agent_workspace import plan

SNAP = {'settings': {}, 'secret_refs': {}, 'provider_model': 'gpt-6-luna', 'capability': 'decisions'}


def use_decisions(monkeypatch, judge):
    """A Decisions Default whose answers come from `judge(question, evidence)`; records each request."""
    asked = []
    monkeypatch.setattr(decisions, 'snapshot', lambda: SNAP)
    def ask(snap, evidence, questions, cfg=None):
        asked.append((evidence, questions))
        return [dict(judge(q, evidence), name=q['name']) for q in questions]
    monkeypatch.setattr(decisions, 'ask', ask)
    return asked


def supported_when(word):
    return lambda q, e: {'type': 'predicate', 'probability': 0.95 if word in q['instructions'] else 0.1}


def steps(message):
    return [step['label'] for step in message['answer_workflow']['steps']]


# ------------------------------------------------------------- answer support

def test_dashboard_answer_is_checked_sentence_by_sentence_and_passes(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch)
    asked = use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.92})
    monkeypatch.setattr(agent_model, 'complete', lambda m, t, **k: {'text': 'Invoices are stored. [1] Policies are stored too. [2]', 'calls': []})
    message = post(s, '/api/dataset-chat/messages', body(a, b, summary=True))['message']
    support = message['tool_trace'][0]['result']['answer_support']
    assert support['status'] == 'passed' and support['checked'] == 2 and support['model'] == 'gpt-6-luna'
    evidence, questions = asked[-1]
    assert [q['type'] for q in questions] == ['predicate', 'predicate']
    assert '"Invoices are stored."' in questions[0]['instructions'] and '[1]' in questions[0]['instructions']
    assert '"sources"' in evidence[0]['content'][1]['text']  # the cited evidence travels as data
    assert 'Checking the sources support the answer' in steps(message)


def test_dashboard_unsupported_sentence_is_repaired_from_the_same_evidence(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch); drafts = []
    use_decisions(monkeypatch, supported_when('stored'))
    def answer(messages, tools, **kw):
        drafts.append(messages[-1]['content'])
        text = 'Invoices total 9 million dollars. [1]' if len(drafts) == 1 else 'Invoices are stored. [1]'
        return {'text': text, 'calls': []}
    monkeypatch.setattr(agent_model, 'complete', answer)
    message = post(s, '/api/dataset-chat/messages', body(a, b, summary=True))['message']
    assert message['text'] == 'Invoices are stored. [1]'
    assert 'not supported by the sources they cite' in drafts[1] and '9 million' in drafts[1]
    assert message['tool_trace'][0]['result']['answer_support']['status'] == 'passed'


def test_dashboard_answer_unsupported_twice_is_not_shown(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch)
    use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.05})
    monkeypatch.setattr(agent_model, 'complete', lambda m, t, **k: {'text': 'Invented fact. [1]', 'calls': []})
    response = s.api.post('/api/dataset-chat/messages', json=body(a, b, summary=True))
    assert response.status_code == 502 and 'cited sources do not support' in response.json()['detail']


def test_without_a_decisions_default_nothing_claims_a_support_check(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch)
    monkeypatch.setattr(decisions, 'ask', lambda *x, **y: pytest.fail('No Decisions Default, so no Decisions request.'))
    message = post(s, '/api/dataset-chat/messages', body(a, b, summary=True))['message']
    assert message['tool_trace'][0]['result']['answer_support'] == {'status': 'not_configured'}
    assert 'Checking the sources support the answer' not in steps(message)


def test_a_failed_decisions_request_is_reported_as_unavailable_not_passed(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch)
    monkeypatch.setattr(decisions, 'snapshot', lambda: SNAP)
    def broken(*args, **kwargs):
        raise decisions.DecisionsError('Model service is unavailable, timed out, or returned invalid JSON.')
    monkeypatch.setattr(decisions, 'ask', broken)
    message = post(s, '/api/dataset-chat/messages', body(a, b, summary=True))['message']
    support = message['tool_trace'][0]['result']['answer_support']
    assert support['status'] == 'unavailable' and 'unavailable' in support['reason']


def test_refused_sentences_are_counted_as_unchecked():
    from lapi_app.lapi_agent import answer_support
    records = [{'citation_index': 1, 'title': 'Invoice', 'data': {'text': 'Total 42.'}}]
    import lapi_app.lapi_models.decisions as d
    original = (d.snapshot, d.ask)
    try:
        d.snapshot = lambda: SNAP
        d.ask = lambda snap, evidence, questions, cfg=None: [{'type': 'refusal', 'name': q['name']} for q in questions]
        result = answer_support.check('The total is 42. [1]', records)
    finally:
        d.snapshot, d.ask = original
    assert result['status'] == 'passed' and result['checked'] == 0 and result['refused'] == 1


def test_citation_after_the_full_stop_belongs_to_its_sentence():
    from lapi_app.lapi_agent.answer_support import claims
    assert claims('The total is 42. [1] The vendor is Acme [2].\n- Due 1 May [1][2]') == [
        {'text': 'The total is 42.', 'cited': [1]}, {'text': 'The vendor is Acme.', 'cited': [2]}, {'text': 'Due 1 May', 'cited': [1, 2]}]


def test_lapi_agent_repairs_an_unsupported_sentence(system, monkeypatch):
    s = system; d, doc, t, ex = prepared(s)
    activate(monkeypatch, dict(source='documents'))
    asked = use_decisions(monkeypatch, supported_when('42'))
    drafts = []
    def answer(messages, tools, **kw):
        drafts.append(messages[-1]['content'])
        return {'text': ('The original says invoice total 99. [1]' if len(drafts) % 2 else 'The original says invoice total 42. [1]'), 'calls': []}
    monkeypatch.setattr(agent_model, 'complete', answer)
    p = plan(s, d, text='What amount is written in the selected original?', document_ids=[doc['id']], allow_external=True)
    assert '42' in p['explanation'] and len(asked) == 2 and 'not supported' in drafts[-1]


def test_without_consent_to_send_data_out_the_check_is_skipped_and_says_so(monkeypatch):
    from lapi_app.lapi_agent import answer_support
    monkeypatch.setattr(decisions, 'snapshot', lambda: SNAP)
    monkeypatch.setattr(decisions, 'ask', lambda *x, **y: pytest.fail('Nothing is sent without consent.'))
    result = answer_support.check('The total is 42. [1]', [{'citation_index': 1, 'title': 'Invoice', 'data': {}}], allow_external=False)
    assert result['status'] == 'skipped'


# ------------------------------------------------------- Dashboard chat routing

def test_decisions_sends_a_greeting_looking_request_to_knowledge(system, monkeypatch):
    from lapi_app.lapi_agent import dataset_chat_general
    s = system; a, one, b, two = setup(s, monkeypatch)
    asked = use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.8})
    monkeypatch.setattr(dataset_chat_general, 'decision', lambda *x: pytest.fail('Decisions said knowledge, so no direct answer.'))
    message = post(s, '/api/dataset-chat/messages', body(a, b, text='Who signed it?'))['message']
    assert message['request_route']['routing_mode'] == 'dataset_knowledge_chat'
    assert message['request_route']['routing_check']['status'] == 'knowledge'
    assert asked[0][1][0]['name'] == 'needs_knowledge'
    assert message['tool_trace'][0]['result']['retrieval']['mode'] == 'hybrid'


def test_a_low_knowledge_probability_keeps_the_model_written_direct_answer(system, monkeypatch):
    from lapi_app.lapi_agent import dataset_chat_general
    s = system; a, one, b, two = setup(s, monkeypatch)
    use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.02})
    monkeypatch.setattr(dataset_chat_general, 'decision', lambda *x: json.dumps({'route': 'general', 'answer': 'Hello! How can I help?'}))
    message = post(s, '/api/dataset-chat/messages', body(a, b, text='Hi', dataset_ids=[a['id']]))['message']
    assert message['text'] == 'Hello! How can I help?'
    assert message['request_route'] == {'routing_mode': 'dataset_general_chat', 'knowledge_used': False,
        'routing_check': {'status': 'general', 'probability': 0.02, 'threshold': 0.3, 'model': 'gpt-6-luna'}}


def test_decisions_never_skips_lookup_for_a_request_that_needs_knowledge(system, monkeypatch):
    s = system; a, one, b, two = setup(s, monkeypatch)
    asked = use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.0 if q['name'] == 'needs_knowledge' else 0.95})
    message = post(s, '/api/dataset-chat/messages', body(a, b, text='Hi, how many documents are there?'))['message']
    assert message['request_route']['routing_mode'] == 'dataset_knowledge_chat'
    assert all(q[0]['name'] != 'needs_knowledge' for _, q in asked)


# ------------------------------------------------------------ set-up chat

def choose(value, confidence=0.9):
    return lambda q, e: {'type': 'choice', 'choice': value, 'confidence': confidence, 'probabilities': []}


def test_setup_yes_no_and_options_are_read_by_decisions(accounts, monkeypatch):
    admin = accounts; login(admin)
    asked = use_decisions(monkeypatch, choose('yes'))
    assert admin.post('/api/setup/interpret', json={'stage': 'team', 'answer': 'yeah go on'}).json() == {'decision': 'yes'}
    assert [c['value'] for c in asked[-1][1][0]['choices']] == ['yes', 'no', '__none__']
    assert '"yeah go on"' in asked[-1][0][0]['content'][1]['text']
    use_decisions(monkeypatch, choose('Finance team'))
    picked = admin.post('/api/setup/interpret', json={'stage': 'choose', 'answer': 'the finance one', 'options': ['Just me', 'Finance team']})
    assert picked.json() == {'decision': 'answer', 'pick': 'Finance team'}


def test_setup_low_confidence_falls_back_and_a_confident_no_match_asks_again(accounts, monkeypatch):
    admin = accounts; login(admin)
    use_decisions(monkeypatch, choose('yes', confidence=0.4))
    assert admin.post('/api/setup/interpret', json={'stage': 'consent', 'answer': 'hmm'}).json() == {'decision': 'rules'}
    use_decisions(monkeypatch, choose('__none__'))
    assert admin.post('/api/setup/interpret', json={'stage': 'help', 'answer': 'what is this'}).json() == {'decision': 'unclear'}
    use_decisions(monkeypatch, choose('__none__', confidence=0.3))
    assert admin.post('/api/setup/interpret', json={'stage': 'help', 'answer': 'what is this'}).json() == {'decision': 'rules'}
    # Stages that need written answers (a name) never use Decisions.
    use_decisions(monkeypatch, lambda q, e: pytest.fail('Names are not a fixed choice.'))
    assert admin.post('/api/setup/interpret', json={'stage': 'name', 'answer': 'its mnai'}).json() == {'decision': 'rules'}


def test_setup_field_changes_go_to_the_chat_model_when_there_is_one(accounts, monkeypatch):
    admin = accounts; login(admin)
    use_decisions(monkeypatch, choose('change'))
    assert admin.post('/api/setup/interpret', json={'stage': 'fields', 'answer': 'add the due date', 'fields': ['Total']}).json() == {'decision': 'change'}
    monkeypatch.setattr(setup_assist, 'chat_snapshot', lambda: {'settings': {}})
    import lapi_app.prompt_suggest as suggest
    monkeypatch.setattr(suggest, 'call_model', lambda messages, snapshot, output=None: json.dumps({'decision': 'change', 'fields': [
        {'label': 'Total', 'type': 'number', 'description': 'Invoice total.'}, {'label': 'Due date', 'type': 'date', 'description': 'Payment due date.'}]}))
    reply = admin.post('/api/setup/interpret', json={'stage': 'fields', 'answer': 'add the due date', 'fields': ['Total']}).json()
    assert reply['decision'] == 'change' and [f['label'] for f in reply['fields']] == ['Total', 'Due date']


# --------------------------------------------- Lapi Agent agentic chat (production path)

def agentic_answer(monkeypatch, sentence_after_owner):
    from test_agentic_chat import agentic, prefetch_index
    agentic(monkeypatch)
    seen = []
    def complete(messages, tools, on_token=None):
        seen.append(messages); n = prefetch_index([{'messages': messages}])
        return {'text': f'Alice is the owner [{n}].' + (f' {sentence_after_owner} [{n}].' if sentence_after_owner else ''), 'calls': []}
    monkeypatch.setattr(agent_model, 'complete', complete)
    return seen


def test_agentic_chat_checks_cited_sentences_with_decisions(system, monkeypatch):
    from test_agentic_chat import indexed, thread_message
    s = system; d, doc = indexed(s)
    asked = use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.93})
    agentic_answer(monkeypatch, None)
    p = plan(s, d, text='Who is the owner of the invoice?')
    m = thread_message(s, p)
    support = m['request_route']['validation']['answer_support']
    assert support['status'] == 'passed' and support['checked'] == 1
    evidence, questions = asked[0]
    assert '"Alice is the owner."' in questions[0]['instructions'] and 'Alice' in evidence[0]['content'][1]['text']
    assert 'Checking the sources support the answer' in [step['label'] for step in m['answer_workflow']['steps']]


def test_agentic_chat_repairs_then_removes_a_sentence_decisions_rejects(system, monkeypatch):
    from test_agentic_chat import indexed, thread_message
    s = system; d, doc = indexed(s)
    use_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.04 if 'approved' in q['instructions'] else 0.95})
    seen = agentic_answer(monkeypatch, 'Bob approved it')  # passes the value check: no numbers, dates or full names
    p = plan(s, d, text='Who owns and approved the invoice?')
    m = thread_message(s, p)
    assert len(seen) == 2 and 'is not supported by the sources it cites' in seen[1][-1]['content']
    assert 'Bob approved' not in m['text'] and 'Alice is the owner [1].' in m['text'] and '1 statement removed' in m['text']
    validation = m['request_route']['validation']
    assert validation['result'] == 'removed' and validation['answer_support']['status'] == 'unsupported'
    assert validation['attempts'][0]['reason'] == 'not_supported'


def test_agentic_chat_without_decisions_says_so_and_sends_nothing(system, monkeypatch):
    from test_agentic_chat import indexed, thread_message
    s = system; d, doc = indexed(s)
    monkeypatch.setattr(decisions, 'ask', lambda *x, **y: pytest.fail('No Decisions Default, so no Decisions request.'))
    agentic_answer(monkeypatch, None)
    m = thread_message(s, plan(s, d, text='Who is the owner of the invoice?'))
    assert m['request_route']['validation']['answer_support'] == {'status': 'not_configured'}
    assert m['request_route']['validation']['result'] == 'passed'
    assert 'Checking the sources support the answer' not in [step['label'] for step in m['answer_workflow']['steps']]



def test_an_answer_decisions_matches_to_no_choice_is_asked_again_without_the_chat_model(accounts, monkeypatch):
    admin = accounts; login(admin)
    use_decisions(monkeypatch, choose('__none__'))
    monkeypatch.setattr(setup_assist, 'chat_snapshot', lambda: {'settings': {}})
    import lapi_app.prompt_suggest as suggest
    monkeypatch.setattr(suggest, 'call_model', lambda *a, **k: pytest.fail('Decisions already decided; the chat model is not asked.'))
    reply = admin.post('/api/setup/interpret', json={'stage': 'help', 'answer': 'hi', 'options': ['Add a collection', 'A team workspace']}).json()
    assert reply == {'decision': 'unclear'}
