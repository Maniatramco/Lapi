"""Workspaces group document collections (datasets). Everyone has a personal workspace and may
create one team workspace; administrators have no limit. People can belong to other team workspaces.

Access stays on the datasets: a workspace's members and teams are written onto the grants of every
collection in it, so the access checks and OpenFGA sync are unchanged. Existing datasets are placed
without widening access: unshared ones go to their owner's personal workspace, shared ones to one
"Organization" workspace whose visibility follows each person's existing grants.
"""
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from . import core, relational
from . import dataset_access as access

KIND = 'workspace'
RANK = {'viewer': 1, 'editor': 2, 'owner': 3}
ORGANIZATION = 'Organization'


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)


class Members(BaseModel):
    model_config = ConfigDict(extra='forbid')
    people: dict[str, Literal['viewer', 'editor', 'owner'] | None] = {}
    teams: dict[str, Literal['viewer', 'editor', 'owner'] | None] = {}


def read(record): return core.store.json(record.ref)


def rows():
    with core.Session() as session:
        return list(session.scalars(select(core.Record).where(core.Record.kind == KIND, core.Record.status != 'deleted').order_by(core.Record.created_at, core.Record.id)))


def collections():
    with core.Session() as session:
        return list(session.scalars(select(core.Record).where(core.Record.kind == 'knowledge_base', core.Record.status != 'deleted')))


def _new(owner, name, audience, **extra):
    from . import dataset_models as routing
    return routing.create(KIND, owner, name, {'audience': audience, 'members': {}, 'teams': {}, **extra})


def _display(owner):
    from . import preferences
    name = preferences.display_name(owner)
    if name: return name
    with core.Session() as session:
        user = session.get(core.User, owner)
    return user.username if user else owner


def rename_personal(owner, name):
    """The personal workspace takes the name the person gave, while it still has its default name."""
    if not name: return
    with core.document_lock('workspace-' + owner):
        found = next((r for r in rows() if r.owner == owner and read(r).get('audience') == 'personal'), None)
        if found is None: return
        with core.Session.begin() as session:
            record = session.get(core.Record, found.id)
            if record.name.endswith("'s workspace"): record.name = name + "'s workspace"


def personal_for(owner):
    """This person's personal workspace, created the first time it is needed."""
    with core.document_lock('workspace-' + owner):
        found = next((r for r in rows() if r.owner == owner and read(r).get('audience') == 'personal'), None)
        return found or _new(owner, _display(owner) + "'s workspace", 'personal')


def place_existing():
    """Give every collection a workspace once, never changing who can open it."""
    pending = []
    for record in collections():
        data = core.store.json(record.ref)
        if not data.get('workspace_id'): pending.append((record, data))
    if not pending: return
    with core.document_lock('workspace-placement'):
        for record, data in pending:
            data = core.store.json(record.ref)
            if data.get('workspace_id'): continue
            with core.Session() as session:
                people = {row.user_id: row.access_level or 'viewer' for row in session.scalars(select(relational.UserDataset).where(
                    relational.UserDataset.dataset_id == record.id, relational.UserDataset.enabled == True)) if row.user_id != record.owner}
                shared = bool(people) or bool(session.scalars(select(relational.TeamDataset).where(relational.TeamDataset.dataset_id == record.id)).first())
            if data.get('audience') == 'team':
                # Made for a team in the earlier release: its people become the workspace's members.
                workspace = next((r for r in rows() if r.owner == record.owner and read(r).get('audience') == 'team'), None)
                if workspace is None: workspace = _new(record.owner, record.name, 'team', members=people)
            elif shared:
                workspace = next((r for r in rows() if read(r).get('organization')), None) or _new(record.owner, ORGANIZATION, 'team', organization=True)
            else:
                workspace = personal_for(record.owner)
            core.store.put_json(record.ref, data | {'workspace_id': workspace.id})


