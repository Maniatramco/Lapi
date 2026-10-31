"""Workspaces group collections; access stays on the collections and is never widened by placement."""
from fastapi.testclient import TestClient
from lapi_app import core, main, relational
from test_dataset_models import system
from test_user_management import accounts, login, OLD


def add_outsider():
    with core.Session.begin() as session:
        session.add(core.User(id='outsider', username='Outsider', password_hash=core.password_hash(OLD)))


def space(client, id):
    return next(w for w in client.get('/api/workspaces').json()['workspaces'] if w['id'] == id)


def test_team_members_reach_every_collection_and_lose_it_when_removed(accounts):
    add_outsider()
    with TestClient(main.app) as owner, TestClient(main.app) as outsider:
        login(owner, 'Colleague'); login(outsider, 'Outsider')
        team = owner.post('/api/workspaces', json={'name': 'Finance team'}).json()
        first = owner.post('/api/datasets', json={'name': 'Invoices', 'workspace_id': team['id'], 'collection_type': 'Finance'}).json()
        assert first['collection_type'] == 'Finance' and first['workspace_id'] == team['id']
        assert owner.get('/api/datasets/' + first['id']).status_code == 200
        assert outsider.get('/api/datasets/' + first['id']).status_code == 404
        assert outsider.post('/api/datasets', json={'name': 'Sneak', 'workspace_id': team['id']}).status_code == 404
        assert outsider.get('/api/workspaces/' + team['id'] + '/members').status_code == 403
        assert outsider.put('/api/workspaces/' + team['id'] + '/members', json={'people': {'outsider': 'owner'}, 'teams': {}}).status_code == 403
        people = owner.get('/api/workspaces/' + team['id'] + '/members').json()
        assert any(p['id'] == 'outsider' for p in people['directory'])
        assert owner.put('/api/workspaces/' + team['id'] + '/members', json={'people': {'outsider': 'viewer'}, 'teams': {}}).status_code == 200
        assert outsider.get('/api/datasets/' + first['id']).status_code == 200
        assert space(outsider, team['id'])['my_access'] == 'viewer'
        later = owner.post('/api/datasets', json={'name': 'Added later', 'workspace_id': team['id']}).json()
        assert outsider.get('/api/datasets/' + later['id']).status_code == 200  # New collections follow the members.
        assert outsider.post('/api/datasets', json={'name': 'As viewer', 'workspace_id': team['id']}).status_code == 403
        assert owner.put('/api/workspaces/' + team['id'] + '/members', json={'people': {'outsider': 'editor'}, 'teams': {}}).status_code == 200
        assert outsider.post('/api/datasets', json={'name': 'As editor', 'workspace_id': team['id']}).status_code == 200
        assert owner.put('/api/workspaces/' + team['id'] + '/members', json={'people': {'outsider': None}, 'teams': {}}).status_code == 200
        assert outsider.get('/api/datasets/' + first['id']).status_code == 404
        assert outsider.get('/api/datasets/' + later['id']).status_code == 404
        assert all(w['id'] != team['id'] for w in outsider.get('/api/workspaces').json()['workspaces'])


def test_existing_datasets_are_placed_without_widening_access(accounts):
    admin = accounts; login(admin); add_outsider()
    shared = admin.post('/api/datasets', json={'name': 'Shared one'}).json()
    private = admin.post('/api/datasets', json={'name': 'Private one'}).json()
    # As datasets from before workspaces: no workspace recorded.
    with core.Session() as session:
        records = [session.get(core.Record, shared['id']), session.get(core.Record, private['id'])]
    for record in records:
        data = core.store.json(record.ref); data.pop('workspace_id'); core.store.put_json(record.ref, data)
    with core.Session.begin() as session:
        session.add(relational.UserDataset(user_id='colleague', dataset_id=shared['id'], access_level='viewer'))
    with TestClient(main.app) as person, TestClient(main.app) as outsider:
        login(person, 'Colleague'); login(outsider, 'Outsider')
        found = person.get('/api/workspaces').json()['workspaces']
        organization = next(w for w in found if w['organization'])
        assert organization['my_access'] == 'viewer' and organization['collection_count'] == 1
        with core.Session.begin() as session:
            session.get(core.Record, organization['id']).owner = 'colleague'
        found = person.get('/api/workspaces').json()['workspaces']
        assert next(w for w in found if w['organization'])['my_access'] == 'viewer'  # Never owner by accident.
        assert [d['id'] for d in person.get('/api/datasets').json()] == [shared['id']]
        assert person.get('/api/datasets/' + private['id']).status_code == 404
        assert all(not w['organization'] for w in outsider.get('/api/workspaces').json()['workspaces'])
        assert outsider.get('/api/datasets/' + shared['id']).status_code == 404
    assert core.store.json(records[1].ref)['workspace_id'] != organization['id']  # Unshared: the owner's own.


def test_personal_workspaces_stay_private_from_every_role(accounts):
    admin = accounts; login(admin); add_outsider()
    with core.Session.begin() as session:
        session.add(relational.WorkspaceContributor(user_id='colleague'))
    with TestClient(main.app) as person, TestClient(main.app) as outsider:
        login(person, 'Colleague'); login(outsider, 'Outsider')
        private = person.post('/api/datasets', json={'name': 'My own'}).json()
        for other in (admin, outsider):
            assert other.get('/api/datasets/' + private['id']).status_code == 404
            assert private['id'] not in [d['id'] for d in other.get('/api/datasets').json()]
            assert all(w['id'] != private['workspace_id'] for w in other.get('/api/workspaces').json()['workspaces'])
        assert person.get('/api/datasets/' + private['id']).status_code == 200
        # An administrator's collection is just as private from a Contributor.
        theirs = admin.post('/api/datasets', json={'name': 'Admin only'}).json()
        assert person.get('/api/datasets/' + theirs['id']).status_code == 404
        assert person.request('DELETE', '/api/datasets/' + theirs['id'], json={'confirmation': 'Admin only', 'expected_version': theirs['version']}).status_code in (403, 404)


def test_the_name_people_give_names_their_workspace_and_greets_them(accounts):
    admin = accounts; login(admin); add_outsider()
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        before = person.get('/api/workspaces').json()['workspaces']
        assert next(w for w in before if w['audience'] == 'personal')['name'] == "Colleague's workspace"
        assert person.get('/api/auth/me').json()['user']['display_name'] == ''
        saved = person.put('/api/me/preferences', json={'goals': [], 'sources': [], 'completed': False, 'dismissed_next_steps': False, 'name': '  Mani  Tram '}).json()
        assert saved['name'] == 'Mani Tram'
        assert person.get('/api/auth/me').json()['user']['display_name'] == 'Mani Tram'
        after = person.get('/api/workspaces').json()['workspaces']
        assert next(w for w in after if w['audience'] == 'personal')['name'] == "Mani Tram's workspace"
        # Saving the set-up answers without a name keeps it.
        kept = person.put('/api/me/preferences', json={'goals': ['ask'], 'sources': [], 'completed': True, 'dismissed_next_steps': False}).json()
        assert kept['name'] == 'Mani Tram' and kept['goals'] == ['ask']
