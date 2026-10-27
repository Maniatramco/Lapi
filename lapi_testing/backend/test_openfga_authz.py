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
            return httpx.Response(200, json={'allowed': key(body['tuple_key']) in store['tuples']})
        if operation == 'list-objects':
            return httpx.Response(200, json={'objects': [o for u, r, o in store['tuples'] if u == body['user'] and r == body['relation'] and o.startswith(body['type'] + ':')]})
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
