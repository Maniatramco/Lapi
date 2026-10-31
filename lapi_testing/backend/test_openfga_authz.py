"""OpenFGA decides administrator and dataset access; the database stays the record and
rebuilds OpenFGA's in-memory store whenever it is empty. No answer means no access."""
import json
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from lapi_app import authz, main
from test_dataset_models import system, dataset
from test_user_management import accounts, login, OLD


class FakeOpenFGA:
    """The slice of the OpenFGA HTTP API Lapi uses, with its in-memory behaviour."""
    def __init__(self):
        self.stores, self.created, self.down, self.calls = {}, 0, False, []

    def restart(self):
        self.stores = {}

    @staticmethod
    def has(tuples, user, relation, obj):
        """Lapi's model: owner > editor > viewer on datasets, and grants to team#member."""
        if (user, relation, obj) in tuples or ('user:*', relation, obj) in tuples:
            return True
        teams = {o for u, r, o in tuples if u == user and r == 'member' and o.startswith('team:')}
        if any((team + '#member', relation, obj) in tuples for team in teams):
            return True
        stronger = {'viewer': 'editor', 'editor': 'owner'}.get(relation)
        return bool(stronger and obj.startswith('dataset:') and FakeOpenFGA.has(tuples, user, stronger, obj))

    def tuples(self):
        return set().union(*(store['tuples'] for store in self.stores.values())) if self.stores else set()

    def handle(self, request):
        if self.down:
            raise httpx.ConnectError('connection refused', request=request)
        path, body = request.url.path, json.loads(request.content) if request.content else {}
        self.calls.append(path.rsplit('/', 1)[-1])
        if path == '/stores':
            if request.method == 'GET':
                return httpx.Response(200, json={'stores': [{'id': id, 'name': s['name'], 'created_at': s['created_at']} for id, s in self.stores.items()], 'continuation_token': ''})
            self.created += 1
            id = 'store%02d' % self.created
            self.stores[id] = {'name': body['name'], 'created_at': '2026-10-27T00:00:%02dZ' % self.created, 'models': [], 'tuples': set()}
            return httpx.Response(201, json={'id': id, 'name': body['name']})
        _, _, id, operation = path.split('/')
        store = self.stores.get(id)
        if store is None:
            return httpx.Response(404, json={'code': 'store_id_not_found', 'message': 'store not found'})
        if operation == 'authorization-models':
            assert body['schema_version'] == '1.1'
            store['models'].append(body)
            return httpx.Response(201, json={'authorization_model_id': 'model%d' % len(store['models'])})
        if not store['models']:
            return httpx.Response(400, json={'code': 'latest_authorization_model_not_found'})
        key = lambda k: (k['user'], k['relation'], k['object'])
        if operation == 'write':
            writes = [key(k) for k in body.get('writes', {}).get('tuple_keys', [])]
            deletes = [key(k) for k in body.get('deletes', {}).get('tuple_keys', [])]
            assert len(writes) + len(deletes) <= 100
            if any(t in store['tuples'] for t in writes) or any(t not in store['tuples'] for t in deletes):
                return httpx.Response(400, json={'code': 'write_failed_due_to_invalid_input'})
            store['tuples'] = (store['tuples'] | set(writes)) - set(deletes)
            return httpx.Response(200, json={})
        if operation == 'read':
            wanted = body.get('tuple_key') or {}
            rows = sorted(t for t in store['tuples'] if (not wanted.get('user') or t[0] == wanted['user'])
                          and (not wanted.get('relation') or t[1] == wanted['relation'])
                          and (not wanted.get('object') or (t[2].startswith(wanted['object']) if wanted['object'].endswith(':') else t[2] == wanted['object'])))
            start = int(body.get('continuation_token') or 0)
            page = rows[start:start + body['page_size']]
            token = str(start + len(page)) if start + len(page) < len(rows) else ''
            return httpx.Response(200, json={'tuples': [{'key': dict(zip(('user', 'relation', 'object'), t))} for t in page], 'continuation_token': token})
        if operation == 'check':
            k = body['tuple_key']
            return httpx.Response(200, json={'allowed': self.has(store['tuples'], k['user'], k['relation'], k['object'])})
        if operation == 'list-objects':
            objects = {o for _, _, o in store['tuples'] if o.startswith(body['type'] + ':')}
            return httpx.Response(200, json={'objects': sorted(o for o in objects if self.has(store['tuples'], body['user'], body['relation'], o))})
        return httpx.Response(404, json={'code': 'undefined_endpoint'})


