"""OpenAI Decisions API as a model use: registered on its own for OpenAI, proven by two
known predicates, chosen as an optional workspace Default, and cleared again."""
import json

import httpx
from sqlalchemy import create_engine, inspect, text
from lapi_app import core, workspace_defaults, relational
from lapi_app.lapi_models import decisions
from test_dataset_models import system
from test_model_registration import body, register, cloud_transport

LUNA = 'gpt-6-luna'


def luna(**values):
    return body('decisions', 'openai-compatible', **({'provider_model': LUNA, 'capabilities': ['decisions'], 'allow_external': True} | values))


class Seen(list):
    judge = None


def fake_decisions(monkeypatch, judge=None):
    """A fake OpenAI /v1/decisions. `judge(question, input)` returns one answer dict."""
    seen = Seen()
    seen.judge = judge
    def default(question, evidence):
        text_input = json.dumps(evidence)
        if question['type'] == 'predicate':
            return {'type': 'predicate', 'probability': 0.97 if '4827' in question['instructions'] and '4827' in text_input else 0.03}
        if question['type'] == 'choice':
            first = question['choices'][0]['value']
            return {'type': 'choice', 'choice': first, 'confidence': 0.9,
                    'probabilities': [{'value': c['value'], 'probability': 0.9 if c['value'] == first else 0.1 / (len(question['choices']) - 1)} for c in question['choices']]}
        return {'type': 'refusal'}
    def handle(request):
        payload = json.loads(request.content)
        seen.append((request.url.path, payload, request.headers.get('authorization')))
        assert request.url.path == '/v1/decisions'
        answers = [dict((seen.judge or default)(q, payload['input']), name=q.get('name')) for q in payload['questions']]
        return httpx.Response(200, json={'answers': answers, 'model': payload['model'], 'usage': {'input_tokens': 120, 'output_tokens': 0}})
    cloud_transport(monkeypatch, handle)
    return seen


def make_default(s, model):
    return s.api.put('/api/model-registrations/' + model['id'] + '/default', json={'role': 'decisions'})


def ready(s, monkeypatch, judge=None):
    seen = fake_decisions(monkeypatch, judge)
    tested = s.api.post('/api/model-registrations/test', json=luna())
    assert tested.status_code == 200, tested.text
    model = register(s, luna())
    assert make_default(s, model).status_code == 200
    return model, seen


def test_decisions_test_sends_two_known_predicates_and_unlocks_the_default(system, monkeypatch):
    s = system; seen = fake_decisions(monkeypatch)
    result = s.api.post('/api/model-registrations/test', json=luna())
    assert result.status_code == 200, result.text
    assert result.json()['decisions_validated'] is True
    path, payload, auth = seen[-1]
    assert payload['model'] == LUNA and [q['type'] for q in payload['questions']] == ['predicate', 'predicate']
    assert auth == 'Bearer synthetic-secret'
    model = register(s, luna())
    assert model['capabilities'] == ['decisions']
    assert s.api.get('/api/workspace/defaults').json()['decisions_model_id'] is None
    changed = make_default(s, model)
    assert changed.status_code == 200, changed.text
    assert changed.json()['decisions_model_id'] == model['id'] == workspace_defaults.current()['decisions']
    snap = decisions.snapshot()
    assert snap['provider_model'] == LUNA and snap['capability'] == 'decisions'
    # Clearing it returns every caller to its own rules.
    cleared = s.api.delete('/api/workspace/defaults/decisions')
    assert cleared.status_code == 200 and cleared.json()['decisions_model_id'] is None and decisions.snapshot() is None


def test_a_model_that_answers_the_test_wrongly_is_refused(system, monkeypatch):
    s = system
    fake_decisions(monkeypatch, lambda q, e: {'type': 'predicate', 'probability': 0.6})
    result = s.api.post('/api/model-registrations/test', json=luna())
    assert result.status_code == 400 and 'answered the Decisions test incorrectly' in result.json()['detail']
    model = register(s, luna())
    refused = make_default(s, model)
    assert refused.status_code == 409 and 'Test the connection' in refused.json()['detail']


def test_decisions_is_openai_only_and_registered_on_its_own(system):
    s = system
    other = body('decisions', 'azure-openai', capabilities=['decisions'])
    response = s.api.post('/api/model-registrations', json=other)
    assert response.status_code == 400 and 'Decisions works with OpenAI connections' in response.json()['detail']
    mixed = s.api.post('/api/model-registrations', json=luna(capabilities=['chat', 'decisions']))
    assert mixed.status_code == 400 and 'Decisions is registered on its own' in mixed.json()['detail']
    choices = {c['id']: c['categories'] for c in s.api.get('/api/model-providers').json()}
    assert 'decisions' in choices['openai']
    assert all('decisions' not in categories for id, categories in choices.items() if id != 'openai')


def test_a_chat_model_cannot_become_the_decisions_default(system, monkeypatch):
    s = system; fake_decisions(monkeypatch)
    chat = register(s, body('chat', 'openai-compatible', provider_model='gpt-5.6-luna', allow_external=True))
    refused = make_default(s, chat)
    assert refused.status_code == 409 and 'Only an enabled decisions model' in refused.json()['detail']


def test_only_administrators_change_the_decisions_default(system, monkeypatch):
    s = system; model, _ = ready(s, monkeypatch)
    from lapi_app import dataset_access
    monkeypatch.setattr(dataset_access, 'require_admin', lambda actor: (_ for _ in ()).throw(__import__('fastapi').HTTPException(403, 'Administrators only.')))
    assert s.api.delete('/api/workspace/defaults/decisions').status_code == 403
    assert workspace_defaults.current()['decisions'] == model['id']


def test_refusals_and_wrong_shapes_are_reported_not_passed(system, monkeypatch):
    s = system; model, seen = ready(s, monkeypatch)
    snap = decisions.snapshot()
    seen.judge = lambda q, e: {'type': 'refusal'}
    answers = decisions.ask(snap, 'evidence', [{'type': 'predicate', 'name': 'q', 'instructions': 'Is it true?'}])
    assert answers[0]['type'] == 'refusal'
    seen.judge = (lambda q, e: {'type': 'choice', 'choice': 'invented', 'confidence': 1.0, 'probabilities': []})
    try:
        decisions.ask(snap, 'evidence', [{'type': 'choice', 'name': 'q', 'instructions': 'Which?', 'choices': [{'value': 'a'}, {'value': 'b'}]}])
        assert False, 'an invented choice must not be accepted'
    except decisions.DecisionsError as exc:
        assert 'not offered' in str(exc)


def test_older_database_gains_the_decisions_default_column(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'old.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE lapi_workspace_defaults (workspace_id VARCHAR(40) PRIMARY KEY, chat_model_id VARCHAR(80), '
            'extraction_model_id VARCHAR(80), embedding_model_id VARCHAR(80), ocr_model_id VARCHAR(80), embedding_snapshot_json TEXT, '
            'active_collection VARCHAR(100), reindex_json TEXT, updated_by VARCHAR(80), updated_at FLOAT)'))
        core.Base.metadata.create_all(connection)
        relational.upgrade_legacy(connection)
        assert 'decisions_model_id' in {c['name'] for c in inspect(connection).get_columns('lapi_workspace_defaults')}
