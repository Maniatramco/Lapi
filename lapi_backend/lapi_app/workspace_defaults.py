"""Workspace Default models and the single active knowledge collection pointer.

One Default per role (Chat, Extraction, Embedding, OCR) lives in one database row so
every API pod and worker agree. Datasets may override Chat, Extraction and OCR; they
never choose an embedding model. The Embedding Default builds the one knowledge
index. Changing it deletes the current index immediately and reindexes every
document in the background. There is no rollback.
"""
import copy
import hashlib
import json
import time
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from . import core
from .database import timestamp_type

WORKSPACE = 'workspace'
ROLES = {'chat': 'chat_model_id', 'extraction': 'extraction_model_id', 'embedding': 'embedding_model_id', 'ocr': 'ocr_model_id'}
CONFIRMATION = 'I understand the knowledge index will be deleted and rebuilt'


class WorkspaceDefaults(core.Base):
    __tablename__ = 'lapi_workspace_defaults'
    workspace_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    chat_model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Added after the table existed; relational.upgrade_legacy adds it to older databases.
    ocr_model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Pinned model/profile versions of the Embedding Default (references only, no secrets).
    embedding_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The only knowledge collection any code path may write or read.
    active_collection: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Latest delete-and-reindex run: document -> job, errors, start time.
    reindex_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)


def _text(value):
    if value is None: return None
    return value.read() if hasattr(value, 'read') else value


def _ensure_row():
    for _ in range(2):
        try:
            with core.Session.begin() as session:
                if session.get(WorkspaceDefaults, WORKSPACE) is None:
                    session.add(WorkspaceDefaults(workspace_id=WORKSPACE, updated_at=time.time()))
            return
        except IntegrityError:
            continue  # Another pod created it first.


def _read():
    with core.Session() as session:
        row = session.get(WorkspaceDefaults, WORKSPACE)
        if row is None: return {}
        return {'chat': row.chat_model_id, 'extraction': row.extraction_model_id, 'embedding': row.embedding_model_id, 'ocr': row.ocr_model_id,
                'embedding_snapshot': json.loads(_text(row.embedding_snapshot_json)) if row.embedding_snapshot_json else None,
                'active_collection': row.active_collection,
                'reindex': json.loads(_text(row.reindex_json)) if row.reindex_json else None,
                'updated_at': row.updated_at, 'updated_by': row.updated_by}


def _write(actor=None, **values):
    _ensure_row()
    with core.Session.begin() as session:
        row = session.get(WorkspaceDefaults, WORKSPACE)
        for key, value in values.items(): setattr(row, key, value)
        row.updated_by = actor or row.updated_by; row.updated_at = time.time()


def space(snapshot):
    """Embedding space identity: same model weights, connection and chunking.

    Registration IDs, owners, credential and profile versions are not part
    of the space. Two equivalent registrations produce comparable vectors.
    """
    from . import dataset_models as routing
    cfg = (snapshot or {}).get('settings', {})
    ignored = {'timeout', 'top_k', 'search_provider'}
    values = {k: cfg.get(k) for k in routing.EMBED_KEYS if k not in ignored}
    values['model'] = (snapshot or {}).get('provider_model') or cfg.get('embedding_model')
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def same_space(first, second):
    return bool(first and second) and space(first) == space(second)


def legacy_spaces():
    """Distinct embedding spaces still recorded by dataset configurations."""
    with core.Session() as session:
        datasets = list(session.scalars(select(core.Record).where(core.Record.kind == 'knowledge_base').order_by(core.Record.created_at, core.Record.id)))
    spaces = {}
    for dataset in datasets:
        try: data = core.store.json(dataset.ref)
        except FileNotFoundError: continue
        snapshot = data.get('embedding_snapshot'); model_id = data.get('embedding_model_id')
        if not snapshot or not model_id: continue
        key = space(snapshot); found = spaces.get(key)
        newer = (snapshot.get('model_version') or 0, snapshot.get('connection_profile_version') or 0)
        if not found or newer > (found[1].get('model_version') or 0, found[1].get('connection_profile_version') or 0):
            spaces[key] = (model_id, snapshot, [dataset.id] + (found[2] if found else []))
        else: found[2].append(dataset.id)
    return list(spaces.values())


