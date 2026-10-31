"""Quick start: the dataset's extraction model suggests (and rewrites) extraction fields."""
import json
from types import SimpleNamespace
from fastapi.testclient import TestClient
from lapi_app import core, main, prompt_suggest, providers
from test_dataset_models import system, dataset
from test_user_management import accounts, login

LEASE = b'Lease agreement between Acme Ltd and Lapi Corp. Start date: 1 March 2026. Monthly rent: 4,200 EUR. Notice period: 90 days.'
SUGGESTION = {'name': 'Lease agreement fields', 'instructions': 'Return null when a value is missing.', 'fields': [
    {'key': 'landlord', 'label': 'Landlord', 'type': 'text', 'description': 'Landlord name as written.'},
    {'key': 'start_date', 'label': 'Start date', 'type': 'date', 'description': 'Lease start as YYYY-MM-DD.'},
    {'key': 'monthly_rent', 'label': 'Monthly rent', 'type': 'number', 'description': 'Rent per month as a number.'},
    {'key': 'monthly_rent', 'label': 'Duplicate', 'type': 'number', 'description': 'Dropped: same key.'}]}


def ready_document(client, d):
    uploaded = client.post('/api/documents/upload', files={'files': ('lease.txt', LEASE, 'text/plain')}, data={'dataset_id': d['id'], 'allow_external': 'true'})
    assert uploaded.status_code == 200, uploaded.text
    document_id = uploaded.json()['documents'][0]['id']
    core.store.put_json(f'documents/{document_id}/parsed.json', {'pages': [{'page': 1, 'text': LEASE.decode()}]})
    with core.Session.begin() as session:
        session.get(core.Record, document_id).status = 'ready'
    return document_id


def test_fields_are_suggested_from_the_document_and_can_be_rewritten(accounts, monkeypatch):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    document_id = ready_document(client, d)
    seen = []
    def model(messages, snapshot):
        seen.append(json.loads(messages[1]['content']))
        return '```json\n' + json.dumps(SUGGESTION) + '\n```'
    monkeypatch.setattr(prompt_suggest, 'call_model', model)
    result = client.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True})
    assert result.status_code == 200, result.text
    body = result.json()
    assert [f['key'] for f in body['fields']] == ['landlord', 'start_date', 'monthly_rent']
    assert 'Monthly rent: 4,200 EUR' in seen[0]['document_excerpt']
    assert body['schema']['properties']['start_date'] == {'type': ['string', 'null'], 'format': 'date', 'description': 'Start date: Lease start as YYYY-MM-DD.'}
    # The suggestion is a valid Lapi prompt template.
    saved = client.post('/api/templates', json={'name': body['name'], 'schema': body['schema'], 'instructions': body['instructions'], 'dataset_id': d['id']})
    assert saved.status_code == 200, saved.text
    rewrite = client.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True,
                                                         'request': 'Add the notice period', 'current': body['fields']})
    assert rewrite.status_code == 200
    assert seen[1]['requested_changes'] == 'Add the notice period' and len(seen[1]['current_fields']) == 3


def test_suggestions_need_editor_access_ready_documents_and_a_readable_reply(accounts, monkeypatch):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    document_id = ready_document(client, d)
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']], 'levels': {d['id']: 'viewer'}}).status_code == 200
    with TestClient(main.app) as viewer:
        login(viewer, 'Colleague')
        refused = viewer.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True})
        assert refused.status_code == 403
    monkeypatch.setattr(prompt_suggest, 'call_model', lambda messages, snapshot: 'not json at all')
    unreadable = client.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True})
    assert unreadable.status_code == 502 and 'could not be read' in unreadable.json()['detail']
    def failing(messages, snapshot):
        raise providers.ProviderError('model offline')
    monkeypatch.setattr(prompt_suggest, 'call_model', failing)
    offline = client.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True})
    assert offline.status_code == 502 and 'model offline' in offline.json()['detail']
    with core.Session.begin() as session:
        session.get(core.Record, document_id).status = 'processing'
    waiting = client.post('/api/templates/suggest', json={'dataset_id': d['id'], 'document_ids': [document_id], 'allow_external': True})
    assert waiting.status_code == 409
