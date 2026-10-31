"""Screens per person and device, decided by OpenFGA and managed in the Access map (screens.py)."""
from types import SimpleNamespace
from fastapi.testclient import TestClient
from lapi_app import core, main, relational, screens
from test_dataset_models import system, dataset
from test_user_management import accounts, login, OLD
from test_openfga_authz import fga


def mine(client, device):
    r = client.get('/api/me/screens', params={'device': device})
    assert r.status_code == 200, r.text
    return r.json()


def test_defaults_computers_see_everything_phones_only_the_core_and_admins_always_all(accounts):
    admin = accounts
    login(admin)
    assert mine(admin, 'phone')['screens'] == screens.IDS and mine(admin, 'phone')['administrator'] is True
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        computer = mine(person, 'computer')
        assert computer['screens'] == screens.IDS and 'Review' in computer['views'] and computer['core'] == ['home', 'agent', 'quick-start']
        phone = mine(person, 'phone')
        assert phone['screens'] == [] and phone['views'] == [] and phone['administrator'] is False
        assert person.get('/api/screens').status_code == 403


def test_grants_for_everyone_a_team_or_a_person_apply_at_once_and_reach_openfga(accounts, fga):
    admin = accounts
    login(admin)
    team = admin.post('/api/teams', json={'name': 'Finance'}).json()
    assert admin.put('/api/teams/' + team['id'] + '/members', json={'user_ids': ['colleague']}).status_code == 200
    grid = admin.get('/api/screens').json()
    assert {g['screen'] for g in grid['grants']} == set(screens.IDS) and all(g['default'] for g in grid['grants'])
    assert ('user:*', 'enabled', 'screen:review') in fga.tuples() and ('user:*', 'enabled', 'screen:review-phone') not in fga.tuples()
    saved = admin.put('/api/screens', json={'grants': [
        {'screen': 'review', 'device': 'phone', 'teams': [team['id']]},
        {'screen': 'datasets', 'device': 'phone', 'users': ['colleague']},
        {'screen': 'prompts', 'device': 'computer'}]})  # explicitly off
    assert saved.status_code == 200, saved.text
    assert ('team:' + team['id'] + '#member', 'enabled', 'screen:review-phone') in fga.tuples()
    assert ('user:colleague', 'enabled', 'screen:datasets-phone') in fga.tuples()
    assert ('user:*', 'enabled', 'screen:prompts') not in fga.tuples()
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        assert mine(person, 'phone')['screens'] == ['datasets', 'review']
        assert 'prompts' not in mine(person, 'computer')['screens'] and 'datasets' in mine(person, 'computer')['screens']
    assert admin.put('/api/screens', json={'grants': [{'screen': 'nope', 'device': 'phone', 'everyone': True}]}).status_code == 422
    assert admin.put('/api/screens', json={'grants': [{'screen': 'review', 'device': 'phone', 'teams': ['missing']}]}).status_code == 422


def test_presets_switch_between_agent_only_phones_and_everything(accounts):
    admin = accounts
    login(admin)
    assert admin.post('/api/screens/preset', json={'preset': 'everything'}).status_code == 200
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        assert mine(person, 'phone')['screens'] == screens.IDS
    assert admin.post('/api/screens/preset', json={'preset': 'agent-only-phone'}).status_code == 200
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        assert mine(person, 'phone')['screens'] == [] and mine(person, 'computer')['screens'] == screens.IDS
    assert admin.post('/api/screens/preset', json={'preset': 'other'}).status_code == 422
