"""WS9: one knowledge base, workspace Default models and delete-and-reindex."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from lapi_app import core, knowledge, knowledge_catalog, providers, worker, workspace_defaults, dataset_models as routing
from lapi_app.lapi_agent.chat_knowledge import PublishedKnowledge, index_notice
from test_dataset_models import system, dataset, upload, model, post, template, conversation, message, make_default
from test_model_registration import body as registration, register
from test_agent_onboarding import processing_body, stage, finish


def embedding_of(d):
    return next(m for m in d['models'] if m['id'] == d['embedding_model_id'])


def generation_of(d):
    return next(m for m in d['models'] if 'chat' in m['capabilities'])


def distinct_space(monkeypatch, name='Rebuilt embeddings'):
    """Mock embeddings ignore the model name; give the replacement its own space."""
    original = providers.fingerprint
    monkeypatch.setattr(providers, 'fingerprint', lambda cfg=None: original(cfg)+('-rebuilt' if (cfg or core.settings()).get('embedding_model') == name else ''))


def test_one_collection_after_onboarding_and_zero_orphans(system):
    s = system; first = dataset(s, 'Invoices')
    body, files = processing_body(first)
    workflow = finish(s, stage(s, post(s, '/api/agent-v2/onboarding', body), files))
    assert workflow['status'] == 'completed'
    second = dataset(s, 'Policies'); upload(s, second)
    for d in (first, second, {'id': workflow['dataset_id']}): knowledge.sync(s.owner, d['id'])
    active = workspace_defaults.active_collection()
    assert active and knowledge_catalog.names() == [active]
    assert {knowledge.embedding_snapshot(s.owner, d['id'])['knowledge_collection'] for d in (first, second)} == {active}
    health = knowledge.health()
    assert health['collections'] == 1 and health['orphan_rows'] == 0 and not health['alert']
    assert s.api.get('/ready').json()['knowledge']['orphan_rows'] == 0


def test_catalog_lives_in_the_database_and_imports_legacy_manifests(system):
    s = system; d = dataset(s); upload(s, d)
    snapshot, _ = knowledge.sync(s.owner, d['id']); name = snapshot['knowledge_collection']
    assert not core.local_store.path('knowledge/'+name+'/manifest.json').exists()
    with core.Session() as db:
        rows = db.scalar(select(func.count()).select_from(knowledge_catalog.KnowledgePoint).where(knowledge_catalog.KnowledgePoint.collection_name == name))
    assert rows == len(knowledge.manifest(name)['points']) > 0
    legacy = 'lapi_knowledge_' + '0'*20
    core.local_store.put_json('knowledge/'+legacy+'/manifest.json', {'entities': {'x': {'stamp': 's', 'ids': ['p1']}},
        'points': {'p1': {'source_type': 'dataset', 'entity_id': 'x', 'text': 'Legacy'}}, 'vectors': {'p1': [1.0]}, 'failures': []})
    assert knowledge.manifest(legacy)['points']['p1']['text'] == 'Legacy'
    assert knowledge_catalog.vectors(legacy, ['p1']) == {'p1': [1.0]}
    assert not core.local_store.path('knowledge/'+legacy+'/manifest.json').exists()


def test_workspace_default_rules(system):
    s = system; d = dataset(s); generation = generation_of(d)
    second = model(s, generation['connection_profile_id'], 'Second chat', ['chat'])
    assert make_default(s, generation, 'chat').json()['chat_model_id'] == generation['id']
    # One Default per role: choosing another replaces it.
    assert make_default(s, second, 'chat').json()['chat_model_id'] == second['id']
    assert workspace_defaults.roles_of(generation['id']) == []
    # Only an enabled model with that capability.
    assert s.api.put('/api/model-registrations/'+embedding_of(d)['id']+'/default', json={'role': 'chat'}).status_code == 409
    disabled = model(s, generation['connection_profile_id'], 'Disabled chat', ['chat'], enabled=False)
    assert s.api.put('/api/model-registrations/'+disabled['id']+'/default', json={'role': 'chat'}).status_code == 409
    # The current Default stays enabled until another Default is chosen.
    values = {k: second[k] for k in ('name', 'connection_profile_id', 'provider_model', 'capabilities')} | {'enabled': False}
    refused = s.api.put('/api/models/'+second['id'], json=values)
    assert refused.status_code == 409 and 'Default' in refused.text
    # A registration must pass its connection test first.
    registered = register(s, registration('chat', 'ollama', provider_model='qwen3:4b'))
    untested = s.api.put('/api/model-registrations/'+registered['id']+'/default', json={'role': 'chat'})
    assert untested.status_code == 409 and 'Test the connection' in untested.text
    assert make_default(s, registered, 'chat').status_code == 200
    blocked = s.api.put('/api/model-registrations/'+registered['id'], json=registration('chat', 'ollama', provider_model='qwen3:4b', enabled=False))
    assert blocked.status_code == 409
    assert s.api.get('/api/workspace/defaults').json()['chat_model_id'] == registered['id']


def test_dataset_override_then_workspace_default(system):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]; generation = generation_of(d)
    workspace = model(s, generation['connection_profile_id'], 'Workspace chat', ['chat'])
    assert make_default(s, workspace, 'chat').status_code == 200
    current = s.api.get('/api/datasets/'+d['id']+'/models').json()
    payload = {k: current[k] for k in ('mappings', 'default_extraction_model_id')} | {'default_chat_model_id': None}
    saved = s.api.put('/api/datasets/'+d['id']+'/models', json=payload)
    assert saved.status_code == 200 and saved.json()['models_complete'], saved.text
    c = conversation(s, d, [doc['id']])
    assert message(s, c).json()['message']['model_selection']['model_id'] == workspace['id']
    override = s.api.put('/api/datasets/'+d['id']+'/models', json=payload | {'default_chat_model_id': generation['id']})
    assert override.status_code == 200
    assert message(s, c).json()['message']['model_selection']['model_id'] == generation['id']
    # Datasets never choose an embedding model.
    other = model(s, embedding_of(d)['connection_profile_id'], 'Other embeddings', ['embedding'])
    refused = s.api.put('/api/datasets/'+d['id']+'/models', json=payload | {'embedding_model_id': other['id'], 'acknowledge_reindex': True})
    assert refused.status_code == 400 and 'overall Default embedding' in refused.text


def test_embedding_change_requires_confirmation_deletes_now_and_reports_progress(system, monkeypatch):
    s = system; d = dataset(s); docs = [upload(s, d)['documents'][0] for _ in range(2)]
    old = knowledge.sync(s.owner, d['id'])[0]['knowledge_collection']
    distinct_space(monkeypatch)
    replacement = model(s, embedding_of(d)['connection_profile_id'], 'Rebuilt embeddings', ['embedding'])
    impact = s.api.get('/api/workspace/defaults').json()['impact']
    assert impact['documents'] == 2 and impact['knowledge_items'] > 0
    refused = make_default(s, replacement)
    assert refused.status_code == 409 and 'I understand the knowledge index will be deleted and rebuilt' in refused.text
    assert knowledge_catalog.names() == [old]
    assert all(s.api.get('/api/documents/'+doc['id']).json()['status'] == 'ready' for doc in docs)
    accepted = make_default(s, replacement, acknowledge_index_rebuild=True)
    assert accepted.status_code == 200, accepted.text
    status = accepted.json()['index']
    assert status['state'] == 'building' and status['total'] == 2 and status['indexed'] == 0 and 'still building' in status['message']
    # The old collection is deleted at once, before any reindexing.
    assert old not in knowledge_catalog.names() and knowledge.index_status()['building']
    real = knowledge.publish_document; failed = []
    def flaky(document_id, *args, **kwargs):
        if not failed:
            failed.append(document_id); raise providers.ProviderError('Embedding service unavailable')
        return real(document_id, *args, **kwargs)
    monkeypatch.setattr(knowledge, 'publish_document', flaky)
    assert worker.run_once() and worker.run_once()
    status = s.api.get('/api/workspace/knowledge-index').json()
    assert status['state'] == 'attention' and status['indexed'] == 1 and status['failed'] == 1
    assert status['failures'][0]['document_id'] == failed[0]
    retried = post(s, '/api/workspace/knowledge-index/retry', {})['index']
    assert retried['state'] == 'building' and retried['pending'] == 1
    assert worker.run_once()
    status = s.api.get('/api/workspace/knowledge-index').json()
    assert status['state'] == 'ready' and status['indexed'] == 2 and status['failed'] == 0
    knowledge.sync(s.owner, d['id'])
    active = workspace_defaults.active_collection()
    assert active != old and knowledge_catalog.names() == [active]
    assert knowledge.health()['orphan_rows'] == 0 and knowledge.health()['collections'] == 1


def test_chat_reads_only_reindexed_documents_while_the_index_builds(system, monkeypatch):
    s = system; d = dataset(s); first = upload(s, d)['documents'][0]; second = upload(s, d)['documents'][0]
    knowledge.sync(s.owner, d['id']); distinct_space(monkeypatch)
    replacement = model(s, embedding_of(d)['connection_profile_id'], 'Rebuilt embeddings', ['embedding'])
    assert make_default(s, replacement, acknowledge_index_rebuild=True).status_code == 200
    assert worker.run_once()  # Only the first document is reindexed so far.
    knowledge.sync(s.owner, d['id'])
    view = PublishedKnowledge(s.owner, d['id'])
    assert view.index_building and 'still building' in index_notice(view)
    chunks = view.candidate_ids(['document_chunk'])
    assert chunks and {view.manifest['points'][id]['document_id'] for id in chunks} == {first['id']}
    assert worker.run_once()
    knowledge.sync(s.owner, d['id'])
    view = PublishedKnowledge(s.owner, d['id'])
    assert not view.index_building and index_notice(view) is None
    assert {view.manifest['points'][id]['document_id'] for id in view.candidate_ids(['document_chunk'])} == {first['id'], second['id']}


def test_extraction_and_document_search_read_the_unified_index(system, monkeypatch):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    # Embed once: no legacy per-document chunk index is written.
    with pytest.raises(FileNotFoundError): core.store.get('vectors/'+doc['id']+'.json')
    monkeypatch.setattr(providers, '_legacy_retrieve', lambda *a, **k: pytest.fail('The legacy chunk index was read.'))
    real = knowledge.retrieve_chunks; seen = []
    def spy(query, documents, limit):
        hits = real(query, documents, limit); seen.append(hits); return hits
    monkeypatch.setattr(knowledge, 'retrieve_chunks', spy)
    extraction = post(s, '/api/extractions', {'dataset_id': d['id'], 'document_ids': [doc['id']], 'template_id': template(s)['id']})
    assert worker.run_once()
    assert s.api.get('/api/extractions/'+extraction['id']).json()['status'] == 'ready'
    active = workspace_defaults.active_collection()
    chunks = {c['id']: c['text'] for c in core.store.json('documents/'+doc['id']+'/chunks.json')['chunks']}
    assert seen and all(hit['knowledge_collection'] == active and chunks[hit['chunk_id']] == hit['text'] for batch in seen for hit in batch)
    found = len(seen)
    answer = message(s, conversation(s, d, [doc['id']]))
    assert answer.status_code == 200 and answer.json()['message']['citations']
    assert len(seen) > found


def test_orphan_collections_are_reported_and_removed(system):
    s = system; d = dataset(s); upload(s, d)
    active = knowledge.sync(s.owner, d['id'])[0]['knowledge_collection']
    orphan = 'lapi_knowledge_' + 'f'*20
    knowledge_catalog.apply(orphan, [('x', {'stamp': 's', 'ids': ['p1']}, {'p1': {'source_type': 'dataset', 'entity_id': 'x', 'text': 'Orphan'}}, None)])
    core.local_store.put_json('knowledge/lapi_knowledge_'+'e'*20+'/manifest.json', {'entities': {}, 'points': {}})
    health = knowledge.health()
    assert health['alert'] and health['orphan_rows'] == 1 and orphan in health['orphan_collections']
    assert s.api.get('/ready').json()['knowledge']['orphan_rows'] == 1
    removed = post(s, '/api/workspace/knowledge-index/remove-orphans')
    assert removed['active_collection'] == active and orphan in removed['collections']
    assert knowledge_catalog.names() == [active]
    assert not list(core.local_store.path('knowledge/marker').parent.glob('*/manifest.json'))
    health = knowledge.health()
    assert health['orphan_rows'] == 0 and not health['alert']


def test_no_code_path_creates_a_second_active_collection(system):
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    active = knowledge.sync(s.owner, d['id'])[0]['knowledge_collection']
    other = 'lapi_knowledge_' + '1'*20
    with pytest.raises(HTTPException) as error: knowledge.claim(other)
    assert error.value.status_code == 409
    # Simulate another embedding space becoming active behind the scenes.
    workspace_defaults._write(active_collection=other)
    refused = s.api.post('/api/documents/'+doc['id']+'/reindex', json={})
    assert refused.status_code == 409 and 'second active collection' in refused.text
    with pytest.raises(HTTPException): knowledge.sync(s.owner, d['id'])
    with pytest.raises(HTTPException): PublishedKnowledge(s.owner, d['id'])
    assert knowledge_catalog.names() == [active]


def test_legacy_chunk_index_parity_behind_the_flag(system, monkeypatch):
    """Parity check for retiring providers.put_vectors: same chunks either way."""
    monkeypatch.setenv('LAPI_LEGACY_CHUNK_INDEX', 'true')
    s = system; d = dataset(s); doc = upload(s, d)['documents'][0]
    assert core.store.json('vectors/'+doc['id']+'.json')['ids']
    record = routing.owned(doc['id'], s.owner, 'document')
    snapshot = core.store.json('documents/'+doc['id']+'/index-execution.json')
    with core.execution_context(snapshot):
        legacy = providers._legacy_retrieve('Who is the owner?', record.owner, [record], 5)
        unified = knowledge.retrieve_chunks('Who is the owner?', [record], 5)
    assert legacy and {h['chunk_id'] for h in legacy} == {h['chunk_id'] for h in unified}
    assert [h['text'] for h in sorted(legacy, key=lambda h: h['chunk_id'])] == [h['text'] for h in sorted(unified, key=lambda h: h['chunk_id'])]


def test_datasets_on_different_models_need_an_admin_choice_then_reindex_the_rest(system):
    s = system; a = dataset(s, 'A'); one = upload(s, a)['documents'][0]; b = dataset(s, 'B'); two = upload(s, b)['documents'][0]
    other = model(s, embedding_of(a)['connection_profile_id'], 'Legacy second embeddings', ['embedding'])
    # A workspace from before WS9: dataset B pinned another embedding model and no Default is saved.
    record = routing.owned(b['id'], s.owner, 'knowledge_base')
    with core.Session() as db: pinned = workspace_defaults.pin_embedding(db.get(core.Record, other['id']))
    routing.write_version(record, routing.dataset_config(record) | {'embedding_model_id': other['id'], 'embedding_snapshot': pinned})
    workspace_defaults._write(embedding_model_id=None, embedding_snapshot_json=None, active_collection=None)
    status = s.api.get('/api/workspace/knowledge-index').json()
    assert status['state'] == 'conflict' and 'different embedding models' in status['message']
    assert s.api.post('/api/documents/'+one['id']+'/reindex', json={}).status_code == 409
    chosen = make_default(s, embedding_of(a), acknowledge_index_rebuild=True)
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()['index']['total'] == 1  # Only the other dataset is reindexed.
    assert s.api.get('/api/documents/'+one['id']).json()['status'] == 'ready'
    assert s.api.get('/api/documents/'+two['id']).json()['status'] == 'queued'
    assert worker.run_once()
    for d in (a, b): knowledge.sync(s.owner, d['id'])
    assert s.api.get('/api/workspace/knowledge-index').json()['state'] == 'ready'
    assert knowledge_catalog.names() == [workspace_defaults.active_collection()]
