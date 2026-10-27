"""OCR is a fourth model use: ticked in Model Registration, proven by reading a sample image,
chosen as a workspace Default, and used by datasets that do not pick their own OCR model."""
import json

import httpx
import pytest
from sqlalchemy import create_engine, inspect, text
from lapi_app import core, worker, workspace_defaults, dataset_models as routing, relational
from lapi_app.lapi_models import cloud_ocr
from test_dataset_models import system, dataset, mapping
from test_model_registration import body, register, cloud_transport
from test_image_uploads import picture

LUNA = 'gpt-5.6-luna'


def openai(**values):
    return body('chat', 'openai-compatible', provider_model=LUNA, capabilities=['chat', 'extraction', 'ocr'], allow_external=True,
                context_limit=200000, max_output_tokens=4096, **values)


def vision(monkeypatch, reads='Lapi OCR test code 4827', api='chat_completions'):
    """A fake OpenAI that answers chat, extraction and image transcription requests."""
    seen = []
    def handle(request):
        payload = json.loads(request.content)
        seen.append((request.url.path, payload))
        images = [part for message in payload.get('messages', payload.get('input', [])) if isinstance(message.get('content'), list)
                  for part in message['content'] if part.get('type') in ('image_url', 'input_image')]
        if images:
            content = json.dumps({'text': reads, 'unreadable': False})
        elif payload.get('tools'):
            call = {'id': 'call-1', 'type': 'function', 'function': {'name': 'connection_status', 'arguments': '{"status":"ready"}'}}
            return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None, 'tool_calls': [call]}}]})
        else:
            content = json.dumps({'status': 'ready'})
        if request.url.path.endswith('/responses'):
            return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': content}]}]})
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content}}]})
    cloud_transport(monkeypatch, handle)
    return seen