def level_for(record, actor, session=None):
    """The person's level on the workspace itself, or None."""
    data = read(record)
    # Administrators look after the Organization workspace; everyone else's are private to their members.
    if data.get('organization') and core.is_administrator(actor, session): return 'owner'
    # Whoever happened to trigger the Organization workspace's creation gains nothing from it.
    if record.owner == actor and not data.get('organization'): return 'owner'
    levels = [data.get('members', {}).get(actor)]
    if data.get('teams'):
        with core.Session() as active:
            mine = set(active.scalars(select(relational.TeamMember.team_id).where(relational.TeamMember.user_id == actor)))
        levels += [level for team, level in data['teams'].items() if team in mine]
    levels = [level for level in levels if level]
    return max(levels, key=lambda level: RANK[level]) if levels else None


def can_add_collections(record, actor):
    return level_for(record, actor) in ('owner', 'editor')


def visible(actor):
    """Workspaces this person belongs to, or holds a collection in (the Organization workspace)."""
    place_existing()
    personal_for(actor)
    found = rows()
    data_of = {record.id: read(record) for record in found}
    placed = [(record, core.store.json(record.ref).get('workspace_id')) for record in collections()]
    if core.is_administrator(actor):
        organization = {id for id, data in data_of.items() if data.get('organization')}
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            for record, workspace_id in placed:
                if workspace_id in organization and session.get(relational.UserDataset, (actor, record.id)) is None:
                    _set_grant(session, record.id, actor, 'owner')
    with core.Session() as session:
        mine = access.dataset_ids(actor, session)
    counts, holding = {}, set()
    for record, workspace_id in placed:
        counts[workspace_id] = counts.get(workspace_id, 0) + 1
        if record.id in mine: holding.add(workspace_id)
    out = []
    for record in found:
        data, level = data_of[record.id], level_for(record, actor)
        if data.get('audience') == 'personal' and record.owner != actor: continue  # Never anyone else's.
        if level is None and record.id not in holding: continue
        out.append({'id': record.id, 'name': record.name, 'audience': data.get('audience', 'team'), 'organization': bool(data.get('organization')),
                    'my_access': level or 'viewer', 'mine': record.owner == actor, 'collection_count': counts.get(record.id, 0)})
    return sorted(out, key=lambda w: (w['audience'] != 'personal', not w['mine'], w['name'].lower()))


def _set_grant(session, dataset_id, user_id, level):
    row = session.get(relational.UserDataset, (user_id, dataset_id))
    if row is None:
        # Written even on removal: a creator with no row would otherwise keep access.
        session.add(relational.UserDataset(user_id=user_id, dataset_id=dataset_id, access_level=level or 'viewer', enabled=bool(level)))
    elif level:
        row.enabled, row.access_level = True, level
    else:
        row.enabled = False


def _set_team_grant(session, dataset_id, team_id, level):
    row = session.get(relational.TeamDataset, (team_id, dataset_id))
    if row is None:
        if level: session.add(relational.TeamDataset(team_id=team_id, dataset_id=dataset_id, access_level=level))
    elif level:
        row.access_level = level
    else:
        session.delete(row)


def grant_to_collection(workspace, dataset_id, creator):
    """A new collection is open to everyone in its workspace, and its creator owns it."""
    data = read(workspace)
    with core.document_lock('dataset-access'), core.Session.begin() as session:
        for user_id, level in data.get('members', {}).items():
            if user_id != creator: _set_grant(session, dataset_id, user_id, level)
        for team_id, level in data.get('teams', {}).items():
            _set_team_grant(session, dataset_id, team_id, level)
        if session.get(core.User, creator):
            _set_grant(session, dataset_id, creator, 'owner')
        if workspace.owner != creator and session.get(core.User, workspace.owner):
            _set_grant(session, dataset_id, workspace.owner, 'owner')


def is_personal(dataset_record):
    workspace_id = core.store.json(dataset_record.ref).get('workspace_id')
    if not workspace_id: return False
    with core.Session() as session:
        workspace = session.get(core.Record, workspace_id)
    return bool(workspace and read(workspace).get('audience') == 'personal')