def embedding():
    """{'model_id', 'snapshot'} of the Embedding Default, or None.

    Migration: when no Default is saved and every dataset already uses one
    embedding space, adopt it once. Different spaces need an admin choice.
    """
    saved = _read()
    if saved.get('embedding') and saved.get('embedding_snapshot'):
        return {'model_id': saved['embedding'], 'snapshot': saved['embedding_snapshot']}
    spaces = legacy_spaces()
    if len(spaces) != 1: return None
    model_id, snapshot, _ = spaces[0]
    _ensure_row()
    with core.Session.begin() as session:
        result = session.execute(update(WorkspaceDefaults).where(WorkspaceDefaults.workspace_id == WORKSPACE,
            WorkspaceDefaults.embedding_model_id.is_(None)).values(embedding_model_id=model_id,
            embedding_snapshot_json=json.dumps(snapshot), updated_at=time.time()))
    if not result.rowcount: return embedding()
    return {'model_id': model_id, 'snapshot': snapshot}


def unset_message():
    if len(legacy_spaces()) > 1:
        return ('Datasets currently use different embedding models. Choose the workspace Default embedding model in Model Registration; '
                'the other documents are then reindexed into the one knowledge index.')
    return 'Choose a Default embedding model in Model Registration before indexing documents or asking questions.'


def current():
    saved = _read(); pinned = embedding()
    return {'chat': saved.get('chat'), 'extraction': saved.get('extraction'), 'embedding': pinned['model_id'] if pinned else None, 'ocr': saved.get('ocr')}


def default_id(role):
    if role == 'embedding':
        pinned = embedding(); return pinned['model_id'] if pinned else None
    return _read().get(role)


def roles_of(model_id):
    values = current()
    return [role for role, value in values.items() if value == model_id]


def active_collection():
    return _read().get('active_collection')


def claim_collection(name):
    """Set the active pointer only while none is set. Returns True on success."""
    _ensure_row()
    with core.Session.begin() as session:
        result = session.execute(update(WorkspaceDefaults).where(WorkspaceDefaults.workspace_id == WORKSPACE,
            WorkspaceDefaults.active_collection.is_(None)).values(active_collection=name, updated_at=time.time()))
    return result.rowcount == 1


def verified(model):
    """Registrations need a passing connection test for their current version.

    Models created from deployment connection profiles (legacy catalog and
    migrated settings) have no test endpoint and are verified by deployment.
    """
    from . import dataset_models as routing
    data = routing.model_data(model)
    with core.Session() as session: profile = session.get(core.Record, data.get('connection_profile_id'))
    if profile is None: return False
    try: registration = core.local_store.json(profile.ref).get('registration_model_id')
    except FileNotFoundError: return False
    if not registration: return True
    test = data.get('connection_test') or {}
    return test.get('connection_profile_version') == data.get('connection_profile_version')


def require_eligible(model, role):
    from . import dataset_models as routing
    if model is None or model.kind != 'model': raise HTTPException(404, 'Model not found.')
    data = routing.model_data(model)
    if data.get('archived') or not data.get('enabled', True) or role not in data.get('capabilities', []):
        raise HTTPException(409, 'Only an enabled ' + role + ' model can be the ' + role.title() + ' Default.')
    profile = routing.owned(data['connection_profile_id'], model.owner, 'config_profile')
    cfg = routing.profile_snapshot(profile, data.get('connection_profile_version'))['settings']
    if role == 'embedding' and cfg.get('embedding_connection') and cfg['search_provider'] == 'oci':
        raise HTTPException(400, 'Registered embedding connections require Local or Qdrant vector storage. OCI managed retrieval owns its embedding configuration.')
    try: core.enforce_local_only(cfg)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc
    if not verified(model):
        raise HTTPException(409, 'Test the connection of ' + model.name + ' in Model Registration and save it before making it a Default.')
    if role == 'ocr':
        from .lapi_models import cloud_ocr
        if not cloud_ocr.ready(data, {'settings': cfg, 'provider_model': data['provider_model']}):
            raise HTTPException(409, model.name + ' cannot be the OCR Default yet. OCR needs an OpenAI or Gemini model whose Test connection read the sample image; test it with OCR ticked and save.')
    return data


def pin_embedding(model):
    from . import dataset_models as routing
    data = routing.model_data(model)
    profile = routing.owned(data['connection_profile_id'], model.owner, 'config_profile')
    snapshot = routing.profile_snapshot(profile, data.get('connection_profile_version'))
    snapshot.update(model_id=model.id, model_name=model.name, model_version=model.version, provider_model=data['provider_model'], capability='embedding')
    snapshot['settings']['embedding_model'] = data['provider_model']
    return snapshot


