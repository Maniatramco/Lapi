"""Per-person answers to the "Let's set you up" questions, used to suggest next steps.

Stored in the control store (not the browser), so the answers follow the person to
another browser or device. Only fixed choices are accepted; nothing free-form is kept.
"""
import hashlib
import time
from typing import List, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from . import core

Goal = Literal['ask', 'extract', 'research', 'knowledge_base']
Source = Literal['files', 'google_drive', 'sharepoint', 's3', 'azure_blob', 'gcs', 'oci_object', 'not_sure']
GOALS = ('ask', 'extract', 'research', 'knowledge_base')
SOURCES = ('files', 'google_drive', 'sharepoint', 's3', 'azure_blob', 'gcs', 'oci_object', 'not_sure')


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    goals: List[Goal] = Field(default_factory=list, max_length=len(GOALS))
    sources: List[Source] = Field(default_factory=list, max_length=len(SOURCES))
    completed: bool = False
    dismissed_next_steps: bool = False


def _key(user_id: str) -> str:
    return f'preferences/{hashlib.sha256(str(user_id).encode()).hexdigest()}.json'


def _unique(values, allowed):
    return [value for value in allowed if value in values]


def _load(user_id: str) -> dict:
    blank = Preferences().model_dump()
    try:
        data = core.local_store.json(_key(user_id))
    except Exception:  # missing or unreadable record: nothing answered yet
        return blank
    if not isinstance(data, dict):
        return blank
    try:
        saved = Preferences.model_validate({k: data[k] for k in blank if k in data})
    except Exception:
        return blank
    return _clean(saved)


def _clean(body: Preferences) -> dict:
    return {
        'goals': _unique(body.goals, GOALS),
        'sources': _unique(body.sources, SOURCES),
        'completed': body.completed,
        'dismissed_next_steps': body.dismissed_next_steps,
    }


def install(app, auth):
    router = APIRouter()

    @router.get('/api/me/preferences')
    def read_preferences(owner=Depends(auth)):
        return _load(owner)

    @router.put('/api/me/preferences')
    def save_preferences(body: Preferences, owner=Depends(auth)):
        record = _clean(body)
        core.local_store.put_json(_key(owner), {**record, 'updated_at': int(time.time())})
        return record

    app.include_router(router)