@pytest.fixture
def fga(accounts, monkeypatch):
    fake = FakeOpenFGA()
    monkeypatch.setenv('LAPI_OPENFGA_URL', 'http://openfga.test')
    monkeypatch.setattr(authz, '_client', lambda: httpx.Client(transport=httpx.MockTransport(fake.handle)))
    monkeypatch.setitem(authz._state, 'store', None)
    return fake


def test_access_is_decided_by_openfga_and_kept_in_step_with_the_database(accounts, fga):
    client = accounts
    assert login(client)['user']['is_admin']
    assert ('user:administrator', 'administrator', 'lapi:workspace') in fga.tuples()
    d = dataset(SimpleNamespace(api=client))
    other = dataset(SimpleNamespace(api=client), name='Other')
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']]}).status_code == 200
    assert ('user:colleague', 'viewer', 'dataset:' + d['id']) in fga.tuples()
    with TestClient(main.app) as colleague:
        login(colleague, 'Colleague')
        assert [row['id'] for row in colleague.get('/api/datasets').json()] == [d['id']]
        assert colleague.get('/api/datasets/' + other['id']).status_code in (403, 404)
        assert colleague.get('/api/users').status_code == 403
        assert 'check' in fga.calls and 'list-objects' in fga.calls
        # OpenFGA, not the database row, is what decides.
        for store in fga.stores.values():
            store['tuples'].discard(('user:colleague', 'viewer', 'dataset:' + d['id']))
        assert colleague.get('/api/datasets').json() == []
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [other['id']]}).status_code == 200
    assert {t for t in fga.tuples() if t[0] == 'user:colleague'} == {('user:colleague', 'viewer', 'dataset:' + other['id'])}


def test_role_change_moves_the_administrator_tuple(accounts, fga):
    client = accounts
    login(client)
    result = client.patch('/api/users/colleague/role', json={'role': 'administrator', 'current_password': OLD})
    assert result.status_code == 200
    assert ('user:colleague', 'administrator', 'lapi:workspace') in fga.tuples()
    result = client.patch('/api/users/colleague/role', json={'role': 'user', 'current_password': OLD})
    assert result.status_code == 200
    assert ('user:colleague', 'administrator', 'lapi:workspace') not in fga.tuples()


def test_an_openfga_restart_is_rebuilt_from_the_database(accounts, fga):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']]}).status_code == 200
    before = fga.tuples()
    fga.restart()  # Memory store: everything is gone, including the store itself.
    assert client.get('/api/users').status_code == 200
    assert fga.tuples() == before and len(fga.stores) == 1


def test_containers_starting_together_share_the_oldest_store_and_stale_tuples_are_removed(accounts, fga):
    authz.prepare()
    first = next(iter(fga.stores))
    fga.stores['store99'] = {'name': 'lapi', 'created_at': '2026-10-28T00:00:00Z', 'models': [authz.MODEL], 'tuples': set()}
    fga.stores[first]['tuples'].add(('user:gone', 'viewer', 'dataset:deleted'))
    authz.prepare()
    assert ('user:gone', 'viewer', 'dataset:deleted') not in fga.stores[first]['tuples']
    assert ('user:administrator', 'administrator', 'lapi:workspace') in fga.stores[first]['tuples']
    assert not fga.stores['store99']['tuples']


def test_no_answer_from_openfga_refuses_access(accounts, fga):
    client = accounts
    login(client)
    fga.down = True
    for result in (client.get('/api/users'), client.get('/api/datasets')):
        assert result.status_code == 503
        assert result.json()['detail'] == 'The permission service is unavailable. Try again in a minute.'
    fga.down = False
    assert client.get('/api/users').status_code == 200


def test_many_tuples_are_written_in_batches_of_100(accounts, fga, monkeypatch):
    rows = {('user:u%03d' % i, 'viewer', 'dataset:d') for i in range(250)}
    monkeypatch.setattr(authz, '_desired', lambda user_id=None: rows)
    authz.prepare()
    assert fga.tuples() == rows


