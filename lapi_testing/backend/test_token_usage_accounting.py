"""WS10: provider-reported tokens per call, versioned prices and the admin usage report."""
import csv
import io
import time
from decimal import Decimal
import pytest
from sqlalchemy import select
from lapi_app import core, providers, worker
from lapi_app.lapi_agent import token_usage
from lapi_app.usage_tables import TokenUsage, ModelPrice
from test_dataset_models import system, dataset, upload
from test_user_management import accounts, login

PRICE = {'currency': 'USD', 'input_price': '2.00', 'cached_input_price': '0.50',
         'cache_write_price': '2.50', 'output_price': '8.00', 'reasoning_price': None}


def cost(call, price=PRICE):
    return token_usage.call_cost(call, price)


# ------------------------------------------------------------- provider formulas

def test_openai_cached_tokens_are_inside_prompt_and_never_counted_twice():
    usage = token_usage.parse_usage({'usage': {'prompt_tokens': 1000, 'completion_tokens': 200,
        'prompt_tokens_details': {'cached_tokens': 800}, 'completion_tokens_details': {'reasoning_tokens': 50}}}, 'openai')
    assert (usage['input_tokens'], usage['cached_input_tokens'], usage['output_tokens'], usage['reasoning_tokens']) == (1000, 800, 200, 50)
    status, amount, currency = cost(usage)
    # 200 uncached x 2 + 800 cached x 0.5 + 150 output x 8 + 50 reasoning x 8 (output price), per 1M.
    assert status == 'priced' and currency == 'USD'
    assert amount == Decimal('0.0024')


def test_openai_responses_api_usage_shape():
    usage = token_usage.parse_usage({'usage': {'input_tokens': 300, 'output_tokens': 40,
        'input_tokens_details': {'cached_tokens': 100}, 'output_tokens_details': {'reasoning_tokens': 10}}}, 'openai')
    assert (usage['input_tokens'], usage['cached_input_tokens'], usage['output_tokens'], usage['reasoning_tokens']) == (300, 100, 40, 10)


def test_claude_cache_reads_and_writes_are_reported_separately_and_added_once():
    usage = token_usage.parse_usage({'usage': {'input_tokens': 200, 'cache_read_input_tokens': 800,
        'cache_creation_input_tokens': 100, 'output_tokens': 200}}, 'anthropic')
    assert (usage['input_tokens'], usage['cached_input_tokens'], usage['cache_write_tokens']) == (1100, 800, 100)
    status, amount, _ = cost(usage, {'currency': 'USD', 'input_price': '3', 'cached_input_price': '0.30',
                                      'cache_write_price': '3.75', 'output_price': '15'})
    # 200 x 3 + 800 x 0.30 + 100 x 3.75 + 200 x 15, per 1M tokens.
    assert status == 'priced' and amount == Decimal('0.004215')


def test_bedrock_cache_tokens_and_vertex_thoughts():
    bedrock = token_usage.parse_usage({'usage': {'inputTokens': 50, 'outputTokens': 20,
        'cacheReadInputTokens': 30, 'cacheWriteInputTokens': 10}}, 'bedrock')
    assert (bedrock['input_tokens'], bedrock['cached_input_tokens'], bedrock['cache_write_tokens'], bedrock['output_tokens']) == (90, 30, 10, 20)
    vertex = token_usage.parse_usage({'usageMetadata': {'promptTokenCount': 120, 'cachedContentTokenCount': 100,
        'candidatesTokenCount': 30, 'thoughtsTokenCount': 70}}, 'vertex')
    assert (vertex['input_tokens'], vertex['cached_input_tokens'], vertex['output_tokens'], vertex['reasoning_tokens']) == (120, 100, 100, 70)
    status, amount, _ = cost(vertex, {'currency': 'USD', 'input_price': '1', 'cached_input_price': '0.25',
                                      'output_price': '4', 'reasoning_price': '10'})
    # 20 x 1 + 100 x 0.25 + 30 x 4 + 70 x 10 (separate reasoning price), per 1M.
    assert status == 'priced' and amount == Decimal('0.000865')


def test_ollama_and_embedding_reports():
    chat = token_usage.parse_usage({'prompt_eval_count': 40, 'eval_count': 9, 'message': {'content': 'private'}}, 'ollama')
    assert (chat['input_tokens'], chat['output_tokens']) == (40, 9) and 'message' not in (chat['usage'] or {})
    embedding = token_usage.parse_usage({'prompt_eval_count': 12, 'embeddings': [[0.1]]}, 'ollama', embedding=True)
    assert (embedding['input_tokens'], embedding['output_tokens'], embedding['reported']) == (12, 0, True)
    openai_embedding = token_usage.parse_usage({'usage': {'prompt_tokens': 7, 'total_tokens': 7}, 'data': []}, 'openai', embedding=True)
    assert (openai_embedding['input_tokens'], openai_embedding['output_tokens']) == (7, 0)
    unreported = token_usage.parse_usage({'data': []}, 'openai', embedding=True)
    assert unreported['input_tokens'] is None and unreported['output_tokens'] is None and not unreported['reported']