def execution(snapshot):
    """Workspace embedding execution settings from a pinned snapshot (no dataset parts)."""
    from . import dataset_models as routing
    from .database_control import vector_backend
    snapshot = copy.deepcopy(snapshot)
    cfg = core.settings().copy(); cfg.update({k: snapshot['settings'][k] for k in routing.EMBED_KEYS if k in snapshot['settings']})
    transport = vector_backend()
    if transport: cfg['search_provider'] = transport
    cfg['_ocr_cloud_only'] = True
    if cfg['embedding_provider'] == 'ollama':
        from .ollama_provider import model_digest, OllamaError
        try:
            with core.execution_context(dict(snapshot, settings=cfg)): cfg['_embedding_digest'] = model_digest(cfg['embedding_model'])
        except OllamaError as error: raise HTTPException(409, str(error))
    snapshot['settings'] = cfg
    return snapshot


def embedding_execution():
    """Resolved Embedding Default, enforcing that it is still enabled and unchanged."""
    from . import dataset_models as routing
    pinned = embedding()
    if not pinned: raise HTTPException(409, unset_message())
    model = routing.model_record(pinned['model_id'])
    if not model or model.kind != 'model':
        raise HTTPException(409, 'The Default embedding model is no longer registered. Choose another Default in Model Registration.')
    data = routing.model_data(model)
    if data.get('archived') or not data.get('enabled', True) or 'embedding' not in data.get('capabilities', []):
        raise HTTPException(409, 'The Default embedding model is unavailable. Choose another Default in Model Registration.')
    snapshot = pinned['snapshot']
    # Legacy catalog models follow their profile's latest version.
    profile_version = data.get('connection_profile_version')
    if profile_version is None:
        with core.Session() as session: profile = session.get(core.Record, data.get('connection_profile_id'))
        profile_version = profile.version if profile else None
    if model.version != snapshot.get('model_version') or profile_version != snapshot.get('connection_profile_version'):
        raise HTTPException(409, 'Embedding model configuration changed. Re-apply it as the workspace Default in Model Registration to delete and rebuild the knowledge index.')
    return execution(snapshot)


def guard_disable(model_id):
    """The current Default of any role stays enabled until another is chosen."""
    roles = roles_of(model_id)
    if roles:
        raise HTTPException(409, 'This model is the workspace ' + ', '.join(r.title() for r in roles) + ' Default. Choose another Default before disabling it.')


def record_test(model_id, profile_version):
    """Persist a passing connection test for a saved registration version."""
    from . import dataset_models as routing
    with core.document_lock('model-' + model_id):
        with core.Session() as session: model = session.get(core.Record, model_id)
        if model is None: return
        data = routing.model_data(model)
        if data.get('connection_profile_version') != profile_version: return
        data['connection_test'] = {'connection_profile_version': profile_version, 'passed_at': time.time()}
        core.store.put_json(model.ref, data)


# ---------------------------------------------------------------- reindex run

def _datasets():
    with core.Session() as session:
        return list(session.scalars(select(core.Record).where(core.Record.kind == 'knowledge_base').order_by(core.Record.created_at, core.Record.id)))


def _documents(dataset_ids):
    if not dataset_ids: return []
    with core.Session() as session:
        return list(session.scalars(select(core.Record).where(core.Record.kind == 'document', core.Record.parent_id.in_(list(dataset_ids)),
            core.Record.status != 'deleting').order_by(core.Record.created_at, core.Record.id)))


def impact():
    from . import knowledge_catalog as catalog
    datasets = _datasets(); documents = _documents([d.id for d in datasets])
    active = active_collection()
    return {'datasets': len(datasets), 'documents': len(documents), 'knowledge_items': catalog.entity_count(active) if active else 0}


