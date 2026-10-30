"""Set-up answers ("Let's set you up"): stored per person on the server, isolated, authenticated and validated."""
import hashlib
from fastapi.testclient import TestClient
from lapi_app import core, main
from test_user_management import accounts, login  # noqa: F401  (pytest fixture)
from test_dataset_models import system  # noqa: F401  (pytest fixture)

BLANK = {'goals': [], 'sources': [], 'completed': False, 'dismissed_next_steps': False, 'name': ''}
ANSWERS = {'goals': ['extract', 'ask'], 'sources': ['google_drive', 'files'], 'completed': True, 'dismissed_next_steps': False}


def test_anonymous_requests_are_refused(accounts):
    client = accounts
    assert client.get('/api/me/preferences').status_code == 401
    assert client.put('/api/me/preferences', json=ANSWERS).status_code == 401


def test_answers_are_blank_until_saved_then_remembered_on_another_browser(accounts):
    client = accounts
    me = login(client, 'Colleague')
    assert client.get('/api/me/preferences').json() == BLANK
    saved = client.put('/api/me/preferences', json=ANSWERS)
    assert saved.status_code == 200
    # Choices come back once each, in a fixed order.
    assert saved.json() == {'goals': ['ask', 'extract'], 'sources': ['files', 'google_drive'], 'completed': True, 'dismissed_next_steps': False, 'name': ''}
    assert client.get('/api/me/preferences').json() == saved.json()
    stored = core.local_store.json(_key(me['user']['id']))
    assert stored['goals'] == ['ask', 'extract'] and stored['completed'] is True
    with TestClient(main.app) as other:
        login(other, 'Colleague')
        assert other.get('/api/me/preferences').json()['sources'] == ['files', 'google_drive']


def test_answers_are_isolated_between_people(accounts):
    client = accounts
    login(client, 'Colleague')
    assert client.put('/api/me/preferences', json=ANSWERS).status_code == 200
    with TestClient(main.app) as other:
        login(other, 'Admin')
        assert other.get('/api/me/preferences').json() == BLANK
        assert other.put('/api/me/preferences', json={**BLANK, 'dismissed_next_steps': True}).status_code == 200
    assert client.get('/api/me/preferences').json()['dismissed_next_steps'] is False


def test_unknown_values_and_fields_are_rejected(accounts):
    client = accounts
    login(client, 'Colleague')
    for bad in (
        {**ANSWERS, 'goals': ['hack']},
        {**ANSWERS, 'sources': ['dropbox']},
        {**ANSWERS, 'sources': 'files'},
        {**ANSWERS, 'completed': 'yes'},
        {**ANSWERS, 'completed': 1},
        {**ANSWERS, 'note': 'free text'},
        {**ANSWERS, 'goals': ['ask'] * 5},
        [ANSWERS],
    ):
        assert client.put('/api/me/preferences', json=bad).status_code == 422, bad
    assert client.get('/api/me/preferences').json() == BLANK


def test_unreadable_record_reads_as_blank(accounts):
    client = accounts
    me = login(client, 'Colleague')
    client.put('/api/me/preferences', json=ANSWERS)
    core.local_store.put_json(_key(me['user']['id']), {'goals': ['nope'], 'sources': 7})
    assert client.get('/api/me/preferences').json() == BLANK


def test_put_requires_csrf_token(accounts):
    client = accounts
    login(client, 'Colleague')
    del client.headers['X-CSRF-Token']
    assert client.put('/api/me/preferences', json=ANSWERS).status_code == 403


def _key(user_id):
    return f'preferences/{hashlib.sha256(user_id.encode()).hexdigest()}.json'
