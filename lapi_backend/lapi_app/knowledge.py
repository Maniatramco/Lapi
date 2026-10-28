"""Unified, rebuildable semantic index. SQL/files remain authoritative.

Exactly one collection is active per workspace, built by the Default embedding
model. Its catalog of entities and points lives in the control database so all
API pods and workers share it. No conversation text, credentials or arbitrary configuration bodies enter this
index. Every hit is reconstructed from its current authorized canonical source.
"""
import copy
import hashlib
import json
import re
import time
import uuid
from types import SimpleNamespace
from sqlalchemy import select
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from . import core, dataset_models as routing, dataset_access as access, providers, runtime_config
from . import knowledge_catalog as catalog

TYPES = {'dataset', 'document', 'document_chunk', 'extraction', 'prompt', 'model', 'workflow', 'application'}
KINDS = {'knowledge_base', 'document', 'extraction', 'template', 'model', 'agent_plan', 'agent_onboarding'}
SCHEMA_VERSION = 1
PUBLICATION_VERSION = 3
TEXT_BYTES = 2400
GUIDE = {
    'cloud_sources': 'Any signed-in user can choose Dashboard > Add new knowledge to connect Amazon S3, SharePoint, Google Drive, Azure Blob Storage or OCI Object Storage to a dataset they can access. Each connection belongs to the user who saved it; administrators can see all connections. Connections use read-only AWS access keys or server IAM identity, a Microsoft Entra application, a Google service-account JSON key shared onto the selected Drive folder, an Azure container SAS token limited to read and list, or an OCI customer secret key for the S3-compatible endpoint. Test the connection, browse the configured folder or prefix, select up to 20 supported files and choose Vectorize after confirming that authorized dataset users may read the copies and allowing any external processing. Vectorize indexes copies with the workspace Default embedding model; they become usable in Agent and Dataset Knowledge Chat only after indexing succeeds. Extraction and review stay separate. Google Docs export as DOCX and Sheets/Slides as PDF. PDF, DOCX, TXT and JSON are supported. Imports are snapshots: source ACLs, deletes and updates are not automatically synchronized, disabled connections do not remove copies, and changed content creates another retained copy. Credentials never enter chat. Scheduled sync and delegated user sign-in are unavailable.',
    'datasets': 'Create a dataset with a name, optional description and optional chat and extraction model choices in New dataset; without a choice the workspace Default is used. Every dataset is indexed by the one workspace Default embedding model. Dataset onboarding alone does not upload documents, save a prompt or run extraction. Lapi Agent can collect these separately when explicitly requested. Dataset access governs shared documents and results.',
    'documents': 'Upload PDF, DOCX, TXT, JSON or image (PNG, JPG, WEBP) documents to a selected dataset; images are read with the dataset OCR model. Originals remain in their configured persistent file storage. Parsing or configured OCR creates text chunks; the workspace Default embedding model publishes searchable knowledge once into the one knowledge index. A ready indexed document does not mean field extraction has run. A prompt JSON file belongs to Prompt templates, not the document upload input.',
    'extraction': 'Select the dataset, documents, saved prompt and mapped extraction model, then confirm extraction. Lapi retrieves and reranks evidence, extracts fields, validates JSON Schema and saves versioned JSON and Parquet results. Re-extract uses saved documents and a selected prompt while preserving earlier results. A question about extraction does not authorize running it.',
    'review': 'Review filters saved runs by dataset, prompt template and extraction. Open a run to compare extracted fields with its unchanged source document side by side. Reload retrieves saved values; Download exports saved results. Reviewed saves checked values and permanently locks that extraction. Re-extract is available from the Review list and creates a separate result. Citations show recorded evidence; missing source locations are never guessed.',
    'models': 'Model Registration defines embedding, chat and extraction profiles under Manage workspace. An administrator marks one tested model per role as the workspace Default; datasets may override Chat and Extraction only. Changing the Default embedding model deletes the knowledge index and reindexes every document in the background. LangGraph orchestrates agents. Chat and extraction profiles may use the same weights with different limits. Actual endpoints, limits and availability come from configured model metadata, not assumptions in this guide.',
    'storage': 'Storage manages file storage, database and vector destinations and required connection settings. The Connections footer identifies Local or OCI for Storage, Database, Vector DB, FastAPI, WebApp, Worker and AI models. Existing deployments can use OCI files and Oracle vectors while AI models remain on a laptop through a private relay. Read configured destinations to report actual placement. Credentials are encrypted and must never appear in chat or the knowledge index.',
    'knowledge': 'Lapi Agent can explain Lapi, help onboard datasets and map models, upload and index documents, work with prompt templates, extract or re-extract fields, summarize or search saved knowledge, compare results, inspect Review and export saved results. Every chat question uses access-scoped hybrid vector and keyword retrieval, then CPU reranking, then a model answer and citation validation. Lapi help uses indexed application guidance; document and result questions retain dataset and document filters. Exact counts and complete lists use complete authorized published catalog facts in addition to ranked evidence. Previous chat text is not indexed knowledge. No web search or implicit processing is available.',
    'recovery': 'Confirmed processing jobs persist beyond the browser. Retry resumes accepted processing; restart repeats the confirmed workflow while preserving originals and earlier results. Chat questions do not start processing. Upload and extraction workflows require their existing confirmation. Laptop-hosted AI requires the laptop and relay to stay online; connection failures produce recoverable errors without switching to paid models.',
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def fragments(text):
    # Split without breaking UTF-8 and without losing the tail of long fields.
    current = []; size = 0
    for char in text:
        length = len(char.encode())
        if size + length > TEXT_BYTES:
            yield ''.join(current); current = []; size = 0
        current.append(char); size += length
    if current: yield ''.join(current)


def payload_metadata(value):
    """Preserve exact audit/OCR metadata through vector backends' JSON codecs.

    Qdrant may round floating-point payload numbers during a JSON round trip.
    Business values remain numeric in the canonical JSON text, which assemble()
    decodes. Only auxiliary metadata floats use lossless decimal strings.
    """
    if isinstance(value,float):return repr(value)
    if isinstance(value,dict):return {key:payload_metadata(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [payload_metadata(item) for item in value]
    return value


def point(source_type, entity_id, dataset_id, owner, title, text, version=1, **extra):
    pieces=list(fragments(text))
    for part, excerpt in enumerate(pieces):
        payload = dict(source_type=source_type, entity_id=entity_id, dataset_id=dataset_id or '',
            owner_id=owner, title=title, text=excerpt, source_version=version, part=part, part_count=len(pieces), **payload_metadata(extra))
        payload['content_digest'] = digest(payload)
        id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'lapi-knowledge:{source_type}:{entity_id}:{version}:{part}'))
        yield {'id': id, 'payload': payload}


def application_sources():
    return [p for topic, text in GUIDE.items() for p in point('application', topic, '', '', 'Lapi · '+topic, text)]

def call_extraction_ids(call):
    result=call.get('result',{})
    return [e['extraction_id'] for e in result.get('extractions',[]) if not e.get('superseded')] or ([result['extraction_id']] if result.get('extraction_id') else [])


def record_sources(record):
    """Explicit allowlisted fields, never a generic dump of stored artifacts."""
    if record.kind not in KINDS: return []
    title = record.name or record.id; base = dict(status=record.status,source_updated_at=record.updated_at)
    if record.kind == 'model':
        data = routing.model_public(record)
        if data.get('archived') or not data.get('enabled', True): return []
        fields = {k: data.get(k) for k in ('name', 'provider_model', 'provider', 'capabilities', 'context_limit', 'max_output_tokens', 'timeout', 'enabled')}
        return list(point('model', record.id, '', record.owner, title, encoded(fields), record.version, **base))
    data = {} if record.kind=='document' else core.store.json(record.ref)
    dataset_id = record.id if record.kind == 'knowledge_base' else record.parent_id or ''
    if record.kind == 'knowledge_base':
        fields = {'name': title, 'description': data.get('description', ''), 'active': data.get('active', True),
            'embedding_model_id': data.get('embedding_model_id'), 'chat_model_id': data.get('default_chat_model_id'),
            'extraction_model_id': data.get('default_extraction_model_id')}
        return list(point('dataset', record.id, dataset_id, record.owner, title, encoded(fields), record.version, **base))
    if record.kind == 'document':
        output = list(point('document', record.id, dataset_id, record.owner, title,
            encoded({'filename': title, 'size': record.size, 'status': record.status, 'version': record.version}), record.version, document_ids=[record.id], **base))
        if record.status == 'ready':
            try: chunks = core.store.json('documents/'+record.id+'/chunks.json')['chunks']
            except FileNotFoundError: chunks = []
            for chunk in chunks:
                # Existing immutable chunk ID distinguishes pages within a document.
                output.extend(point('document_chunk', record.id+':'+chunk['id'], dataset_id, record.owner, title,
                    chunk['text'], record.version, document_ids=[record.id], document_id=record.id,
                    chunk_id=chunk['id'], page=chunk.get('page'), ocr=chunk.get('ocr'), **base))
        return output
    if record.kind == 'template':
        fields = {'filename': data.get('source_filename') or title, 'schema': data.get('schema', {}), 'instructions': data.get('instruction') or data.get('instructions', '')}
        return list(point('prompt', record.id, dataset_id, record.owner, title, encoded(fields), record.version, **base))
    if record.kind == 'agent_onboarding':
        fields={'name':data['name'],'status':data['status'],'dataset_id':data.get('dataset_id'),
            'steps':[{'label':s['label'],'status':s['status']} for s in data['steps']],
            'document_ids':data.get('document_ids',[]),'extraction_ids':data.get('extraction_ids',[]),
            'prompt_id':data.get('template_id'),'models':data.get('models',{})}
        return list(point('workflow',record.id,data.get('dataset_id',''),record.owner,title,encoded(fields),record.version,private=True,**base))
    if record.kind == 'agent_plan':
        if not data.get('calls'): return []
        fields = {'workflow_id': record.id, 'document_ids':data.get('document_ids',[]),'steps': [{'tool': c.get('tool'), 'status': c.get('status'), 'error': c.get('error','')[:300],
            'extraction_ids':call_extraction_ids(c)} for c in data.get('calls', [])],
            'goal_status': data.get('goal', {}).get('status')}
        return list(point('workflow', record.id, dataset_id or data.get('dataset_id', ''), record.owner, title,
            encoded(fields), record.version, private=True, **base))
    if record.kind == 'extraction':
        from .parquet_results import load
        documents = data.get('document_ids', [])
        extra = dict(document_ids=documents, merged_document_id=(data.get('merge') or {}).get('document_id'),review_status=data.get('review_status', 'unreviewed'), **base)
        output = list(point('extraction', record.id, dataset_id, record.owner, title,
            encoded({'extraction_id': record.id, 'name': title, 'status': record.status, 'review_status': extra['review_status']}), record.version, record_index=-1, **extra))
        if record.status != 'ready': return output
        result = load(data).get('result')
        items = result.get('records', []) if isinstance(result, dict) and isinstance(result.get('records'), list) else [{'fields': result}]
        for index, item in enumerate(items):
            fields = item.get('fields', item) if isinstance(item, dict) else item
            # Each result record is separately discoverable; complete exact values
            # remain in Parquet and are read by read_extraction_results.
            output.extend(point('extraction', record.id+':record:'+str(index), dataset_id, record.owner, title,
                encoded({'source_filename': item.get('source_filename') if isinstance(item, dict) else None, 'fields': fields}), record.version,
                extraction_id=record.id, record_index=index, **extra))
        return output
    return []


def eligible(actor, dataset_id='', document_ids=None):
    if dataset_id: access.get_record(dataset_id, actor, 'knowledge_base')
    selected = set(document_ids or [])
    for id in selected:
        doc = access.get_record(id, actor, 'document')
        if not dataset_id or doc.parent_id != dataset_id: raise HTTPException(400, 'Selected document is outside the selected dataset.')
    with core.Session() as session:
        datasets = access.dataset_ids(actor, session)
        records = session.scalars(select(core.Record).where(core.Record.kind.in_(KINDS))).all()
        result = []
        for record in records:
            if not access.allowed(record, actor, session, datasets): continue
            if record.kind=='agent_plan':
                if record.status=='query':continue
                saved=core.store.json(record.ref)
                status='workflow' if saved.get('calls') else 'query'
                if record.status!=status:
                    with core.Session.begin() as update_session:update_session.get(core.Record,record.id).status=status
                    record.status=status
                if status=='query':continue
            scope = record.id if record.kind == 'knowledge_base' else record.parent_id
            if record.kind in ('agent_plan','agent_onboarding') and not scope:
                scope=core.store.json(record.ref).get('dataset_id','')
                if scope in datasets:
                    with core.Session.begin() as update_session:update_session.get(core.Record,record.id).parent_id=scope
                    record.parent_id=scope
            if dataset_id and record.kind != 'model' and scope not in ('', dataset_id): continue
            if selected and record.kind == 'document' and record.id not in selected: continue
            if selected and record.kind == 'extraction':
                data = core.store.json(record.ref)
                if not set(data.get('document_ids', [])) <= selected: continue
            result.append(record)
    return result


VECTOR_PROVIDERS = ('qdrant', 'oracle')
GUARDRAIL = ('A different knowledge collection is active. Re-apply the Default embedding model in Model Registration to delete and '
             'rebuild the knowledge index; a second active collection is never created.')


def unified(snapshot):
    """One compatible embedding space for every dataset: the unified collection."""
    cfg = copy.deepcopy(snapshot['settings'])
    if cfg['embedding_provider'] not in ('ollama', 'mock', 'sentence_transformers', 'openai', 'registered') or cfg['search_provider'] not in ('qdrant', 'oracle', 'local'):
        raise HTTPException(409, 'The Default embedding model needs Local, Qdrant, or Oracle vector storage for unified semantic search.')
    cfg['_index_namespace'] = 'unified-knowledge-v1'
    cfg['embedding_extra_parameters'] = {k: v for k, v in cfg.get('embedding_extra_parameters', {}).items() if k != 'truncate'}
    value = dict(snapshot, settings=cfg)
    signature = digest({'schema': SCHEMA_VERSION, 'embedding': providers.fingerprint(cfg)})[:20]
    value['knowledge_collection'] = 'lapi_knowledge_'+signature
    return value


def embedding_snapshot(actor, dataset_id=''):
    candidates = [routing.owned(dataset_id, actor, 'knowledge_base')] if dataset_id else routing.rows(actor, 'knowledge_base')
    for dataset in candidates:
        try: return unified(routing.embedding_snapshot(dataset))
        except HTTPException: continue
    if not dataset_id:
        # Application guidance and catalogs need no dataset: use the workspace Default.
        from . import workspace_defaults
        try: return unified(workspace_defaults.embedding_execution())
        except HTTPException: pass
    raise HTTPException(409, 'Choose a Default embedding model with Local, Qdrant, or Oracle vector storage in Model Registration before using unified semantic search.')


def _manifest_ref(snapshot):
    """Legacy pod-local manifest path; read once for migration into the catalog."""
    name = snapshot if isinstance(snapshot, str) else snapshot['knowledge_collection']
    return 'knowledge/'+name+'/manifest.json'


def _import_legacy(name):
    """One-time move of a pod-local manifest into the shared database catalog."""
    if catalog.exists(name): return
    ref = _manifest_ref(name)
    try: legacy = core.local_store.json(ref)
    except (FileNotFoundError, ValueError): return
    with core.document_lock('unified-knowledge-'+name):
        if catalog.exists(name): return
        points = legacy.get('points', {}); vectors = legacy.get('vectors', {})
        upserts = []
        for key, entry in legacy.get('entities', {}).items():
            owned = {id: points[id] for id in entry.get('ids', []) if id in points}
            upserts.append((key, entry, owned, {id: vectors[id] for id in owned if id in vectors} or None))
        catalog.apply(name, upserts, failures=legacy.get('failures', []))
        core.local_store.delete(ref)


def manifest(snapshot, vectors=False):
    """Shared catalog view of a collection: {'entities', 'points', 'failures'}."""
    name = snapshot if isinstance(snapshot, str) else snapshot['knowledge_collection']
    _import_legacy(name)
    return catalog.load(name, vectors)


def require_active(name):
    """Readers never use a collection the active pointer does not reference."""
    from . import workspace_defaults
    active = workspace_defaults.active_collection()
    if active is not None and active != name: raise HTTPException(409, GUARDRAIL)


def require_writable(execution):
    """Refuse indexing work that would target a non-active collection."""
    try: name = unified(execution)['knowledge_collection']
    except HTTPException: return  # Managed retrieval (OCI) has no unified collection.
    require_active(name)


def claim(name):
    """The single path that may make a collection active."""
    from . import workspace_defaults
    active = workspace_defaults.active_collection()
    if active == name: return
    if active is None and workspace_defaults.claim_collection(name): return
    if workspace_defaults.active_collection() != name: raise HTTPException(409, GUARDRAIL)


def entity_stamp(record):
    return digest([PUBLICATION_VERSION,record.kind,record.name,record.status,record.version,record.ref,record.updated_at,record.size])


def _client(snapshot):
    return providers.client() if snapshot['settings']['search_provider'] in VECTOR_PROVIDERS else None


def _prepare(q, name):
    if q and not q.collection_exists(name):
        probe = providers.embed(['Lapi unified knowledge.'])[0]
        from qdrant_client.models import VectorParams, Distance, PayloadSchemaType
        q.create_collection(name, vectors_config=VectorParams(size=len(probe), distance=Distance.COSINE))
        for field in ('dataset_id', 'source_type', 'owner_id', 'entity_id', 'document_id'):
            q.create_payload_index(name, field, PayloadSchemaType.KEYWORD, wait=True)


def _existing_vectors(q, name, ids):
    """Vectors already stored for unchanged text; payload-only updates never re-embed."""
    if not ids: return {}
    if q is None: return catalog.vectors(name, ids)
    try:
        from qdrant_client.models import Filter, HasIdCondition
        found = {}; offset = None
        while True:
            page, offset = q.scroll(name, scroll_filter=Filter(must=[HasIdCondition(has_id=list(ids))]), offset=offset, limit=256,
                                    with_payload=False, with_vectors=True)
            found.update({str(p.id): list(p.vector) for p in page if isinstance(p.vector, (list, tuple)) and p.vector})
            if offset is None: break
        return found
    except Exception:
        return {}  # Embed again rather than fail publication.


def _write_points(q, name, sources, known, checkpoint=None):
    """Embed only new or changed text and upsert the points. Returns (local vectors, dimensions)."""
    reuse = [p['id'] for p in sources if (known.get(p['id']) or {}).get('text') == p['payload']['text']]
    vectors = _existing_vectors(q, name, reuse)
    local = {}; dimensions = None
    for start in range(0, len(sources), 24):
        if checkpoint: checkpoint()
        batch = sources[start:start+24]
        missing = [p for p in batch if p['id'] not in vectors]
        if missing:
            fresh = providers.embed([p['payload']['text'] for p in missing])
            if len(fresh) != len(missing): raise providers.ProviderError('Unified embedding batch returned an incomplete result.')
            vectors.update({p['id']: v for p, v in zip(missing, fresh)})
        if q:
            from qdrant_client.models import PointStruct
            q.upsert(name, [PointStruct(id=p['id'], vector=vectors[p['id']], payload=p['payload']) for p in batch], wait=True)
        else:
            local.update({p['id']: vectors[p['id']] for p in batch})
        dimensions = dimensions or len(vectors[batch[0]['id']])
    return local, dimensions


def sync(actor, dataset_id='', max_points=None, application_only=False):
    """Durable digest ledger; retries repeat deterministic IDs, not new records."""
    from .workspace_reset import paused
    if paused():raise HTTPException(503,'Workspace archive operation is running.')
    snapshot = embedding_snapshot(actor, dataset_id)
    name = snapshot['knowledge_collection']
    claim(name)
    records = [] if application_only else eligible(actor, dataset_id)
    with core.document_lock('unified-knowledge-'+name):
        if paused():raise HTTPException(503,'Workspace archive operation is running.')
        try: current = manifest(name)
        except FileNotFoundError: current = {'entities': {}, 'points': {}, 'failures': []}
        entities = current['entities']; points = current['points']; pending = []; alive = set(); failures = []
        for record in records:
            key = record.id; alive.add(key)
            stamp = entity_stamp(record)
            # Live plan/goal phases are persisted outside SQL between leases.
            # Their public summaries must participate in change detection.
            if record.kind=='agent_plan': stamp=digest([PUBLICATION_VERSION,record_sources(record)])
            if entities.get(key, {}).get('stamp') == stamp: continue
            try: sources = record_sources(record)
            except (FileNotFoundError, ValueError, KeyError):
                failures.append(key); continue
            pending.append((key, stamp, sources))
        app_stamp = digest([PUBLICATION_VERSION,GUIDE])
        if entities.get('application', {}).get('stamp') != app_stamp: pending.append(('application', app_stamp, application_sources()))
        upserted = 0; removed = []; changes = []; deleted = []
        from .lapi_agent import token_usage
        with core.execution_context(snapshot), token_usage.scope(owner=actor, dataset_id=dataset_id or None, stage='reindex'):
            q = _client(snapshot)
            _prepare(q, name)
            for key, stamp, sources in pending:
                if max_points is not None and upserted and upserted+len(sources)>max_points: break
                local, _ = _write_points(q, name, sources, points)
                old = entities.get(key, {}).get('ids', [])
                ids = [p['id'] for p in sources]
                removed.extend(id for id in old if id not in ids)
                for p in sources: points[p['id']] = p['payload']
                current_record=next((r for r in records if r.id==key),None)
                entities[key] = {'stamp': stamp, 'ids': ids,'revision_stamp':entity_stamp(current_record) if current_record else None}; upserted += len(sources)
                changes.append((key, entities[key], {p['id']: p['payload'] for p in sources}, local if q is None else None))
            # Purge deleted or newly inaccessible records only inside this actor's
            # scope. Another user's entries must never be removed by a query.
            for key, entity in ([] if application_only else list(entities.items())):
                if key == 'application' or key in alive: continue
                with core.Session() as session: existing = session.get(core.Record, key)
                if existing is None:
                    removed.extend(entity['ids']); del entities[key]; deleted.append(key)
            if removed and q:
                from qdrant_client.models import PointIdsList
                q.delete(name, PointIdsList(points=removed), wait=True)
            for id in removed: points.pop(id, None)
        catalog.apply(name, changes, deleted, removed, failures)
    return snapshot, {'collection': name, 'upserted': upserted, 'removed': len(removed), 'failed_entities': len(failures), 'points': len(points)}


def publish_document(document_id, execution, checkpoint=None):
    """Worker indexing: embed a document's chunks once, into the active collection.

    The payload is published as the ready revision. The next sync only rewrites
    payload metadata (status, timestamps) and reuses these vectors.
    """
    snapshot = unified(execution)
    name = snapshot['knowledge_collection']
    try: claim(name)
    except HTTPException as exc: raise ValueError(str(exc.detail)) from exc
    with core.Session() as session: record = session.get(core.Record, document_id)
    if record is None: raise ValueError('Target no longer exists')
    ready = SimpleNamespace(**{column.key: getattr(record, column.key) for column in core.Record.__table__.columns})
    ready.status = 'ready'
    sources = record_sources(ready)
    with core.document_lock('unified-knowledge-'+name):
        entry, known = catalog.entity(name, document_id)
        with core.execution_context(snapshot):
            q = _client(snapshot)
            _prepare(q, name)
            local, dimensions = _write_points(q, name, sources, known, checkpoint)
            ids = [p['id'] for p in sources]
            removed = [id for id in (entry or {}).get('ids', []) if id not in ids]
            if removed and q:
                from qdrant_client.models import PointIdsList
                q.delete(name, PointIdsList(points=removed), wait=True)
        stamp = entity_stamp(ready)
        catalog.apply(name, [(document_id, {'stamp': stamp, 'ids': ids, 'revision_stamp': stamp}, {p['id']: p['payload'] for p in sources}, local if q is None else None)],
                      removed_points=removed)
    return {'collection': name, 'points': len(sources), 'dimensions': dimensions}


def forget(ids):
    """Remove published points that belong to or reference these records."""
    from .admin_documents import references
    ids = set(ids)
    for name in catalog.names():
        with core.document_lock('unified-knowledge-'+name):
            try: current = catalog.load(name)
            except FileNotFoundError: current = {'entities': {}, 'points': {}, 'failures': []}
            removed = {key for key, value in current['points'].items() if
                value.get('entity_id', '').split(':', 1)[0] in ids or references(value.get('document_ids', []), ids) or value.get('extraction_id') in ids}
            for entity in ids: removed.update(current['entities'].get(entity, {}).get('ids', []))
            if removed and core.settings()['search_provider'] in VECTOR_PROVIDERS:
                from qdrant_client.models import PointIdsList
                q = providers.client()
                if q.collection_exists(name): q.delete(name, PointIdsList(points=sorted(removed)), wait=True)
            catalog.apply(name, deleted_entities=[e for e in ids if e in current['entities']], removed_points=removed,
                          failures=[e for e in current.get('failures', []) if e not in ids])


def _fused(vector_ids, keyword_ids, points, limit):
    """Reciprocal-rank fusion by entity, with the fused score kept for ordering."""
    scores = {}
    for ranked in (vector_ids, keyword_ids):
        seen = set()
        for rank, id in enumerate(ranked, 1):
            entity = points[id]['entity_id']
            if entity in seen: continue
            seen.add(entity); scores[entity] = scores.get(entity, 0) + 1/(60+rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]


def retrieve_chunks(query, documents, limit):
    """Hybrid document-chunk search over the unified index (document search, extraction).

    Callers authorize the documents first. Results keep the legacy chunk citation
    shape; text always comes from the canonical chunks.json, never the payload.
    """
    from .lapi_agent.chat_retrieval import keyword_ranks
    from . import workspace_defaults
    if not documents: return []
    active = core._execution.get()
    snapshot = unified(active if active is not None else workspace_defaults.embedding_execution())
    name = snapshot['knowledge_collection']
    require_active(name)
    allowed = {d.id: d for d in documents}
    points = catalog.document_points(name, allowed) if catalog.exists(name) else {}
    published = {p.get('document_id') for p in points.values()}
    # Documents indexed before embed-once have no unified chunks yet. Publish
    # them once now from their saved chunks; later reads reuse the vectors.
    missing = [d for d in documents if d.id not in published and getattr(d, 'status', '') == 'ready']
    for document in missing:
        try: publish_document(document.id, active if active is not None else snapshot)
        except (FileNotFoundError, KeyError, ValueError): continue
    if missing: points = catalog.document_points(name, allowed)
    if not points: return []
    keywords = keyword_ranks(query, points, limit)
    with core.execution_context(snapshot):
        vector = providers.embed([query], query=True)[0]
        q = _client(snapshot)
        if q:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
            hits = q.query_points(name, query=vector, query_filter=Filter(must=[FieldCondition(key='source_type', match=MatchValue(value='document_chunk')),
                FieldCondition(key='document_id', match=MatchAny(any=sorted(allowed)))]), limit=min(100, limit)).points
            vector_hits = [(str(p.id), p.score) for p in hits if str(p.id) in points]
        else:
            stored = catalog.vectors(name, points)
            vector_hits = sorted(((id, sum(a*b for a, b in zip(vector, value))) for id, value in stored.items()), key=lambda item: item[1], reverse=True)[:limit]
    similarity = {}
    for id, score in vector_hits:
        entity = points[id]['entity_id']; similarity[entity] = max(score, similarity.get(entity, score))
    first = {}
    for id, payload in points.items(): first.setdefault(payload['entity_id'], payload)
    chunks = {}; results = []
    for entity, score in _fused([id for id, _ in vector_hits], keywords, points, limit):
        payload = first[entity]; did = payload.get('document_id'); cid = payload.get('chunk_id')
        if did not in allowed: continue
        if did not in chunks:
            try: chunks[did] = {c['id']: c for c in core.store.json('documents/'+did+'/chunks.json')['chunks']}
            except FileNotFoundError: chunks[did] = {}
        chunk = chunks[did].get(cid)
        if not chunk: continue
        results.append({'document_id': did, 'document_name': allowed[did].name, 'chunk_id': cid, 'text': chunk['text'], 'excerpt': chunk['text'],
            'page': chunk.get('page'), 'score': score, 'vector_score': similarity.get(entity), 'knowledge_collection': name,
            **{key: chunk[key] for key in ('text_origin', 'ocr', 'source_key', 'source_filename', 'source_page', 'section', 'coordinates', 'sheet', 'row_start', 'row_end') if key in chunk}})
    return results


def hydrate(actor, id, payload):
    kind = payload.get('source_type'); entity = payload.get('entity_id', '')
    if kind not in TYPES: return None
    if kind == 'application': sources = application_sources()
    else:
        record_id = entity.split(':', 1)[0]
        try: record = access.get_record(record_id, actor)
        except HTTPException: return None
        try: sources = record_sources(record)
        except (FileNotFoundError, ValueError, KeyError): return None
    source = next((p for p in sources if p['id'] == id), None)
    if not source or source['payload']['content_digest'] != payload.get('content_digest'): return None
    value = dict(source['payload'], knowledge_id=id)
    # Excerpts always come from reconstructed canonical content, never payload text.
    value['source_url'] = '/api/knowledge/sources/'+id
    return value


def search(query, actor, dataset_id='', document_ids=None, source_types=None, limit=5):
    if not query.strip(): raise HTTPException(400, 'Enter a semantic search question.')
    source_types = set(source_types or TYPES)
    if source_types-TYPES: raise HTTPException(400, 'Unknown knowledge source type.')
    records = eligible(actor, dataset_id, document_ids)
    snapshot, indexing = sync(actor, dataset_id)
    current = manifest(snapshot, vectors=snapshot['settings']['search_provider'] not in VECTOR_PROVIDERS)
    permitted_ids = {r.id for r in records}
    ids = [id for id,p in current['points'].items() if p['source_type'] in source_types and
        (p['source_type']=='application' or p['entity_id'].split(':',1)[0] in permitted_ids)]
    if not ids: return {'matches': [], 'count': 0, 'index': indexing}
    with core.execution_context(snapshot):
        vector = providers.embed([query], query=True)[0]
        if snapshot['settings']['search_provider'] in VECTOR_PROVIDERS:
            from qdrant_client.models import Filter, HasIdCondition
            q = providers.client()
            hits = q.query_points(snapshot['knowledge_collection'], query=vector,
                query_filter=Filter(must=[HasIdCondition(has_id=ids)]), limit=min(100, limit*5)).points
            hits = [(str(p.id), p.payload, p.score) for p in hits]
        else:
            vectors = current.get('vectors', {})
            hits = [(id,current['points'][id],sum(a*b for a,b in zip(vector,vectors.get(id,[])))) for id in ids]
            hits = sorted(hits,key=lambda p:p[2],reverse=True)[:limit*5]
    matches = []
    for id, payload, score in hits:
        source = hydrate(actor, id, payload)
        if source:
            source.update(knowledge_collection=snapshot['knowledge_collection'],source_url=source['source_url']+'?collection='+snapshot['knowledge_collection'])
            matches.append(dict(source, score=score))
            if len(matches) >= limit: break
    return {'matches': matches, 'count': len(matches), 'index': indexing,
        'complete_catalog': False, 'note': 'Semantic matches discover relevant sources; exact counts, complete lists and live status require authoritative reads.'}


def reconcile():
    """Worker background sync; optional search failure cannot fail document jobs."""
    with core.Session() as session: users = session.scalars(select(core.User)).all()
    for user in users:
        token = access.request_actor.set(user.id)
        try:
            # Every dataset publishes into the one collection of the workspace
            # Default embedding model. A failing dataset cannot block others.
            for dataset in routing.rows(user.id, 'knowledge_base'):
                try: sync(user.id, dataset.id, max_points=256)
                except Exception: pass  # A failed provider cannot block other datasets.
        except Exception: pass  # No provider bodies/secrets in background logs.
        finally: access.request_actor.reset(token)


# ------------------------------------------------- one index: status, orphans

def index_status(actor=None):
    """Knowledge index state other code can read; chat uses `building`.

    While the index is rebuilt after an embedding change, chat answers only
    from documents that are already reindexed and says the index is building.
    """
    from . import workspace_defaults
    try: pinned = workspace_defaults.embedding()
    except Exception: pinned = None
    run = workspace_defaults.reindex_status()
    state = 'ready'
    if not pinned: state = 'conflict' if len(workspace_defaults.legacy_spaces()) > 1 else 'unconfigured'
    elif run and run['pending']: state = 'building'
    elif run and run['failed']: state = 'attention'
    value = {'state': state, 'building': state == 'building', 'collection': workspace_defaults.active_collection(),
             'model_id': pinned['model_id'] if pinned else None,
             'model_name': (pinned['snapshot'].get('model_name') if pinned else None),
             'total': run['total'] if run else 0, 'indexed': run['indexed'] if run else 0,
             'pending': run['pending'] if run else 0, 'failed': run['failed'] if run else 0,
             'started_at': run['started_at'] if run else None}
    admin = actor is None or access.request_actor.get() is None or core.is_administrator(actor)
    value['failures'] = (run['failures'] if run else []) if admin else []
    if state == 'building':
        value['message'] = (f'The knowledge index is still building: {value["indexed"]} of {value["total"]} documents are reindexed. '
                            'Answers use only documents that are already reindexed.')
    elif state == 'attention':
        value['message'] = f'{value["failed"]} documents could not be reindexed. Retry them to make them searchable again.'
    elif state == 'conflict':
        value['message'] = workspace_defaults.unset_message()
    elif state == 'unconfigured':
        value['message'] = 'Choose a Default embedding model in Model Registration.'
    return value


def _settings(settings=None):
    # Deployment vector store; never probes model services (used by /ready).
    return settings if settings is not None else core.settings()


def _store_collections(settings):
    """Our collections in the vector store (Qdrant or Oracle), if one is used."""
    if settings['search_provider'] not in VECTOR_PROVIDERS: return None, []
    with core.execution_context({'settings': settings, 'secret_refs': {}}):
        q = providers.client()
        names = [c.name for c in q.get_collections().collections if c.name.startswith('lapi_knowledge_') or
                 c.name.startswith('lapi_') and not runtime_config.get('LAPI_LEGACY_CHUNK_INDEX')]
    return q, names


def remove_collections(keep=None, settings=None):
    """Delete every collection except `keep`: vectors, catalog rows and legacy manifests."""
    settings = _settings(settings)
    removed = {'collections': [], 'catalog_rows': 0, 'vector_collections': []}
    for name in catalog.names():
        if name == keep: continue
        with core.document_lock('unified-knowledge-'+name):
            removed['catalog_rows'] += catalog.drop(name); removed['collections'].append(name)
    for manifest_key in core.files_in('knowledge/', '*/manifest.json'):
        if manifest_key.split('/')[1] != keep: core.local_store.delete(manifest_key)
    q, names = _store_collections(settings)
    for name in names:
        if name == keep: continue
        with core.execution_context({'settings': settings, 'secret_refs': {}}): q.delete_collection(name)
        removed['vector_collections'].append(name)
    return removed


def remove_orphans():
    """One-time cleanup: delete every collection the active pointer does not reference."""
    from . import workspace_defaults
    active = workspace_defaults.active_collection()
    if active is None:
        try: active = unified(workspace_defaults.embedding_execution())['knowledge_collection']
        except HTTPException as exc: raise HTTPException(409, 'No active knowledge collection is set. ' + str(exc.detail)) from exc
        claim(active)
    return {'active_collection': active, **remove_collections(keep=active)}


def health():
    """Collection count and orphan rows for /ready. Orphans above zero alert."""
    from . import workspace_defaults
    active = workspace_defaults.active_collection()
    rows = catalog.counts(); names = set(rows) | set(catalog.names())
    orphan_rows = sum(count for name, count in rows.items() if name != active)
    try:
        q, stored = _store_collections(_settings())
        for name in stored:
            names.add(name)
            if name != active:
                with core.execution_context({'settings': _settings(), 'secret_refs': {}}): orphan_rows += q.get_collection(name).points_count or 0
    except Exception:
        pass
    orphans = sorted(name for name in names if name != active)
    return {'active_collection': active, 'collections': len(names), 'orphan_collections': orphans,
            'orphan_rows': orphan_rows, 'alert': orphan_rows > 0 or len(orphans) > 0}


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=2000)
    dataset_id: str = ''
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    source_types: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=5, ge=1, le=12)


