"""The 1-minute tour flag: stored per user on the server, isolated, authenticated and validated."""
from fastapi.testclient import TestClient
from lapi_app import core, main, walkthrough
from test_user_management import accounts, login  # noqa: F401  (pytest fixture)
from test_dataset_models import system  # noqa: F401  (pytest fixture)


def test_anonymous_requests_are_refused(accounts):
    client=accounts
    assert client.get('/api/me/walkthrough').status_code==401
    assert client.post('/api/me/walkthrough',json={'version':1}).status_code==401


def test_tour_is_unseen_until_marked_then_remembered(accounts):
    client=accounts
    login(client,'Colleague')
    assert client.get('/api/me/walkthrough').json()=={'seen':False,'version':walkthrough.TOUR_VERSION}
    result=client.post('/api/me/walkthrough',json={'version':walkthrough.TOUR_VERSION})
    assert result.status_code==200 and result.json()['seen'] is True
    assert client.get('/api/me/walkthrough').json()['seen'] is True
    stored=core.local_store.json('walkthrough/colleague.json')
    assert stored['version']==walkthrough.TOUR_VERSION
    # A second browser for the same account does not replay the tour.
    with TestClient(main.app) as other:
        login(other,'Colleague')
        assert other.get('/api/me/walkthrough').json()['seen'] is True


def test_seen_flag_is_isolated_between_users(accounts):
    client=accounts
    login(client,'Colleague')
    assert client.post('/api/me/walkthrough',json={'version':1}).status_code==200
    with TestClient(main.app) as other:
        login(other,'Admin')
        assert other.get('/api/me/walkthrough').json()['seen'] is False


def test_new_tour_version_shows_again(accounts,monkeypatch):
    client=accounts
    login(client,'Colleague')
    client.post('/api/me/walkthrough',json={'version':1})
    monkeypatch.setattr(walkthrough,'TOUR_VERSION',2)
    assert client.get('/api/me/walkthrough').json()=={'seen':False,'version':2}
    assert client.post('/api/me/walkthrough',json={'version':2}).json()['seen'] is True


def test_bad_bodies_are_rejected(accounts):
    client=accounts
    login(client,'Colleague')
    for bad in ({},{'version':'one'},{'version':0},{'version':1,'extra':True},[1]):
        assert client.post('/api/me/walkthrough',json=bad).status_code==422
    assert client.get('/api/me/walkthrough').json()['seen'] is False


def test_post_requires_csrf_token(accounts):
    client=accounts
    login(client,'Colleague')
    del client.headers['X-CSRF-Token']
    assert client.post('/api/me/walkthrough',json={'version':1}).status_code==403


def test_agent_training_is_shown_once_per_person(accounts):
    client=accounts
    login(client,'Colleague')
    assert client.get('/api/me/agent-training').json()=={'seen':False,'version':walkthrough.TRAINING_VERSION}
    assert client.post('/api/me/agent-training',json={'version':walkthrough.TRAINING_VERSION}).json()['seen'] is True
    assert client.get('/api/me/agent-training').json()['seen'] is True
    assert client.get('/api/me/walkthrough').json()['seen'] is False  # separate from the tour
