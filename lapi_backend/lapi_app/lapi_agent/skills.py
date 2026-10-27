"""Skills (WS5): named playbooks the agent loads on demand.

Built-in skills live in lapi_agent/skills/*.md (front matter + steps). People
add their own as Record kind "skill": personal by default, or shared with one
dataset or the whole workspace by an administrator. A skill only narrows what
the agent does; it can never widen tool access or skip confirmation.
"""
import re
import time
from pathlib import Path
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from .. import core, dataset_models as routing
from ..dataset_access import dataset_ids

BUILTIN_DIR = Path(__file__).with_name('skills')
NAME = re.compile(r'^[a-z0-9][a-z0-9-]{1,39}$')


def _parse(text):
    meta, body = {}, text
    if text.startswith('---'):
        _, head, body = text.split('---', 2)
        for line in head.strip().splitlines():
            if ':' in line:
                key, value = line.split(':', 1); meta[key.strip()] = value.strip()
    tools = [t.strip() for t in meta.get('allowed_tools', '').split(',') if t.strip()]
    return {'name': meta.get('name', ''), 'description': meta.get('description', ''), 'allowed_tools': tools,
            'output_format': meta.get('output_format', ''), 'instructions': body.strip()}


def builtins():
    out = []
    for path in sorted(BUILTIN_DIR.glob('*.md')):
        skill = _parse(path.read_text(encoding='utf-8'))
        out.append(skill | {'id': 'builtin:' + skill['name'], 'source': 'builtin', 'scope': 'workspace', 'editable': False})
    return out


def _custom(owner, dataset_id=''):
    with core.Session() as session:
        allowed = dataset_ids(owner, session)
        records = list(session.scalars(select(core.Record).where(core.Record.kind == 'skill', core.Record.status != 'deleted')))
    out = []
    for r in records:
        data = core.store.json(r.ref)
        scope = data.get('scope', 'personal')
        visible = (r.owner == owner) or scope == 'workspace' or (scope == 'dataset' and r.parent_id in allowed)
        if not visible: continue
        if scope == 'dataset' and dataset_id and r.parent_id != dataset_id and r.owner != owner: continue
        out.append({k: data.get(k, '') for k in ('name', 'description', 'output_format', 'instructions')} |
                   {'allowed_tools': data.get('allowed_tools', []), 'id': r.id, 'source': 'custom', 'scope': scope,
                    'dataset_id': r.parent_id or '', 'version': r.version, 'editable': r.owner == owner or core.is_administrator(owner),
                    'owner': r.owner, 'updated_at': r.updated_at})
    return out


class Library:
    """Resolution order: personal, then dataset, then workspace, then built-in."""

    def all(self, owner, dataset_id=''):
        custom = _custom(owner, dataset_id)
        rank = {'personal': 0, 'dataset': 1, 'workspace': 2}
        custom.sort(key=lambda s: rank.get(s['scope'], 3))
        seen = set(); out = []
        for skill in custom + builtins():
            if skill['name'] in seen: continue
            seen.add(skill['name']); out.append(skill)
        return out

    def index(self, owner, dataset_id=''):
        return [{'name': s['name'], 'description': s['description']} for s in self.all(owner, dataset_id)]

    def get(self, name, owner, dataset_id=''):
        key = name.strip().lower()
        return next((s for s in self.all(owner, dataset_id) if s['name'] == key), None)


def library():
    return Library()


class SkillInput(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=8000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=30)
    output_format: str = Field(default='', max_length=500)
    scope: str = Field(default='personal', pattern='^(personal|dataset|workspace)$')
    dataset_id: str = ''

    @field_validator('name')
    @classmethod
    def slug(cls, value):
        value = value.strip().lower().replace(' ', '-')
        if not NAME.match(value): raise ValueError('Use lowercase letters, numbers and dashes (2-40 characters).')
        return value

    @field_validator('allowed_tools')
    @classmethod
    def known(cls, value):
        from .agent_tools_v2 import CONTRACTS
        unknown = sorted(set(value) - set(CONTRACTS))
        if unknown: raise ValueError('Unknown tools: ' + ', '.join(unknown))
        return value


def _check_scope(body, owner):
    if body.scope == 'workspace' and not core.is_administrator(owner):
        raise HTTPException(403, 'Only an administrator can share a skill with the whole workspace.')
    if body.scope == 'dataset':
        if not body.dataset_id: raise HTTPException(422, 'Choose the dataset to share this skill with.')
        if not core.is_administrator(owner): raise HTTPException(403, 'Only an administrator can share a skill with a dataset.')
        with core.Session() as session:
            if body.dataset_id not in dataset_ids(owner, session): raise HTTPException(404, 'Dataset not found.')


def _editable(skill_id, owner):
    with core.Session() as session: record = session.get(core.Record, skill_id)
    if not record or record.kind != 'skill' or record.status == 'deleted': raise HTTPException(404, 'Skill not found.')
    if record.owner != owner and not core.is_administrator(owner): raise HTTPException(403, 'You can only change your own skills.')
    return record


def install(app, auth):
    @app.get('/api/skills')
    def list_skills(dataset_id: str = '', owner=Depends(auth)):
        return {'skills': Library().all(owner, dataset_id)}

    @app.post('/api/skills')
    def create_skill(body: SkillInput, owner=Depends(auth)):
        _check_scope(body, owner)
        if any(s['name'] == body.name and s['source'] == 'custom' and s['owner'] == owner for s in _custom(owner)):
            raise HTTPException(409, 'You already have a skill with this name.')
        data = body.model_dump() | {'saved_at': time.time()}
        record = routing.create('skill', owner, body.name, data, parent=body.dataset_id if body.scope == 'dataset' else '')
        return next(s for s in _custom(owner) if s['id'] == record.id)

    @app.put('/api/skills/{skill_id}')
    def update_skill(skill_id: str, body: SkillInput, owner=Depends(auth)):
        record = _editable(skill_id, owner); _check_scope(body, owner)
        routing.write_version(record, body.model_dump() | {'saved_at': time.time()})
        with core.Session.begin() as session:
            r = session.get(core.Record, skill_id); r.name = body.name
            r.parent_id = body.dataset_id if body.scope == 'dataset' else ''
        return next(s for s in _custom(owner) if s['id'] == skill_id)

    @app.delete('/api/skills/{skill_id}')
    def delete_skill(skill_id: str, owner=Depends(auth)):
        _editable(skill_id, owner)
        with core.Session.begin() as session:
            session.get(core.Record, skill_id).status = 'deleted'
        return {'deleted': skill_id}
