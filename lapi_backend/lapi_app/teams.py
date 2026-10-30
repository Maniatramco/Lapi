"""Teams and dataset members.

A team gets dataset access for all its members at once. Keycloak teams mirror each
person's Keycloak groups at sign-in (keycloak_auth.provision); local teams are managed
here by administrators. Dataset owners manage who can open their dataset, and at which
level, without being administrators. OpenFGA follows every change (authz.py).
"""
import hashlib
import re
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from . import core, relational
from . import dataset_access as access

Level = Literal['viewer', 'editor', 'owner']
KEYCLOAK = 'keycloak'


class TeamInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)


class TeamMembers(BaseModel):
    model_config = ConfigDict(extra='forbid')
    user_ids: list[str] = Field(max_length=5000)


class Grants(BaseModel):
    """Dataset ID => level; a dataset left out has no access through this team."""
    model_config = ConfigDict(extra='forbid')
    grants: dict[str, Level] = Field(max_length=1000)


class Members(BaseModel):
    """Changes only: level to set, or null to remove. Others stay as they are."""
    model_config = ConfigDict(extra='forbid')
    people: dict[str, Level | None] = Field(default_factory=dict, max_length=5000)
    teams: dict[str, Level | None] = Field(default_factory=dict, max_length=1000)


def keycloak_team_id(name):
    return 'kc-' + hashlib.sha256(name.encode()).hexdigest()[:40]


def keycloak_names(groups):
    """Keycloak group paths ('/Finance/Auditors') to team names, without the leading slash."""
    names = set()
    for group in groups or []:
        if isinstance(group, str) and (name := group.strip().strip('/')):
            names.add(name[:200])
    return names


def sync_keycloak_teams(session, user_id, groups):
    """Make the person's Keycloak-team memberships match their Keycloak groups now."""
    wanted = {keycloak_team_id(name): name for name in keycloak_names(groups)}
    for team_id, name in wanted.items():
        if session.get(relational.Team, team_id) is None:
            session.add(relational.Team(team_id=team_id, name=name, source=KEYCLOAK))
    session.flush()
    current = {row.team_id: row for row in session.scalars(select(relational.TeamMember).join(
        relational.Team, relational.Team.team_id == relational.TeamMember.team_id).where(
        relational.TeamMember.user_id == user_id, relational.Team.source == KEYCLOAK))}
    for team_id in wanted.keys() - current.keys():
        session.add(relational.TeamMember(team_id=team_id, user_id=user_id))
    for team_id in current.keys() - wanted.keys():
        session.delete(current[team_id])


def team_rows(session):
    teams = list(session.scalars(select(relational.Team).order_by(relational.Team.name)))
    members, grants = {}, {}
    for row in session.scalars(select(relational.TeamMember)):
        members.setdefault(row.team_id, []).append(row.user_id)
    for row in session.scalars(select(relational.TeamDataset)):
        grants.setdefault(row.team_id, {})[row.dataset_id] = row.access_level
    return [{'id': team.team_id, 'name': team.name, 'source': team.source,
             'member_ids': sorted(members.get(team.team_id, [])), 'grants': grants.get(team.team_id, {})} for team in teams]


def _existing_datasets(session, ids):
    found = set(session.scalars(select(relational.Dataset.dataset_id).where(relational.Dataset.dataset_id.in_(list(ids))))) if ids else set()
    if found != set(ids):
        raise HTTPException(404, 'One or more workspaces no longer exist. Nothing changed.')


def _team(session, team_id):
    team = session.get(relational.Team, team_id)
    if team is None:
        raise HTTPException(404, 'Team not found.')
    return team


