"""Per-user record of the 1-minute product tour, so it shows once after sign-in.

The flag lives in the control store (not the browser), so a second browser or device
does not replay the tour. Raising TOUR_VERSION shows a new tour to everyone once.
"""
import hashlib
import re
import time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from . import core

TOUR_VERSION = 3
TRAINING_VERSION = 2  # The short in-agent training (agent-training.tsx).
_SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')


class MarkSeen(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1, le=10_000)


def _key(user_id: str, kind: str = 'walkthrough') -> str:
    name = user_id if _SAFE_ID.fullmatch(user_id or '') else hashlib.sha256(str(user_id).encode()).hexdigest()
    return f'{kind}/{name}.json'


def _seen_version(user_id: str, kind: str = 'walkthrough') -> int:
    try:
        data = core.local_store.json(_key(user_id, kind))
    except Exception:  # missing or unreadable record: treat as not seen
        return 0
    value = data.get('version') if isinstance(data, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def install(app, auth):
    router = APIRouter()

    @router.get('/api/me/walkthrough')
    def walkthrough_status(owner=Depends(auth)):
        return {'seen': _seen_version(owner) >= TOUR_VERSION, 'version': TOUR_VERSION}

    @router.get('/api/me/agent-training')
    def training_status(owner=Depends(auth)):
        return {'seen': _seen_version(owner, 'agent-training') >= TRAINING_VERSION, 'version': TRAINING_VERSION}

    @router.post('/api/me/agent-training')
    def mark_training_seen(body: MarkSeen, owner=Depends(auth)):
        version = max(_seen_version(owner, 'agent-training'), min(body.version, TRAINING_VERSION))
        core.local_store.put_json(_key(owner, 'agent-training'), {'version': version, 'seen_at': time.time()})
        return {'seen': version >= TRAINING_VERSION, 'version': TRAINING_VERSION}

    @router.post('/api/me/walkthrough')
    def mark_walkthrough_seen(body: MarkSeen, owner=Depends(auth)):
        version = max(_seen_version(owner), min(body.version, TOUR_VERSION))
        core.local_store.put_json(_key(owner), {'version': version, 'seen_at': int(time.time())})
        return {'seen': version >= TOUR_VERSION, 'version': TOUR_VERSION}

    app.include_router(router)
