"""Skills (WS5): named playbooks the agent loads on demand, or automatically when they apply.

Built-in skills live in lapi_agent/skills/*.md (front matter + steps). People
add their own as Record kind "skill" (a form, or an uploaded SKILL.md): personal by
default, or shared with one dataset or the whole workspace by an administrator.
Front matter may say when a skill applies (document_types, domains, keywords,
documents); matching skills are loaded before the agent answers, so the person
does not have to name them. A skill only narrows what the agent does; it can
never widen tool access or skip confirmation.
"""
import fnmatch
import re
import time
from pathlib import Path
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
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
    applies = {key: _terms(meta.get(key, '')) for key in APPLIES_KEYS if meta.get(key, '').strip()}
    return {'name': meta.get('name', ''), 'description': meta.get('description', ''), 'allowed_tools': tools,
            'output_format': meta.get('output_format', ''), 'instructions': body.strip(), 'applies_to': applies}


APPLIES_KEYS = ('document_types', 'domains', 'keywords', 'documents')
MAX_AUTO = 4  # Skills loaded automatically for one request.


def _terms(value):
    return [t.strip().lower() for t in str(value).split(',') if t.strip()][:20]


def render(skill):
    """A skill as SKILL.md text (front matter + steps), the same shape uploads accept."""
    head = [('name', skill['name']), ('description', skill.get('description', '')),
            ('allowed_tools', ', '.join(skill.get('allowed_tools') or [])), ('output_format', skill.get('output_format', ''))]
    head += [(key, ', '.join(terms)) for key, terms in (skill.get('applies_to') or {}).items() if terms]
    return '---\n' + '\n'.join(f'{k}: {v}' for k, v in head if v) + '\n---\n' + skill.get('instructions', '').strip() + '\n'


def _words(text):
    return set(re.findall(r'[a-z0-9][a-z0-9-]*', (text or '').lower()))


def applies(skill, text, document_names=()):
    """Why this skill fits the request, or '' when it does not. Matching is plain words and file-name
    patterns, so it is explainable: a keyword, document type or domain in the request, or a document
    whose name matches document_types / documents."""
    terms = skill.get('applies_to') or {}
    if not any(terms.values()): return ''
    words = _words(text); lowered = (text or '').lower(); names = [n.lower() for n in document_names]
    for key in ('keywords', 'document_types', 'domains'):
        for term in terms.get(key, []):
            if (term in words) or (' ' in term and term in lowered): return f'{key.replace("_", " ")}: {term}'
    for term in terms.get('document_types', []):
        if any(term in name for name in names): return f'document type: {term}'
    for pattern in terms.get('documents', []):
        if any(fnmatch.fnmatch(name, pattern) or pattern in name for name in names): return f'document: {pattern}'
    return ''


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
                   {'allowed_tools': data.get('allowed_tools', []), 'applies_to': data.get('applies_to') or {}, 'id': r.id, 'source': 'custom', 'scope': scope,
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

    def relevant(self, owner, dataset_id, text, document_names=()):
        """Skills whose applies_to matches this request, each with the reason, at most MAX_AUTO."""
        out = []
        for skill in self.all(owner, dataset_id):
            why = applies(skill, text, document_names)
            if why: out.append(skill | {'why': why})
        return out[:MAX_AUTO]


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
    applies_to: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator('applies_to')
    @classmethod
    def applies_terms(cls, value):
        unknown = sorted(set(value) - set(APPLIES_KEYS))
        if unknown: raise ValueError('Unknown applies_to keys: ' + ', '.join(unknown))
        out = {}
        for key, terms in value.items():
            terms = [str(t).strip().lower()[:60] for t in (terms or []) if str(t).strip()][:20]
            if terms: out[key] = terms
        return out

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

    @app.post('/api/skills/upload')
    async def upload_skill(file: UploadFile = File(...), scope: str = Form('personal'), dataset_id: str = Form(''), owner=Depends(auth)):
        """A SKILL.md file (front matter + steps). Uploading a skill you already have replaces it."""
        if not (file.filename or '').lower().endswith(('.md', '.txt', '.markdown')):
            raise HTTPException(422, 'Upload a Markdown skill file (SKILL.md).')
        raw = await file.read()
        if len(raw) > 64000: raise HTTPException(413, 'A skill file is at most 64 KB.')
        try: parsed = _parse(raw.decode('utf-8'))
        except UnicodeDecodeError: raise HTTPException(422, 'The skill file must be UTF-8 text.') from None
        name = parsed['name'] or re.sub(r'\.(md|txt|markdown)$', '', file.filename or '', flags=re.I)
        if name.lower() == 'skill': name = ''
        if not name: raise HTTPException(422, 'Add "name: your-skill" to the front matter.')
        if not parsed['instructions']: raise HTTPException(422, 'The skill file has no steps after the front matter.')
        try:
            body = SkillInput(name=name, description=parsed['description'] or parsed['instructions'].splitlines()[0][:300],
                              instructions=parsed['instructions'], allowed_tools=parsed['allowed_tools'], output_format=parsed['output_format'],
                              scope=scope, dataset_id=dataset_id, applies_to=parsed['applies_to'])
        except ValueError as error:
            raise HTTPException(422, str(error).splitlines()[-1][:300]) from None
        _check_scope(body, owner)
        data = body.model_dump() | {'saved_at': time.time(), 'source_filename': file.filename}
        existing = next((s for s in _custom(owner) if s['name'] == body.name and s['owner'] == owner), None)
        if existing:
            record = _editable(existing['id'], owner); routing.write_version(record, data)
            with core.Session.begin() as session:
                r = session.get(core.Record, existing['id']); r.parent_id = body.dataset_id if body.scope == 'dataset' else ''
            return next(s for s in _custom(owner) if s['id'] == existing['id']) | {'replaced': True}
        record = routing.create('skill', owner, body.name, data, parent=body.dataset_id if body.scope == 'dataset' else '')
        return next(s for s in _custom(owner) if s['id'] == record.id)

    @app.get('/api/skills/{skill_id}/download')
    def download_skill(skill_id: str, owner=Depends(auth)):
        skill = next((s for s in Library().all(owner) if s['id'] == skill_id), None)
        if not skill: raise HTTPException(404, 'Skill not found.')
        return Response(render(skill), media_type='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{skill["name"]}.md"'})

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