def reindex_status():
    run = _read().get('reindex')
    if not run: return None
    jobs = run.get('jobs', {}); errors = run.get('errors', {})
    ids = list(jobs.values()); documents = list(jobs) + list(errors)
    with core.Session() as session:
        found = {}; records = {}
        for start in range(0, len(ids), 500):
            found.update({j.id: j for j in session.scalars(select(core.Job).where(core.Job.id.in_(ids[start:start+500])))})
        for start in range(0, len(documents), 500):
            records.update({r.id: r for r in session.scalars(select(core.Record).where(core.Record.id.in_(documents[start:start+500])))})
    indexed = pending = 0; failures = []
    for document_id, job_id in jobs.items():
        record = records.get(document_id)
        if record is None or record.status == 'deleting': continue
        job = found.get(job_id); status = job.status if job else 'failed'
        if status == 'completed': indexed += 1
        elif status in ('failed', 'cancelled'):
            failures.append({'document_id': document_id, 'name': record.name, 'dataset_id': record.parent_id,
                             'error': (job.error if job else '') or record.error or 'Indexing did not finish.'})
        else: pending += 1
    for document_id, error in errors.items():
        record = records.get(document_id)
        if record is None or document_id in jobs: continue
        failures.append({'document_id': document_id, 'name': record.name, 'dataset_id': record.parent_id, 'error': error})
    return {'started_at': run.get('started_at'), 'model_id': run.get('model_id'), 'model_name': run.get('model_name'),
            'total': indexed + pending + len(failures), 'indexed': indexed, 'pending': pending, 'failed': len(failures), 'failures': failures}


def _enqueue(documents, allow_external, run):
    """Background index job per document, pinned to its dataset's new snapshot."""
    from . import dataset_models as routing, main
    snapshots = {}
    for document in documents:
        try:
            if document.parent_id not in snapshots:
                with core.Session() as session: dataset = session.get(core.Record, document.parent_id)
                snapshots[document.parent_id] = routing.embedding_snapshot(dataset)
            snapshot = snapshots[document.parent_id]
            with core.document_lock('submit-' + document.id):
                with core.Session.begin() as session:
                    for job in session.scalars(select(core.Job).where(core.Job.target_id == document.id, core.Job.kind == 'index', core.Job.status.in_(['queued', 'running']))):
                        job.status = 'cancelled'; job.lease_token = ''; job.lease_until = 0; job.error = 'Superseded by the knowledge index rebuild.'
                    current = session.get(core.Record, document.id)
                    if current is None or current.status == 'deleting': continue
                    current.status = 'queued'; current.error = ''
                job = main.enqueue(document.owner, 'index', document.id, allow_external, snapshot)
            run['jobs'][document.id] = job.id; run['errors'].pop(document.id, None)
        except HTTPException as exc:
            run['errors'][document.id] = str(exc.detail)[:400]
        except Exception:
            run['errors'][document.id] = 'Reindexing could not be queued. Retry from the knowledge index banner.'
    return run


def unified_name(target):
    """The one collection this embedding builds; None for OCI managed retrieval,
    which keeps its own per-document indexes."""
    from . import knowledge
    try: return knowledge.unified(target)['knowledge_collection']
    except HTTPException: return None


def change_embedding(model, actor, acknowledged=False, allow_external=False):
    from . import dataset_models as routing, knowledge, main
    with core.document_lock('workspace-defaults'):
        snapshot = pin_embedding(model)
        previous = embedding()
        datasets = _datasets()
        target = execution(snapshot)
        name = unified_name(target)
        active = active_collection()
        # Re-applying the same Default is a no-op unless its index changed,
        # for example after new local weights (another Ollama digest).
        if previous and previous['model_id'] == model.id and previous['snapshot'] == snapshot and active in (None, name):
            return public()
        # A real change deletes the whole index. Migration (no Default yet)
        # keeps the chosen space's collection and reindexes the other datasets.
        rebuild = previous is not None
        stale = [d for d in datasets if rebuild or not same_space(routing.dataset_config(d).get('embedding_snapshot'), snapshot)]
        documents = _documents([d.id for d in stale])
        if (rebuild or documents) and not acknowledged:
            counts = impact()
            raise HTTPException(409, f'Confirm "{CONFIRMATION}". The current index ({counts["documents"]} documents, '
                                     f'{counts["knowledge_items"]} knowledge items) is deleted now and rebuilt with {model.name}.')
        if documents: main.external_check(allow_external, True, target['settings'])
        with core.Session() as session:
            if session.scalar(select(core.Job.id).where(core.Job.kind == 'extract', core.Job.status.in_(['queued', 'running', 'blocked'])).limit(1)):
                raise HTTPException(409, 'Wait for active extraction jobs to finish before changing the Default embedding model.')
        # Delete first. Readers then see an empty, building index, never the old one.
        knowledge.remove_collections(keep=None if rebuild else name, settings=target['settings'])
        run = {'started_at': time.time(), 'model_id': model.id, 'model_name': model.name, 'jobs': {}, 'errors': {}}
        _write(actor, embedding_model_id=model.id, embedding_snapshot_json=json.dumps(snapshot), active_collection=name,
               reindex_json=json.dumps(run))
        for dataset in stale:
            data = routing.dataset_config(dataset)
            routing.write_version(dataset, data | {'embedding_model_id': model.id, 'embedding_snapshot': snapshot,
                                                   'index_generation': routing.generation(data) + 1})
        _enqueue(documents, allow_external, run)
        _write(actor, reindex_json=json.dumps(run))
        return public()


