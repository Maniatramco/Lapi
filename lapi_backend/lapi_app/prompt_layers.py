"""Prompt layers for agentic chat (WS11).

* Dataset instructions: owner-written guidance for one dataset (≤4 KB, versioned).
* Model optimization guides: how to prompt one registered model (≤8 KB), with an
  optional per-dataset override. Built-in guides cover common model families.

All layers are data appended after Lapi's fixed rules; they shape style and
focus but can never switch off citations, access checks or confirmation.
"""
import re
import time
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import core, dataset_models as routing
from .dataset_access import require_admin, require_level, dataset_ids

INSTRUCTION_BYTES = 4096
GUIDE_BYTES = 8192
WEAKENING = [
    (r"\b(?:don'?t|do not|never|no need to|skip|stop|without)\s+(?:\w+\s+){0,2}cit(?:e|ing|ations?)\b", 'asks to drop citations'),
    (r'\b(?:make up|invent|guess|fabricate|assume)\b', 'invites unsupported answers'),
    (r'\bignore\s+(?:the\s+)?(?:rules|instructions|system|previous)\b', 'tries to override Lapi rules'),
    (r'\b(?:general|outside|external|world|your own)\s+knowledge\b', 'invites answers from outside the sources'),
    (r'\b(?:run|start|execute)\s+(?:the\s+)?(?:extraction|upload|workflow)s?\s+(?:automatically|without (?:asking|confirmation))\b', 'tries to skip confirmation'),
]
FAMILY_GUIDES = {
    'gemini': 'Gemini: call several independent read tools in one step. Keep answers short and lead with the result. '
              'Put the citation [n] at the end of each factual sentence. Prefer tables for comparisons.',
    'claude': 'Claude: plan briefly with update_plan for multi-part requests, then call independent tools in parallel. '
              'Answer directly; avoid preambles. Cite each factual sentence.',
    'gpt': 'GPT: prefer exact catalog and aggregate tools for counts; call tools in parallel when independent. '
           'Be concise and cite each factual sentence.',
    'qwen': 'Qwen: one tool at a time is fine. Keep answers under 150 words and cite each factual sentence.',
    'llama': 'Llama: request only needed fields; keep answers short and cite each factual sentence.',
}


def weakening_warnings(text):
    return [label for pattern, label in WEAKENING if re.search(pattern, text or '', re.I)]


def _latest(kind, parent):
    with core.Session() as session:
        record = session.scalars(select(core.Record).where(core.Record.kind == kind, core.Record.parent_id == parent,
                                                            core.Record.status != 'deleted').order_by(core.Record.updated_at.desc())).first()
    return record


def _read(kind, parent):
    record = _latest(kind, parent)
    if not record: return {'text': '', 'version': 0, 'updated_at': None, 'updated_by': None}
    data = core.store.json(record.ref)
    return {'text': data.get('text', ''), 'version': record.version, 'updated_at': record.updated_at,
            'updated_by': data.get('updated_by'), 'summary': data.get('summary', ''), 'id': record.id}


def _write(kind, parent, owner, text, limit, summary=''):
    if len(text.encode('utf-8')) > limit: raise HTTPException(413, f'Keep this under {limit // 1024} KB.')
    data = {'text': text.strip(), 'updated_by': owner, 'summary': summary[:300], 'saved_at': time.time()}
    record = _latest(kind, parent)
    if record is None:
        record = routing.create(kind, owner, kind, data, parent=parent)
    else:
        record = routing.write_version(record, data)
    return _read(kind, parent)


def _versions(kind, parent):
    record = _latest(kind, parent)
    if not record: return []
    out = []
    for n in range(record.version, max(0, record.version - 20), -1):
        try: data = core.store.json(f'{record.kind}/{record.id}/v{n}.json')
        except FileNotFoundError: continue
        out.append({'version': n, 'text': data.get('text', ''), 'summary': data.get('summary', ''),
                    'updated_by': data.get('updated_by'), 'saved_at': data.get('saved_at')})
    return out


