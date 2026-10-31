"""Every API route has a policy, and Viewer / Editor / Owner / Auditor / teams are enforced."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select
from lapi_app import core, main, relational, route_policy, teams
from test_dataset_models import system, dataset
from test_user_management import accounts, login, OLD


def api_routes(routes):
    for route in routes:
        if type(route).__name__ == '_IncludedRouter':
            yield from api_routes(route.original_router.routes)
        elif isinstance(route, APIRoute) and route.path.startswith('/api'):
            for method in route.methods - {'HEAD'}:
                yield method, route.path


def test_every_api_route_has_a_policy_and_no_policy_is_stale():
    live = set(api_routes(main.app.routes))
    missing = sorted(live - route_policy.POLICY.keys())
    assert not missing, 'Add these routes to route_policy.POLICY: %s' % missing
    stale = sorted(route_policy.POLICY.keys() - live)
    assert not stale, 'Remove these from route_policy.POLICY: %s' % stale
    assert set(route_policy.POLICY.values()) <= route_policy.LEVELS


def test_an_unclassified_route_is_refused():
    with pytest.raises(HTTPException) as refused:
        route_policy.check('POST', '/api/not-classified', 'administrator')
    assert refused.value.status_code == 403


def grant(client, user, d, level):
    result = client.put('/api/users/' + user + '/datasets', json={'dataset_ids': [d['id']], 'levels': {d['id']: level}})
    assert result.status_code == 200, result.text
    assert result.json()['levels'] == {d['id']: level}


def upload(client, d):
    return client.post('/api/documents/upload', files={'files': ('note.txt', b'Payment terms are 30 days.', 'text/plain')},
                       data={'dataset_id': d['id'], 'allow_external': 'true'})


def test_viewer_reads_editor_changes_owner_manages(accounts):
    admin = accounts
    login(admin)
    d = dataset(SimpleNamespace(api=admin))
    uploaded = upload(admin, d)
    assert uploaded.status_code == 200, uploaded.text
    document_id = uploaded.json()['documents'][0]['id']
    grant(admin, 'colleague', d, 'viewer')
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        listed = person.get('/api/datasets').json()
        assert [(row['id'], row['my_access']) for row in listed] == [(d['id'], 'viewer')]
        assert person.get('/api/documents/' + document_id).status_code == 200
        refused = upload(person, d)
        assert refused.status_code == 403 and 'Editor access' in refused.json()['detail']
        assert person.delete('/api/documents/' + document_id).status_code == 403
        assert person.post('/api/documents/' + document_id + '/reindex', json={'allow_external': True}).status_code == 403
        assert person.post('/api/templates', json={'name': 'Terms', 'schema': {'type': 'object', 'properties': {'terms': {'type': 'string'}}}, 'dataset_id': d['id']}).status_code == 403
        assert person.patch('/api/datasets/' + d['id'], json={'name': 'Renamed', 'description': ''}).status_code == 403
        assert person.get('/api/datasets/' + d['id'] + '/members').status_code == 403

        grant(admin, 'colleague', d, 'editor')
        assert upload(person, d).status_code == 200
        assert person.patch('/api/datasets/' + d['id'], json={'name': 'Renamed', 'description': ''}).status_code == 403

        grant(admin, 'colleague', d, 'owner')
        renamed = person.patch('/api/datasets/' + d['id'], json={'name': 'Renamed', 'description': ''})
        assert renamed.status_code == 200 and renamed.json()['name'] == 'Renamed'
        members = person.get('/api/datasets/' + d['id'] + '/members').json()
        assert {'user_id': 'colleague', 'level': 'owner'} in members['people']
        assert 'Colleague' in [row['username'] for row in members['directory']]
        # Owners are not administrators: model mappings, deletion and people stay admin-only.
        assert person.put('/api/datasets/' + d['id'] + '/models', json={'mappings': []}).status_code == 403
        assert person.get('/api/users').status_code == 403
        assert person.put('/api/datasets/' + d['id'] + '/members', json={'people': {'administrator': 'viewer'}}).status_code == 200


def test_owner_shares_with_a_team_and_auditor_reads_but_cannot_change(accounts):
    admin = accounts
    login(admin)
    d = dataset(SimpleNamespace(api=admin))
    other = dataset(SimpleNamespace(api=admin), name='Other')
    with core.Session.begin() as session:
        session.add(core.User(id='third', username='Third', password_hash=core.password_hash(OLD)))
    team = admin.post('/api/teams', json={'name': 'Finance'})
    assert team.status_code == 200, team.text
    team_id = team.json()['id']
    assert admin.post('/api/teams', json={'name': ' Finance '}).status_code == 409
    assert admin.put('/api/teams/' + team_id + '/members', json={'user_ids': ['third']}).status_code == 200
    grant(admin, 'colleague', d, 'owner')
    with TestClient(main.app) as owner, TestClient(main.app) as third:
        login(owner, 'Colleague')
        shared = owner.put('/api/datasets/' + d['id'] + '/members', json={'teams': {team_id: 'editor'}})
        assert shared.status_code == 200 and shared.json()['teams'] == [{'team_id': team_id, 'level': 'editor'}]
        login(third, 'Third')
        assert [(row['id'], row['my_access']) for row in third.get('/api/datasets').json()] == [(d['id'], 'editor')]
        assert upload(third, d).status_code == 200
        assert third.get('/api/datasets/' + other['id']).status_code in (403, 404)
        # Removing the team's grant removes access for its members.
        assert owner.put('/api/datasets/' + d['id'] + '/members', json={'teams': {team_id: None}}).status_code == 200
        assert third.get('/api/datasets').json() == []

    assert admin.patch('/api/users/third/role', json={'role': 'auditor', 'current_password': OLD}).status_code == 200
    with TestClient(main.app) as auditor:
        login(auditor, 'Third')
        people = {row['username']: row['workspace_role'] for row in auditor.get('/api/users').json()}
        assert people == {'Admin': 'administrator', 'Colleague': 'user', 'Third': 'auditor'}
        mapped = auditor.get('/api/access-map')
        assert mapped.status_code == 200 and mapped.json()['can_edit'] is False
        assert auditor.get('/api/teams').status_code == 200
        assert auditor.put('/api/users/colleague/datasets', json={'dataset_ids': []}).status_code == 403
        assert auditor.post('/api/teams', json={'name': 'Nope'}).status_code == 403
        assert auditor.get('/api/datasets').json() == []  # Auditing people is not reading their data.
    assert admin.patch('/api/users/third/role', json={'role': 'user', 'current_password': OLD}).status_code == 200
    with core.Session() as session:
        assert session.get(relational.WorkspaceRole, 'third') is None


def test_contributor_creates_but_opens_only_their_own_and_cannot_manage_the_workspace(accounts):
    admin = accounts
    login(admin)
    d = dataset(SimpleNamespace(api=admin))
    with core.Session.begin() as session:
        session.add(relational.WorkspaceContributor(user_id='colleague'))
    with TestClient(main.app) as person:
        user = login(person, 'Colleague')['user']
        assert user['is_contributor'] is True and user['is_admin'] is False
        assert person.get('/api/datasets').json() == []
        assert upload(person, d).status_code == 404
        created = person.post('/api/datasets', json={'name': 'Play area'})
        assert created.status_code == 200, created.text
        assert person.get('/api/datasets/' + d['id'] + '/members').status_code == 404
        removed = person.request('DELETE', '/api/datasets/' + created.json()['id'], json={'confirmation': 'Play area', 'expected_version': created.json()['version']})
        assert removed.status_code == 200, removed.text
        assert person.get('/api/dataset-trash').status_code == 200
        # Managing the workspace stays with administrators.
        for method, path in [('get', '/api/users'), ('get', '/api/access-map'), ('get', '/api/storage'), ('get', '/api/admin/token-usage'),
                             ('post', '/api/teams'), ('patch', '/api/settings'), ('post', '/api/models'), ('get', '/api/admin/documents')]:
            assert getattr(person, method)(path, **({} if method == 'get' else {'json': {}})).status_code == 403, path
    listed = {row['username']: row for row in admin.get('/api/users').json()}
    assert listed['Colleague']['is_contributor'] is True and listed['Admin']['is_contributor'] is False


def test_contributor_quick_start_uses_the_workspace_default_models(accounts):
    """Quick start as a Contributor: new dataset (workspace Defaults, no private model copies),
    upload, reading, a question and an extraction."""
    from lapi_app import worker
    from test_dataset_models import model, make_default
    admin = accounts
    login(admin)
    s = SimpleNamespace(api=admin)
    profile = dataset(s)['models'][0]['connection_profile_id']
    # Workspace Defaults that differ from the legacy settings, as in production.
    emb, gen = model(s, profile, 'Embedding two', ['embedding']), model(s, profile, 'Chat two', ['chat', 'extraction'])
    assert make_default(s, emb, 'embedding', acknowledge_index_rebuild=True, allow_external=True).status_code == 200
    assert make_default(s, gen, 'chat').status_code == 200 and make_default(s, gen, 'extraction').status_code == 200
    models_before = len(admin.get('/api/models').json())
    with core.Session.begin() as session:
        session.add(relational.WorkspaceContributor(user_id='colleague'))
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        d = person.post('/api/datasets', json={'name': 'Resume-mk'}).json()
        migrated = person.post('/api/datasets/' + d['id'] + '/migrate-settings', json={})
        assert migrated.status_code == 200, migrated.text
        config = person.get('/api/datasets/' + d['id'] + '/models').json()
        assert config['embedding_model_id'] == emb['id'] and config['mappings'] == []
        # Model mapping is the administrator's job; chat offers the workspace Default.
        assert [m['id'] for m in config['chat_choices']] == [gen['id']]
        assert person.put('/api/datasets/' + d['id'] + '/models', json={'mappings': []}).status_code == 403
        assert len(admin.get('/api/models').json()) == models_before  # No private model copies.
        uploaded = upload(person, d)
        assert uploaded.status_code == 200, uploaded.text
        assert worker.run_once()
        document_id = uploaded.json()['documents'][0]['id']
        assert person.get('/api/documents/' + document_id).json()['status'] == 'ready'
        chat = person.post('/api/conversations', json={'dataset_id': d['id'], 'document_ids': [document_id]}).json()
        answered = person.post('/api/conversations/' + chat['id'] + '/messages', json={'text': 'What are the payment terms?', 'allow_external': True})
        assert answered.status_code == 200, answered.text
        template = person.post('/api/templates', json={'name': 'Terms', 'dataset_id': d['id'], 'schema': {'type': 'object', 'additionalProperties': False,
            'properties': {'terms': {'type': ['string', 'null']}}, 'required': ['terms']}})
        assert template.status_code == 200, template.text
        extraction = person.post('/api/extractions', json={'dataset_id': d['id'], 'document_ids': [document_id], 'template_id': template.json()['id'], 'allow_external': True})
        assert extraction.status_code == 200, extraction.text
        assert worker.run_once()
        assert person.get('/api/extractions/' + extraction.json()['id']).json()['status'] == 'ready'
        chat = person.post('/api/conversations', json={'dataset_id': d['id'], 'document_ids': [document_id]}).json()
        picked = person.post('/api/conversations/' + chat['id'] + '/messages', json={'text': 'Terms?', 'allow_external': True, 'model_id': gen['id']})
        assert picked.status_code == 200, picked.text


def test_contributor_cannot_create_a_dataset_before_workspace_defaults_exist(accounts):
    login(accounts)
    with core.Session.begin() as session:
        session.add(relational.WorkspaceContributor(user_id='colleague'))
    with TestClient(main.app) as person:
        login(person, 'Colleague')
        d = person.post('/api/datasets', json={'name': 'Too early'}).json()
        refused = person.post('/api/datasets/' + d['id'] + '/migrate-settings', json={})
        assert refused.status_code == 409 and 'administrator' in refused.json()['detail']
        assert person.get('/api/models').json() == []  # Nothing was registered on their behalf.


def test_existing_grants_become_editor_and_bootstrap_owners_become_owner(accounts):
    login(accounts)
    d = dataset(SimpleNamespace(api=accounts))
    grant(accounts, 'colleague', d, 'viewer')
    table = relational.UserDataset.__table__
    with core.current_engine().begin() as connection:
        connection.execute(table.update().values(access_level=None))
        relational.upgrade_legacy(connection)
    with core.Session() as session:
        assert session.scalar(select(relational.UserDataset.access_level).where(relational.UserDataset.user_id == 'colleague')) == 'editor'


def test_keycloak_groups_become_team_memberships(accounts):
    with core.Session.begin() as session:
        teams.sync_keycloak_teams(session, 'colleague', ['/Finance', '/Finance/Auditors', '', 7])
    with core.Session() as session:
        names = {row['name']: row['member_ids'] for row in teams.team_rows(session)}
    assert names == {'Finance': ['colleague'], 'Finance/Auditors': ['colleague']}
    with core.Session.begin() as session:
        teams.sync_keycloak_teams(session, 'colleague', ['/Finance'])
    with core.Session() as session:
        names = {row['name']: row['member_ids'] for row in teams.team_rows(session)}
    assert names == {'Finance': ['colleague'], 'Finance/Auditors': []}
    login(accounts)
    kc_team = teams.keycloak_team_id('Finance')
    refused = accounts.put('/api/teams/' + kc_team + '/members', json={'user_ids': []})
    assert refused.status_code == 409 and 'Keycloak' in refused.json()['detail']