def set_default(model_id, role, actor, acknowledged=False, allow_external=False):
    from . import dataset_models as routing
    model = routing.owned(model_id, actor, 'model')
    require_eligible(model, role)
    if role == 'embedding':
        return change_embedding(model, actor, acknowledged, allow_external)
    with core.document_lock('workspace-defaults'):
        _write(actor, **{ROLES[role]: model.id})
    return public()


def replace_default(role, model_id, actor):
    """Operator consolidation: rebind a Chat or Extraction Default to its replacement."""
    with core.document_lock('workspace-defaults'):
        _write(actor, **{ROLES[role]: model_id})


def replace_embedding(model, actor):
    """Operator consolidation: rebind the Embedding Default and delete the old index.

    The caller must reindex every affected document (consolidation queues them).
    """
    from . import knowledge
    with core.document_lock('workspace-defaults'):
        snapshot = pin_embedding(model)
        previous = embedding()
        if previous and previous['snapshot'] == snapshot: return
        target = execution(snapshot)
        name = unified_name(target)
        knowledge.remove_collections(keep=None, settings=target['settings'])
        _write(actor, embedding_model_id=model.id, embedding_snapshot_json=json.dumps(snapshot), active_collection=name, reindex_json=None)


def bootstrap_embedding(model, actor):
    """First Embedding Default chosen while saving a dataset mapping."""
    require_eligible(model, 'embedding')
    snapshot = pin_embedding(model)
    _ensure_row()
    with core.Session.begin() as session:
        session.execute(update(WorkspaceDefaults).where(WorkspaceDefaults.workspace_id == WORKSPACE,
            WorkspaceDefaults.embedding_model_id.is_(None)).values(embedding_model_id=model.id,
            embedding_snapshot_json=json.dumps(snapshot), updated_by=actor, updated_at=time.time()))
    return embedding()


def retry(actor, allow_external=False):
    from . import main
    with core.document_lock('workspace-defaults'):
        saved = _read(); run = saved.get('reindex'); status = reindex_status()
        if not run or not status or not status['failures']: return public()
        pinned = embedding()
        if pinned: main.external_check(allow_external, True, execution(pinned['snapshot'])['settings'])
        with core.Session() as session:
            documents = list(session.scalars(select(core.Record).where(core.Record.id.in_([f['document_id'] for f in status['failures']]))))
        run.setdefault('errors', {})
        _enqueue(documents, allow_external, run)
        _write(actor, reindex_json=json.dumps(run))
    return public()


def public(actor=None):
    from . import knowledge
    values = current()
    status = knowledge.index_status(actor)
    return {'chat_model_id': values['chat'], 'extraction_model_id': values['extraction'], 'embedding_model_id': values['embedding'], 'ocr_model_id': values['ocr'],
            'index': status, 'impact': impact(), 'confirmation': CONFIRMATION}


class DefaultInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['chat', 'extraction', 'embedding', 'ocr']
    acknowledge_index_rebuild: bool = False
    allow_external: bool = False


class RetryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    allow_external: bool = False


def install(app, auth):
    from . import dataset_access as access

    @app.get('/api/workspace/defaults')
    def defaults(actor=Depends(auth)):
        return public(actor)

    @app.put('/api/model-registrations/{id}/default')
    def choose(id: str, body: DefaultInput, actor=Depends(auth)):
        access.require_admin(actor)
        set_default(id, body.role, actor, body.acknowledge_index_rebuild, body.allow_external)
        return public(actor)

    @app.get('/api/workspace/knowledge-index')
    def index(actor=Depends(auth)):
        from . import knowledge
        return knowledge.index_status(actor)

    @app.post('/api/workspace/knowledge-index/retry')
    def retry_failed(body: RetryInput, actor=Depends(auth)):
        access.require_admin(actor)
        retry(actor, body.allow_external)
        return public(actor)

    @app.post('/api/workspace/knowledge-index/remove-orphans')
    def orphans(actor=Depends(auth)):
        access.require_admin(actor)
        from . import knowledge
        return knowledge.remove_orphans()