def install(app, auth):
    @app.get('/api/knowledge/published-sources/{id}')
    def published_source(id:str,collection:str='',dataset_id:str='',actor=Depends(auth)):
        from .chat_knowledge import PublishedKnowledge,assemble
        if collection and not re.fullmatch(r'lapi_knowledge_[0-9a-f]{20}',collection):raise HTTPException(400,'Invalid knowledge collection.')
        view=PublishedKnowledge(actor,dataset_id)
        if collection and collection!=view.snapshot['knowledge_collection']:raise HTTPException(409,'The embedding configuration changed. Query the current knowledge index again.')
        payload=view.manifest['points'].get(id)
        if not payload:raise HTTPException(404,'Published knowledge source is unavailable.')
        root=payload['entity_id'].split(':',1)[0]
        ids=view.candidate_ids([payload['source_type']],{root})
        if id not in ids:raise HTTPException(404,'Source access removed.')
        values=assemble(view.fetch([key for key in ids if view.manifest['points'][key]['entity_id']==payload['entity_id']]))
        return values[0]

    @app.post('/api/knowledge/search')
    def query(body: SearchInput, actor=Depends(auth)):
        return search(body.text, actor, body.dataset_id, body.document_ids, body.source_types, body.limit)

    @app.get('/api/knowledge/sources/{id}')
    def source(id: str, collection: str='', actor=Depends(auth)):
        if collection and not re.fullmatch(r'lapi_knowledge_[0-9a-f]{20}',collection): raise HTTPException(400,'Invalid knowledge collection.')
        name=collection or embedding_snapshot(actor)['knowledge_collection']
        try: payload = manifest(name)['points'].get(id)
        except FileNotFoundError: payload = None
        value = hydrate(actor, id, payload) if payload else None
        if not value: raise HTTPException(404, 'Knowledge source is unavailable, changed, or access was removed.')
        return value


if __name__ == '__main__':
    # One-time maintenance: python -m lapi_app.knowledge --remove-orphans
    import argparse
    parser = argparse.ArgumentParser(description='One knowledge base: health and orphan cleanup.')
    parser.add_argument('--remove-orphans', action='store_true', help='Delete every collection the active pointer does not reference.')
    arguments = parser.parse_args(); core.init()
    try: print(json.dumps(remove_orphans() if arguments.remove_orphans else health()))
    except HTTPException as error: raise SystemExit(str(error.detail))