def install(app, auth):
    def administrator(owner=Depends(auth)):
        access.require_admin(owner)
        return owner

    def audit_reader(owner=Depends(auth)):
        if not (core.is_administrator(owner) or access.is_auditor(owner)):
            raise HTTPException(403, 'Administrator or Auditor access is required.')
        return owner

    @app.get('/api/teams')
    def teams(owner=Depends(audit_reader)):
        with core.Session() as session:
            return team_rows(session)

    @app.post('/api/teams')
    def create_team(body: TeamInput, owner=Depends(administrator)):
        name = re.sub(r'\s+', ' ', body.name).strip()
        if not name:
            raise HTTPException(422, 'Enter a team name.')
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            if session.scalar(select(relational.Team.team_id).where(relational.Team.name == name)):
                raise HTTPException(409, 'A team with this name already exists.')
            team = relational.Team(team_id=core.uid(), name=name, source='local')
            session.add(team)
            session.flush()
            return {'id': team.team_id, 'name': name, 'source': 'local', 'member_ids': [], 'grants': {}}

    @app.put('/api/teams/{team_id}/members')
    def set_members(team_id: str, body: TeamMembers, owner=Depends(administrator)):
        ids = set(body.user_ids)
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            team = _team(session, team_id)
            if team.source == KEYCLOAK:
                raise HTTPException(409, 'Keycloak sets this team\'s members from its groups. Change them in Keycloak.')
            found = set(session.scalars(select(core.User.id).where(core.User.id.in_(list(ids))))) if ids else set()
            if found != ids:
                raise HTTPException(404, 'One or more people no longer exist. Nothing changed.')
            current = {row.user_id: row for row in session.scalars(select(relational.TeamMember).where(relational.TeamMember.team_id == team_id))}
            for user_id in ids - current.keys():
                session.add(relational.TeamMember(team_id=team_id, user_id=user_id))
            for user_id in current.keys() - ids:
                session.delete(current[user_id])
        return {'ok': True, 'team_id': team_id, 'member_ids': sorted(ids)}

    @app.put('/api/teams/{team_id}/datasets')
    def set_team_grants(team_id: str, body: Grants, owner=Depends(administrator)):
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            _team(session, team_id)
            _existing_datasets(session, body.grants.keys())
            current = {row.dataset_id: row for row in session.scalars(select(relational.TeamDataset).where(relational.TeamDataset.team_id == team_id))}
            for dataset_id, level in body.grants.items():
                if dataset_id in current:
                    current[dataset_id].access_level = level
                else:
                    session.add(relational.TeamDataset(team_id=team_id, dataset_id=dataset_id, access_level=level))
            for dataset_id in current.keys() - body.grants.keys():
                session.delete(current[dataset_id])
        return {'ok': True, 'team_id': team_id, 'grants': body.grants}

    @app.delete('/api/teams/{team_id}')
    def delete_team(team_id: str, owner=Depends(administrator)):
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            team = _team(session, team_id)
            session.execute(delete(relational.TeamDataset).where(relational.TeamDataset.team_id == team_id))
            session.execute(delete(relational.TeamMember).where(relational.TeamMember.team_id == team_id))
            session.delete(team)
        return {'ok': True, 'team_id': team_id}

    @app.get('/api/datasets/{id}/members')
    def dataset_members(id: str, owner=Depends(auth)):
        access.get_record(id, owner, 'knowledge_base', level='owner')
        with core.Session() as session:
            people = [{'user_id': row.user_id, 'level': row.access_level} for row in session.scalars(select(relational.UserDataset).where(
                relational.UserDataset.dataset_id == id, relational.UserDataset.enabled == True))]
            teams = [{'team_id': row.team_id, 'level': row.access_level} for row in session.scalars(select(relational.TeamDataset).where(relational.TeamDataset.dataset_id == id))]
            # Owners pick people and teams to share with by name; administrators already see everything.
            directory = [{'id': user.id, 'username': user.username} for user in session.scalars(
                select(core.User).where(core.User.role != 'administrator').order_by(core.User.username))]
            all_teams = [{'id': team.team_id, 'name': team.name, 'source': team.source} for team in session.scalars(
                select(relational.Team).order_by(relational.Team.name))]
        return {'dataset_id': id, 'people': people, 'teams': teams, 'directory': directory, 'all_teams': all_teams}

    @app.put('/api/datasets/{id}/members')
    def set_dataset_members(id: str, body: Members, owner=Depends(auth)):
        """Owners give or remove access to their dataset. Administrators always have access."""
        access.get_record(id, owner, 'knowledge_base', level='owner')
        with core.document_lock('dataset-access'), core.Session.begin() as session:
            people = set(body.people)
            found = set(session.scalars(select(core.User.id).where(core.User.id.in_(list(people))))) if people else set()
            if found != people:
                raise HTTPException(404, 'One or more people no longer exist. Nothing changed.')
            if any(core.is_administrator(user_id, session) for user_id in people):
                raise HTTPException(400, 'Administrators always have access to every workspace.')
            for team_id in body.teams:
                _team(session, team_id)
            grants = {row.user_id: row for row in session.scalars(select(relational.UserDataset).where(relational.UserDataset.dataset_id == id))}
            for user_id, level in body.people.items():
                row = grants.get(user_id)
                if level is None:
                    if row:
                        row.enabled = False
                elif row:
                    row.enabled, row.access_level = True, level
                else:
                    session.add(relational.UserDataset(user_id=user_id, dataset_id=id, access_level=level))
            team_grants = {row.team_id: row for row in session.scalars(select(relational.TeamDataset).where(relational.TeamDataset.dataset_id == id))}
            for team_id, level in body.teams.items():
                row = team_grants.get(team_id)
                if level is None:
                    if row:
                        session.delete(row)
                elif row:
                    row.access_level = level
                else:
                    session.add(relational.TeamDataset(team_id=team_id, dataset_id=id, access_level=level))
        return dataset_members(id, owner)