def _owned(id, actor):
    with core.Session() as session:
        record = session.get(core.Record, id)
    if record is None or record.kind != KIND or record.status == 'deleted': raise HTTPException(404, 'Workspace not found.')
    return record


def install(app, auth):
    @app.get('/api/workspaces')
    def list_workspaces(actor=Depends(auth)):
        found = visible(actor)
        admin = core.is_administrator(actor)
        return {'workspaces': found, 'can_create_team': admin or not any(w['mine'] and w['audience'] == 'team' and not w['organization'] for w in found)}

    @app.post('/api/workspaces')
    def create_workspace(body: WorkspaceInput, actor=Depends(auth)):
        with core.document_lock('workspace-' + actor + '-team'):
            if not core.is_administrator(actor) and any(r.owner == actor and read(r).get('audience') == 'team' and not read(r).get('organization') for r in rows()):
                raise HTTPException(409, 'You already have a team workspace. Each person can have one personal and one team workspace.')
            record = _new(actor, body.name.strip(), 'team')
        return {'id': record.id, 'name': record.name, 'audience': 'team', 'organization': False, 'my_access': 'owner', 'mine': True, 'collection_count': 0}

    @app.get('/api/workspaces/{id}/members')
    def workspace_members(id: str, actor=Depends(auth)):
        record = _owned(id, actor)
        if level_for(record, actor) != 'owner': raise HTTPException(403, 'Only owners of this workspace can see its members.')
        data = read(record)
        with core.Session() as session:
            directory = [{'id': user.id, 'username': user.username} for user in session.scalars(
                select(core.User).order_by(core.User.username)) if user.id != record.owner]
            all_teams = [{'id': team.team_id, 'name': team.name, 'source': team.source} for team in session.scalars(select(relational.Team).order_by(relational.Team.name))]
        return {'workspace_id': id, 'people': [{'user_id': k, 'level': v} for k, v in data.get('members', {}).items()],
                'teams': [{'team_id': k, 'level': v} for k, v in data.get('teams', {}).items()], 'directory': directory, 'all_teams': all_teams}

    @app.put('/api/workspaces/{id}/members')
    def set_workspace_members(id: str, body: Members, actor=Depends(auth)):
        record = _owned(id, actor)
        if level_for(record, actor) != 'owner': raise HTTPException(403, 'Only owners of this workspace can change its members.')
        with core.document_lock('workspace-members-' + id):
            data = read(record)
            if data.get('audience') == 'personal' and any([*body.people.values(), *body.teams.values()]):
                raise HTTPException(400, 'This is a personal workspace, so it cannot be shared. Use a team workspace to work with others.')
            with core.Session() as session:
                people = set(body.people)
                found = set(session.scalars(select(core.User.id).where(core.User.id.in_(list(people))))) if people else set()
                if found != people: raise HTTPException(404, 'One or more people no longer exist. Nothing changed.')
                if record.owner in people: raise HTTPException(400, 'The workspace creator always keeps access.')
                teams = set(body.teams)
                known = set(session.scalars(select(relational.Team.team_id))) if teams else set()
                if teams - known: raise HTTPException(404, 'One or more teams no longer exist. Nothing changed.')
            members, team_levels = dict(data.get('members', {})), dict(data.get('teams', {}))
            for key, level in body.people.items():
                if level: members[key] = level
                else: members.pop(key, None)
            for key, level in body.teams.items():
                if level: team_levels[key] = level
                else: team_levels.pop(key, None)
            core.store.put_json(record.ref, data | {'members': members, 'teams': team_levels})
            inside = [r.id for r in collections() if core.store.json(r.ref).get('workspace_id') == id]
            with core.document_lock('dataset-access'), core.Session.begin() as session:
                for dataset_id in inside:
                    for user_id, level in body.people.items(): _set_grant(session, dataset_id, user_id, level)
                    for team_id, level in body.teams.items(): _set_team_grant(session, dataset_id, team_id, level)
        return workspace_members(id, actor)