def test_missing_cached_price_falls_back_to_input_price_and_cost_uses_decimal():
    usage = {'input_tokens': 3, 'cached_input_tokens': 1, 'cache_write_tokens': None, 'output_tokens': 1, 'reasoning_tokens': None}
    status, amount, _ = cost(usage, {'currency': 'EUR', 'input_price': '0.1', 'output_price': '0.3'})
    assert status == 'priced' and amount == Decimal('0.0000006')
    assert token_usage.amount_text(amount) == '0.0000006'


# ------------------------------------------------------------- per-answer summary

def test_summary_reports_price_not_set_and_not_reported_without_zero_cost():
    with token_usage.collect() as calls:
        token_usage.record({'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}, 'openai')
        token_usage.attempt()  # Failed request: no provider report.
        summary = token_usage.summary(calls)
    assert summary['model_calls'] == 2 and summary['not_reported_calls'] == 1
    assert summary['cost']['status'] == 'price_not_set' and summary['cost']['totals'] == []
    assert summary['cost']['price_not_set_calls'] == 1 and summary['cost']['not_reported_calls'] == 1
    assert [step['cost']['status'] for step in summary['steps']] == ['price_not_set', 'not_reported']
    assert summary['steps'][1]['input_tokens'] is None
    empty = token_usage.summary([])
    assert empty['source'] == 'no_model_calls' and empty['cost']['status'] == 'no_model_calls' and empty['steps'] == []


def test_summary_keeps_existing_keys_and_adds_cache_reasoning_steps():
    with token_usage.collect() as calls:
        with token_usage.stage('tool_step'):
            token_usage.record({'usage': {'input_tokens': 10, 'cache_read_input_tokens': 4,
                                          'cache_creation_input_tokens': 2, 'output_tokens': 3}}, 'anthropic')
        token_usage.record({'usage': {'prompt_tokens': 100, 'completion_tokens': 40,
            'prompt_tokens_details': {'cached_tokens': 60}, 'completion_tokens_details': {'reasoning_tokens': 30}}}, 'openai', stage='final_answer')
        summary = token_usage.summary(calls)
    for key in ('scope', 'input_tokens', 'output_tokens', 'model_calls', 'reported_calls', 'complete', 'source'):
        assert key in summary
    assert summary['input_tokens'] == 116 and summary['cached_input_tokens'] == 64
    assert summary['cache_write_tokens'] == 2 and summary['reasoning_tokens'] == 30 and summary['output_tokens'] == 43
    assert [step['stage'] for step in summary['steps']] == ['tool_step', 'final_answer']
    assert summary['cost']['approximate'] is True


def test_stage_resolution_for_scope_labels_and_embeddings():
    with token_usage.scope(owner='alice', stage='extraction', persist=False) as current:
        token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai')
        token_usage.record({'usage': {'prompt_tokens': 1}}, 'openai', embedding=True, query=True)
        token_usage.record({'usage': {'prompt_tokens': 1}}, 'openai', embedding=True)
        with token_usage.stage('repair'):
            token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai')
        with token_usage.stage('not-a-stage'):
            token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai')
    assert [row['stage'] for row in current.rows] == ['extraction', 'prefetch_embedding', 'reindex', 'repair', 'extraction']
    assert all(row['owner_id'] == 'alice' for row in current.rows)


def test_no_collector_or_scope_records_nothing():
    assert token_usage.attempt() is None
    assert token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai') is None


def test_pending_call_is_filled_once_and_extra_requests_are_separate_calls():
    with token_usage.collect() as calls:
        with token_usage.pending(protocol='vertex', embedding=True, query=False):
            token_usage.report({'usageMetadata': {'promptTokenCount': 5}}, 'vertex', embedding=True)
            token_usage.report({'usageMetadata': {'promptTokenCount': 6}}, 'vertex', embedding=True)
    assert [c['input_tokens'] for c in calls] == [5, 6] and all(c['stage'] == 'reindex' for c in calls)


# ------------------------------------------------------------- persistence

def rows(**where):
    with core.Session() as session:
        statement = select(TokenUsage)
        for key, value in where.items():
            statement = statement.where(getattr(TokenUsage, key) == value)
        return list(session.scalars(statement.order_by(TokenUsage.created_at)))


def test_scope_persists_one_row_per_call_with_attribution(system):
    with token_usage.scope(owner='alice', dataset_id='d1', conversation_id='c1', stage='chat'):
        with token_usage.stage('final_answer'):
            token_usage.record({'usage': {'prompt_tokens': 12, 'completion_tokens': 3,
                'prompt_tokens_details': {'cached_tokens': 8}}}, 'openai', model_id='m1', provider_model='gpt-test',
                parameters={'temperature': 0, 'messages': ['never stored']})
        token_usage.attempt(model_id='m1')
        token_usage.annotate(message_id='msg1')
    saved = rows(conversation_id='c1')
    assert len(saved) == 2
    first, failed = sorted(saved, key=lambda r: not r.reported)
    assert (first.owner_id, first.dataset_id, first.message_id, first.stage, first.model_id) == ('alice', 'd1', 'msg1', 'final_answer', 'm1')
    assert (first.input_tokens, first.cached_input_tokens, first.output_tokens, first.reported) == (12, 8, 3, True)
    assert 'never stored' not in (first.parameters_json or '') and '"temperature": 0' in first.parameters_json
    assert failed.input_tokens is None and failed.output_tokens is None and not failed.reported


def test_persistence_failure_never_fails_the_caller(system, monkeypatch):
    class Broken:
        def begin(self): raise RuntimeError('database unavailable')
        def __call__(self): raise RuntimeError('database unavailable')
    monkeypatch.setattr(core, 'Session', Broken())
    with token_usage.scope(owner='alice'):
        token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai', model_id='m1')
        with token_usage.collect() as calls:
            token_usage.record({'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, 'openai', model_id='m1')
            assert token_usage.summary(calls)['input_tokens'] == 1


def test_index_job_records_embedding_calls_against_the_job(system, monkeypatch):
    s = system; d = dataset(s)
    original = providers.embed
    def embed(texts, query=False):
        token_usage.record({'usage': {'prompt_tokens': 7 * len(texts)}}, 'openai', embedding=True, query=query)
        return original(texts, query=query)
    monkeypatch.setattr(providers, 'embed', embed)
    document = upload(s, d)['documents'][0]
    job = next(j for j in s.api.get('/api/jobs').json() if j['target_id'] == document['id'])
    saved = rows(job_id=job['id'])
    assert saved and all(r.stage == 'reindex' and r.dataset_id == d['id'] and r.owner_id == s.owner for r in saved)
    assert all(r.input_tokens and r.output_tokens == 0 for r in saved)


# ------------------------------------------------------------- prices and admin report

def model(id='model-a', name='Model A'):
    with core.Session.begin() as session:
        session.add(core.Record(id=id, kind='model', owner='administrator', name=name, ref='models/'+id+'.json'))
    return id


def add_price(client, model_id, **values):
    body = {'currency': 'USD', 'input_price': '2', 'output_price': '8'} | values
    result = client.post(f'/api/model-registrations/{model_id}/prices', json=body)
    assert result.status_code == 200, result.text
    return result.json()


def usage_call(model_id, prompt=1000, completion=100, dataset_id='d1', owner='administrator', **fields):
    with token_usage.scope(owner=owner, dataset_id=dataset_id, stage=fields.pop('stage', 'final_answer')):
        token_usage.record({'usage': {'prompt_tokens': prompt, 'completion_tokens': completion}}, 'openai',
                           model_id=model_id, provider_model='provider-'+model_id, **fields)


def test_price_change_never_rewrites_past_costs(accounts):
    login(accounts)
    mid = model()
    first = add_price(accounts, mid, effective_at=time.time() - 60)
    usage_call(mid)
    second = add_price(accounts, mid, input_price='4', output_price='16')
    usage_call(mid)
    saved = rows(model_id=mid)
    assert sorted(r.price_version_id for r in saved) == sorted([first['id'], second['id']])
    versions = accounts.get(f'/api/model-registrations/{mid}/prices').json()
    assert versions['current']['id'] == second['id'] and len(versions['versions']) == 2
    # 1000 x 2 + 100 x 8 = 0.0028; then 1000 x 4 + 100 x 16 = 0.0056.
    report = accounts.get('/api/admin/token-usage?group_by=model').json()
    assert report['totals']['cost']['totals'] == [{'currency': 'USD', 'amount': '0.0084'}]
    # A backdated version entered later does not reprice calls already made.
    add_price(accounts, mid, input_price='100', output_price='100', effective_at=time.time() - 3600)
    again = accounts.get('/api/admin/token-usage').json()
    assert again['totals']['cost']['totals'] == [{'currency': 'USD', 'amount': '0.0084'}]


def test_admin_report_groups_filters_currencies_and_exclusions(accounts):
    login(accounts)
    a, b = model('model-a', 'Model A'), model('model-b', 'Model B')
    add_price(accounts, a, effective_at=time.time() - 60)
    add_price(accounts, b, currency='EUR', input_price='1', output_price='1', effective_at=time.time() - 60)
    usage_call(a, dataset_id='d1')
    usage_call(a, dataset_id='d2', prompt=500, completion=50)
    usage_call(b, dataset_id='d1', prompt=100, completion=10, stage='tool_step')
    with token_usage.scope(owner='colleague', dataset_id='d1'):
        token_usage.attempt(model_id='model-c')  # Not reported.
        token_usage.record({'usage': {'prompt_tokens': 5, 'completion_tokens': 5}}, 'openai', model_id='model-c')  # Price not set.
    report = accounts.get('/api/admin/token-usage?group_by=dataset').json()
    totals = report['totals']
    assert totals['model_calls'] == 5 and totals['not_reported_calls'] == 1
    assert totals['input_tokens'] == 1605 and totals['output_tokens'] == 165
    assert totals['cost']['price_not_set_calls'] == 1 and totals['cost']['not_reported_calls'] == 1
    assert {t['currency'] for t in totals['cost']['totals']} == {'USD', 'EUR'}  # never added together
    groups = {g['key']: g for g in report['groups']}
    assert groups['d1']['model_calls'] == 4 and groups['d2']['total_tokens'] == 550
    by_model = {g['key']: g for g in accounts.get('/api/admin/token-usage?group_by=model').json()['groups']}
    assert by_model['model-a']['label'] == 'Model A' and by_model['model-a']['input_tokens'] == 1500
    by_user = {g['key']: g for g in accounts.get('/api/admin/token-usage?group_by=user').json()['groups']}
    assert by_user['administrator']['model_calls'] == 3 and by_user['colleague']['model_calls'] == 2
    by_day = accounts.get('/api/admin/token-usage?group_by=day').json()
    assert len(by_day['groups']) == 1 and by_day['by_day'][0]['models']['model-a'] == 1650
    filtered = accounts.get('/api/admin/token-usage?stage=tool_step').json()['totals']
    assert filtered['model_calls'] == 1 and filtered['cost']['totals'] == [{'currency': 'EUR', 'amount': '0.00011'}]
    assert accounts.get('/api/admin/token-usage?dataset_id=d2').json()['totals']['model_calls'] == 1
    future = accounts.get('/api/admin/token-usage?start=2999-01-01').json()['totals']
    assert future['model_calls'] == 0 and future['cost']['status'] == 'no_model_calls'
    assert accounts.get('/api/admin/token-usage?stage=bogus').status_code == 400


def test_csv_export_marks_unpriced_and_unreported_rows_and_escapes_formulas(accounts):
    login(accounts)
    mid = model('model-a', '=HYPERLINK("x")')
    with token_usage.scope(owner='administrator', dataset_id='d1'):
        token_usage.attempt(model_id=mid)
        token_usage.record({'usage': {'prompt_tokens': 5, 'completion_tokens': 5}}, 'openai', model_id=mid)
    result = accounts.get('/api/admin/token-usage/export')
    assert result.status_code == 200 and result.headers['content-type'].startswith('text/csv')
    table = list(csv.DictReader(io.StringIO(result.text)))
    assert sorted(row['approximate_cost'] for row in table) == ['Not reported', 'Price not set']
    assert all(row['model'].startswith("'=") for row in table)


def test_usage_and_prices_are_admin_only(accounts):
    login(accounts)
    mid = model()
    login(accounts, 'Colleague')
    for response in (accounts.get('/api/admin/token-usage'), accounts.get('/api/admin/token-usage/export'),
                     accounts.get(f'/api/model-registrations/{mid}/prices'),
                     accounts.post(f'/api/model-registrations/{mid}/prices', json={'currency': 'USD', 'input_price': '1', 'output_price': '1'})):
        assert response.status_code == 403
    with core.Session() as session:
        assert session.scalar(select(ModelPrice.id)) is None


def test_price_validation(accounts):
    login(accounts)
    mid = model()
    for body in ({'currency': 'USD', 'input_price': '-1', 'output_price': '1'},
                 {'currency': 'US', 'input_price': '1', 'output_price': '1'},
                 {'currency': 'USD', 'output_price': '1'},
                 {'currency': 'USD', 'input_price': 'free', 'output_price': '1'}):
        assert accounts.post(f'/api/model-registrations/{mid}/prices', json=body).status_code == 422
    assert accounts.post('/api/model-registrations/missing/prices', json={'currency': 'USD', 'input_price': '1', 'output_price': '1'}).status_code == 404
    saved = add_price(accounts, mid, currency='eur', input_price=0.15, cached_input_price='', output_price='0.6')
    assert saved['currency'] == 'EUR' and saved['input_price'] == '0.15' and saved['cached_input_price'] is None
