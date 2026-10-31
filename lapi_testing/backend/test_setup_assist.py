"""The set-up chat reads answers with the Default chat model when there is one, and tells the screen to use its rules otherwise."""
import pytest
from fastapi.testclient import TestClient
from jsonschema import ValidationError
from lapi_app import main, setup_assist
from test_dataset_models import system
from test_user_management import accounts, login


def test_without_a_default_chat_model_the_screen_uses_its_rules(accounts):
    admin = accounts; login(admin)
    reply = admin.post('/api/setup/interpret', json={'stage': 'name', 'answer': "hi its mnai"})
    assert reply.status_code == 200 and reply.json() == {'decision': 'rules'}
    assert admin.post('/api/setup/interpret', json={'stage': 'name', 'answer': ''}).status_code == 422
    assert admin.post('/api/setup/interpret', json={'stage': 'nope', 'answer': 'x'}).status_code == 422
    with TestClient(main.app) as nobody:
        assert nobody.post('/api/setup/interpret', json={'stage': 'name', 'answer': 'Mani'}).status_code == 401


def test_the_model_reply_is_read_strictly():
    assert setup_assist.parse('Sure! ```json\n{"decision": "answer", "name": "Mani"}\n```')['name'] == 'Mani'
    assert setup_assist.parse('{"decision": "yes"}') == {'decision': 'yes'}
    with pytest.raises(ValidationError):
        setup_assist.parse('{"decision": "maybe"}')
    with pytest.raises(ValidationError):
        setup_assist.parse('{"decision": "answer", "fields": [{"label": "Total"}]}')