def test_ocr_test_reads_a_sample_image_and_unlocks_the_ocr_default(system, monkeypatch):
    s = system; seen = vision(monkeypatch)
    for category in ('chat', 'extraction', 'ocr'):
        result = s.api.post('/api/model-registrations/test', json=openai() | {'category': category})
        assert result.status_code == 200, result.text
    assert result.json()['ocr_validated'] is True
    image_request = next(p for path, p in seen if any(isinstance(m.get('content'), list) for m in p['messages']))
    assert image_request['model'] == LUNA and image_request['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
    model = register(s, openai())
    assert model['capabilities'] == ['chat', 'extraction', 'ocr'] and model['ocr_eligible'] is True
    changed = s.api.put('/api/model-registrations/' + model['id'] + '/default', json={'role': 'ocr'})
    assert changed.status_code == 200, changed.text
    assert changed.json()['ocr_model_id'] == model['id'] == workspace_defaults.current()['ocr']


def test_ocr_responses_api_sends_the_image_as_input_image(system, monkeypatch):
    s = system; seen = vision(monkeypatch)
    value = openai(connection=openai()['connection'] | {'chat_api': 'responses'}) | {'category': 'ocr'}
    result = s.api.post('/api/model-registrations/test', json=value)
    assert result.status_code == 200, result.text
    path, payload = seen[-1]
    assert path.endswith('/responses') and payload['input'][1]['content'][1]['type'] == 'input_image'


def test_model_that_cannot_read_the_image_is_not_eligible(system, monkeypatch):
    s = system; vision(monkeypatch, reads='I cannot see any image.')
    assert s.api.post('/api/model-registrations/test', json=openai()).status_code == 200  # Chat itself works.
    result = s.api.post('/api/model-registrations/test', json=openai() | {'category': 'ocr'})
    assert result.status_code == 400 and 'did not read the test image' in result.json()['detail']
    model = register(s, openai())
    assert model['ocr_eligible'] is False
    refused = s.api.put('/api/model-registrations/' + model['id'] + '/default', json={'role': 'ocr'})
    assert refused.status_code == 409 and 'cannot be the OCR Default yet' in refused.json()['detail']


def test_ocr_is_only_offered_for_openai_and_gemini(system):
    s = system
    other = body('extraction', 'azure-openai', capabilities=['extraction', 'ocr'])
    response = s.api.post('/api/model-registrations', json=other)
    assert response.status_code == 400 and 'OCR works with OpenAI' in response.json()['detail']
    mixed = s.api.post('/api/model-registrations', json=openai() | {'capabilities': ['ocr', 'embedding'], 'category': 'ocr'})
    assert mixed.status_code == 400 and 'Embedding is registered on its own' in mixed.json()['detail']
    choices = {c['id']: c['categories'] for c in s.api.get('/api/model-providers').json()}
    assert 'ocr' in choices['openai'] and 'ocr' in choices['gemini']
    assert all('ocr' not in categories for id, categories in choices.items() if id not in ('openai', 'gemini'))


def test_dataset_without_its_own_ocr_model_uses_the_workspace_ocr_default(system, monkeypatch):
    s = system; seen = vision(monkeypatch, reads='Lapi OCR test code 4827. Invoice total: 42.50')
    for category in ('chat', 'extraction', 'ocr'):
        assert s.api.post('/api/model-registrations/test', json=openai() | {'category': category}).status_code == 200
    model = register(s, openai())
    assert s.api.put('/api/model-registrations/' + model['id'] + '/default', json={'role': 'ocr'}).status_code == 200
    d = dataset(s)
    saved = s.api.get('/api/datasets/' + d['id'] + '/models').json()
    assert saved['ocr_model_id'] is None and saved['workspace_defaults']['ocr_model_id'] == model['id'] and saved['models_complete']
    snapshot = cloud_ocr.dataset_snapshot(routing.owned(d['id'], s.owner, 'knowledge_base'))
    assert snapshot['provider_model'] == LUNA and snapshot['capability'] == 'ocr'
    upload = s.api.post('/api/documents/upload', data={'dataset_id': d['id'], 'allow_external': 'true'}, files=[('files', ('receipt.png', picture(), 'image/png'))])
    assert upload.status_code == 200, upload.text
    did = upload.json()['documents'][0]['id']
    assert worker.run_once()
    doc = s.api.get('/api/documents/' + did).json()
    assert doc['status'] == 'ready', doc.get('error')
    assert 'Invoice total: 42.50' in core.store.json('documents/' + did + '/parsed.json')['pages'][0]['text']
    # The dataset may also name the workspace OCR Default explicitly without mapping it.
    current = s.api.get('/api/datasets/' + d['id'] + '/models').json()
    assert mapping(s, d, mappings=current['mappings'], ocr_model_id=model['id'])['ocr_model_id'] == model['id']


def test_a_dataset_ocr_model_that_lost_its_image_test_is_refused(system, monkeypatch):
    s = system; vision(monkeypatch)
    assert s.api.post('/api/model-registrations/test', json=openai() | {'category': 'ocr'}).status_code == 200
    model = register(s, openai() | {'category': 'ocr', 'capabilities': ['ocr']})
    assert model['ocr_eligible'] is True and model['capabilities'] == ['ocr']
    d = dataset(s)
    current = s.api.get('/api/datasets/' + d['id'] + '/models').json()
    mapping(s, d, mappings=current['mappings'] + [{'model_id': model['id'], 'enabled': True}], ocr_model_id=model['id'])
    # Editing the connection without a new OCR test leaves no passed image test for the new version.
    edited = s.api.put('/api/model-registrations/' + model['id'], json=openai() | {'category': 'ocr', 'capabilities': ['ocr'], 'timeout': 90})
    assert edited.status_code == 200 and edited.json()['ocr_eligible'] is False
    with pytest.raises(Exception) as refused:
        cloud_ocr.dataset_snapshot(routing.owned(d['id'], s.owner, 'knowledge_base'))
    assert 'tick OCR for it and pass Test connection' in str(getattr(refused.value, 'detail', refused.value))


def test_older_database_gains_the_ocr_default_column(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'old.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE lapi_workspace_defaults (workspace_id VARCHAR(40) PRIMARY KEY, chat_model_id VARCHAR(80), '
            'extraction_model_id VARCHAR(80), embedding_model_id VARCHAR(80), embedding_snapshot_json TEXT, active_collection VARCHAR(100), '
            'reindex_json TEXT, updated_by VARCHAR(80), updated_at FLOAT)'))
        core.Base.metadata.create_all(connection)
        relational.upgrade_legacy(connection)
        assert 'ocr_model_id' in {c['name'] for c in inspect(connection).get_columns('lapi_workspace_defaults')}