def test_access_map_shows_database_grants_beside_openfga_answers(accounts, fga):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    other = dataset(SimpleNamespace(api=client), name='Other')
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']]}).status_code == 200
    result = client.get('/api/access-map').json()
    assert {row['id'] for row in result['datasets']} == {d['id'], other['id']}
    users = {row['id']: row for row in result['users']}
    assert users['colleague']['dataset_ids'] == [d['id']] and not users['colleague']['is_admin']
    assert users['colleague']['openfga'] == {'administrator': False, 'auditor': False, 'contributor': False, 'levels': {d['id']: 'viewer'}, 'dataset_ids': [d['id']], 'in_step': True}
    assert users['administrator']['openfga']['administrator'] and users['administrator']['openfga']['in_step']
    assert result['openfga'] == {'enabled': True, 'reachable': True, 'differences': 0}
    # A tuple OpenFGA lost shows as a difference until Lapi rebuilds it.
    for store in fga.stores.values():
        store['tuples'].discard(('user:colleague', 'viewer', 'dataset:' + d['id']))
    result = client.get('/api/access-map').json()
    colleague = next(row for row in result['users'] if row['id'] == 'colleague')
    assert colleague['openfga'] == {'administrator': False, 'auditor': False, 'contributor': False, 'levels': {}, 'dataset_ids': [], 'in_step': False}
    assert result['openfga']['differences'] == 1
    with TestClient(main.app) as other_client:
        login(other_client, 'Colleague')
        assert other_client.get('/api/access-map').status_code == 403


def test_access_map_without_openfga_lists_database_grants_only(accounts):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']]}).status_code == 200
    result = client.get('/api/access-map').json()
    assert result['openfga'] == {'enabled': False, 'reachable': None, 'differences': 0}
    colleague = next(row for row in result['users'] if row['id'] == 'colleague')
    assert colleague['dataset_ids'] == [d['id']] and 'openfga' not in colleague


def test_levels_and_team_grants_are_answered_by_openfga(accounts, fga):
    client = accounts
    login(client)
    d = dataset(SimpleNamespace(api=client))
    team = client.post('/api/teams', json={'name': 'Finance'}).json()['id']
    assert client.put('/api/teams/' + team + '/members', json={'user_ids': ['colleague']}).status_code == 200
    assert client.put('/api/teams/' + team + '/datasets', json={'grants': {d['id']: 'editor'}}).status_code == 200
    assert ('user:colleague', 'member', 'team:' + team) in fga.tuples()
    assert ('team:' + team + '#member', 'editor', 'dataset:' + d['id']) in fga.tuples()
    with TestClient(main.app) as colleague:
        login(colleague, 'Colleague')
        assert [(row['id'], row['my_access']) for row in colleague.get('/api/datasets').json()] == [(d['id'], 'editor')]
        # OpenFGA decides: dropping the team tuple removes access before the database changes.
        for store in fga.stores.values():
            store['tuples'].discard(('team:' + team + '#member', 'editor', 'dataset:' + d['id']))
        assert colleague.get('/api/datasets').json() == []
    assert client.put('/api/users/colleague/datasets', json={'dataset_ids': [d['id']], 'levels': {d['id']: 'owner'}}).status_code == 200
    assert ('user:colleague', 'owner', 'dataset:' + d['id']) in fga.tuples()
    mapped = {row['id']: row for row in client.get('/api/access-map').json()['users']}
    assert mapped['colleague']['openfga']['levels'] == {d['id']: 'owner'} and mapped['colleague']['openfga']['in_step']
    assert client.patch('/api/users/colleague/role', json={'role': 'auditor', 'current_password': OLD}).status_code == 200
    assert ('user:colleague', 'auditor', 'lapi:workspace') in fga.tuples()
    # Contributor (Keycloak lapi-contributor): OpenFGA answers the role; every dataset opens as Owner.
    from lapi_app import core, relational
    with core.Session.begin() as session:
        session.add(relational.WorkspaceContributor(user_id='colleague'))
    assert ('user:colleague', 'contributor', 'lapi:workspace') in fga.tuples()
    with core.Session.begin() as session:
        session.delete(session.get(relational.WorkspaceContributor, 'colleague'))
    assert ('user:colleague', 'contributor', 'lapi:workspace') not in fga.tuples()
