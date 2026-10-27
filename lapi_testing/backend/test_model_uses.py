"""One registered model can be used for Chat and Extraction; Embedding stays its own
registration (the form saves a second one for the same model)."""
from sqlalchemy import select as query
from lapi_app import core, relational
from test_dataset_models import system
from test_model_registration import body, register


def configs(model_id):
    with core.Session() as session:
        return sorted(row.category for row in session.scalars(query(relational.ModelConfig).where(
            relational.ModelConfig.model_id == model_id, relational.ModelConfig.enabled == True)))


def test_one_model_serves_chat_and_extraction(system):
    model = register(system, body('chat', 'openai-compatible', capabilities=['extraction', 'chat']))
    assert model['capabilities'] == ['chat', 'extraction']
    assert configs(model['id']) == ['chat', 'extraction']
    listed = next(m for m in system.api.get('/api/models').json() if m['id'] == model['id'])
    assert listed['capabilities'] == ['chat', 'extraction']


def test_embedding_is_registered_on_its_own(system):
    mixed = system.api.post('/api/model-registrations', json=body('chat', 'openai-compatible', capabilities=['chat', 'embedding']))
    assert mixed.status_code == 400 and 'Embedding is registered on its own' in mixed.json()['detail']
    outside = system.api.post('/api/model-registrations', json=body('chat', 'openai-compatible', capabilities=['extraction']))
    assert outside.status_code == 400
    embedding = register(system, body('embedding', 'openai-compatible', capabilities=['embedding']))
    assert embedding['capabilities'] == ['embedding']


def test_editing_adds_or_removes_a_use_but_never_crosses_into_embedding(system):
    model = register(system, body('chat', 'openai-compatible'))
    assert model['capabilities'] == ['chat']
    path = '/api/model-registrations/' + model['id']
    both = system.api.put(path, json=body('chat', 'openai-compatible', capabilities=['chat', 'extraction'], existing_model_id=model['id']))
    assert both.status_code == 200 and both.json()['capabilities'] == ['chat', 'extraction']
    assert configs(model['id']) == ['chat', 'extraction']
    # A client that sends no uses keeps the saved ones.
    kept = system.api.put(path, json=body('chat', 'openai-compatible', existing_model_id=model['id']))
    assert kept.status_code == 200 and kept.json()['capabilities'] == ['chat', 'extraction']
    narrowed = system.api.put(path, json=body('extraction', 'openai-compatible', capabilities=['extraction'], existing_model_id=model['id']))
    assert narrowed.status_code == 200 and narrowed.json()['capabilities'] == ['extraction']
    assert configs(model['id']) == ['extraction']
    crossed = system.api.put(path, json=body('embedding', 'openai-compatible', capabilities=['embedding'], existing_model_id=model['id']))
    assert crossed.status_code == 400