def _require_dataset(dataset_id, actor):
    with core.Session() as session:
        if dataset_id not in dataset_ids(actor, session): raise HTTPException(404, 'Workspace not found.')


def dataset_instructions(dataset_id, owner=None):
    if not dataset_id: return {'text': '', 'version': 0}
    return _read('dataset_instructions', dataset_id)


def model_guide(snapshot, dataset_id='', owner=None):
    """Dataset override, else the model's saved guide, else a family default."""
    if dataset_id:
        override = _read('dataset_prompt_guide', dataset_id)
        if override['text']: return override['text']
    model_id = (snapshot or {}).get('model_id')
    if model_id:
        saved = _read('model_prompt_guide', model_id)
        if saved['text']: return saved['text']
    name = ' '.join(str((snapshot or {}).get(k) or '') for k in ('model_name',)) + ' ' + str(((snapshot or {}).get('settings') or {}).get('model') or '')
    for family, text in FAMILY_GUIDES.items():
        if family in name.lower(): return text
    return ''


class TextInput(BaseModel):
    text: str = Field(default='', max_length=GUIDE_BYTES)
    summary: str = Field(default='', max_length=300)
    expected_version: int | None = None


def install(app, auth):
    @app.get('/api/datasets/{dataset_id}/instructions')
    def get_instructions(dataset_id: str, owner=Depends(auth)):
        _require_dataset(dataset_id, owner)
        return dataset_instructions(dataset_id) | {'limit_bytes': INSTRUCTION_BYTES, 'can_edit': core.is_administrator(owner)}

    @app.get('/api/datasets/{dataset_id}/instructions/versions')
    def instruction_versions(dataset_id: str, owner=Depends(auth)):
        _require_dataset(dataset_id, owner)
        return {'versions': _versions('dataset_instructions', dataset_id)}

    @app.put('/api/datasets/{dataset_id}/instructions')
    def put_instructions(dataset_id: str, body: TextInput, owner=Depends(auth)):
        _require_dataset(dataset_id, owner); require_level(owner, dataset_id, 'owner')  # Dataset owners and administrators.
        current = dataset_instructions(dataset_id)
        if body.expected_version is not None and body.expected_version != current['version']:
            raise HTTPException(409, 'The instructions changed since this proposal. Review the latest version first.')
        saved = _write('dataset_instructions', dataset_id, owner, body.text, INSTRUCTION_BYTES, body.summary)
        return saved | {'warnings': weakening_warnings(body.text)}

    @app.get('/api/datasets/{dataset_id}/prompt-guide')
    def get_dataset_guide(dataset_id: str, owner=Depends(auth)):
        _require_dataset(dataset_id, owner)
        return _read('dataset_prompt_guide', dataset_id) | {'limit_bytes': GUIDE_BYTES}

    @app.put('/api/datasets/{dataset_id}/prompt-guide')
    def put_dataset_guide(dataset_id: str, body: TextInput, owner=Depends(auth)):
        _require_dataset(dataset_id, owner); require_level(owner, dataset_id, 'owner')  # Dataset owners and administrators.
        return _write('dataset_prompt_guide', dataset_id, owner, body.text, GUIDE_BYTES, body.summary)

    @app.get('/api/models/{model_id}/prompt-guide')
    def get_model_guide(model_id: str, owner=Depends(auth)):
        record = routing.owned(model_id, owner, 'model')
        saved = _read('model_prompt_guide', record.id)
        default = model_guide({'model_name': record.name, 'settings': {}}) if not saved['text'] else ''
        return saved | {'default_text': default, 'limit_bytes': GUIDE_BYTES}

    @app.put('/api/models/{model_id}/prompt-guide')
    def put_model_guide(model_id: str, body: TextInput, owner=Depends(auth)):
        require_admin(owner); record = routing.owned(model_id, owner, 'model')
        return _write('model_prompt_guide', record.id, owner, body.text, GUIDE_BYTES, body.summary)
