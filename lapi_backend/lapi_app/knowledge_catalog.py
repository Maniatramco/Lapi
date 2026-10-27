"""Shared unified-knowledge catalog in the control database.

The catalog replaces the pod-local knowledge/<collection>/manifest.json files so
every API pod and worker read the same published entities and points. Tables are
created by Base.metadata.create_all: SQLite in tests, Oracle in production. Large
JSON values use Text (CLOB on Oracle) and are never used in WHERE clauses.
"""
import json
import time
from sqlalchemy import String, Integer, Text, Index, select, delete, func
from sqlalchemy.orm import Mapped, mapped_column
from . import core
from .database import timestamp_type


class KnowledgeCollection(core.Base):
    __tablename__ = 'lapi_knowledge_collections'
    collection_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)
    updated_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)


class KnowledgeEntity(core.Base):
    __tablename__ = 'lapi_knowledge_entities'
    collection_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(180), primary_key=True)
    stamp: Mapped[str] = mapped_column(String(64))
    revision_stamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    point_ids_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)


class KnowledgePoint(core.Base):
    __tablename__ = 'lapi_knowledge_points'
    collection_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    point_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(180))
    source_type: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    # Only the local vector provider stores vectors here. Qdrant and Oracle keep
    # vectors in their own store (lapi_knowledge_vectors on Oracle).
    vector_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[float] = mapped_column(timestamp_type(), default=time.time)
    __table_args__ = (Index('ix_lapi_knowledge_points_entity', 'collection_name', 'entity_key'),
                      Index('ix_lapi_knowledge_points_document', 'collection_name', 'document_id'))


TABLES = (KnowledgePoint, KnowledgeEntity, KnowledgeCollection)


def _decode(value, default):
    if value is None: return default
    return json.loads(value.read() if hasattr(value, 'read') else value)


def exists(name):
    with core.Session() as session:
        return session.get(KnowledgeCollection, name) is not None


def names():
    """Every collection with catalog rows, including rows without a header."""
    with core.Session() as session:
        found = set(session.scalars(select(KnowledgeCollection.collection_name)))
        found.update(session.scalars(select(KnowledgeEntity.collection_name).distinct()))
        found.update(session.scalars(select(KnowledgePoint.collection_name).distinct()))
    return sorted(found)


def load(name, vectors=False):
    """Manifest-compatible view: {'entities', 'points', 'failures', 'vectors'?}."""
    with core.Session() as session:
        header = session.get(KnowledgeCollection, name)
        if header is None: raise FileNotFoundError(name)
        entities = {row.entity_key: {'stamp': row.stamp, 'ids': _decode(row.point_ids_json, []), 'revision_stamp': row.revision_stamp}
                    for row in session.scalars(select(KnowledgeEntity).where(KnowledgeEntity.collection_name == name))}
        columns = [KnowledgePoint.point_id, KnowledgePoint.payload_json] + ([KnowledgePoint.vector_json] if vectors else [])
        rows = session.execute(select(*columns).where(KnowledgePoint.collection_name == name)).all()
    manifest = {'entities': entities, 'points': {r[0]: _decode(r[1], {}) for r in rows},
                'failures': _decode(header.failures_json, []), 'updated_at': header.updated_at}
    if vectors: manifest['vectors'] = {r[0]: _decode(r[2], None) for r in rows if r[2] is not None}
    return manifest


def ensure(name):
    with core.Session.begin() as session:
        if session.get(KnowledgeCollection, name) is None:
            session.add(KnowledgeCollection(collection_name=name, failures_json='[]', created_at=time.time(), updated_at=time.time()))


def vectors(name, ids):
    ids = list(ids); found = {}
    with core.Session() as session:
        for start in range(0, len(ids), 500):
            rows = session.execute(select(KnowledgePoint.point_id, KnowledgePoint.vector_json).where(
                KnowledgePoint.collection_name == name, KnowledgePoint.point_id.in_(ids[start:start+500]))).all()
            found.update({r[0]: _decode(r[1], None) for r in rows if r[1] is not None})
    return found


def entity(name, key):
    """(entry or None, {point_id: payload}) of one published entity."""
    with core.Session() as session:
        row = session.get(KnowledgeEntity, (name, key))
        rows = session.execute(select(KnowledgePoint.point_id, KnowledgePoint.payload_json).where(
            KnowledgePoint.collection_name == name, KnowledgePoint.entity_key == key)).all()
        entry = {'stamp': row.stamp, 'ids': _decode(row.point_ids_json, []), 'revision_stamp': row.revision_stamp} if row else None
    return entry, {r[0]: _decode(r[1], {}) for r in rows}


def document_points(name, document_ids):
    """Published document_chunk payloads for these documents, by point id."""
    document_ids = list(document_ids); found = {}
    with core.Session() as session:
        for start in range(0, len(document_ids), 500):
            rows = session.execute(select(KnowledgePoint.point_id, KnowledgePoint.payload_json).where(
                KnowledgePoint.collection_name == name, KnowledgePoint.source_type == 'document_chunk',
                KnowledgePoint.document_id.in_(document_ids[start:start+500]))).all()
            found.update({r[0]: _decode(r[1], {}) for r in rows})
    return found


def apply(name, upserts=(), deleted_entities=(), removed_points=(), failures=None):
    """One transaction: replace entity rows and their points, drop removed ones.

    upserts: iterable of (entity_key, entry, {point_id: payload}, {point_id: vector}|None)
    """
    now = time.time()
    with core.Session.begin() as session:
        header = session.get(KnowledgeCollection, name)
        if header is None:
            header = KnowledgeCollection(collection_name=name, failures_json='[]', created_at=now, updated_at=now); session.add(header)
        for key in deleted_entities:
            session.execute(delete(KnowledgePoint).where(KnowledgePoint.collection_name == name, KnowledgePoint.entity_key == key))
            session.execute(delete(KnowledgeEntity).where(KnowledgeEntity.collection_name == name, KnowledgeEntity.entity_key == key))
        removed = list(removed_points)
        for start in range(0, len(removed), 500):
            session.execute(delete(KnowledgePoint).where(KnowledgePoint.collection_name == name, KnowledgePoint.point_id.in_(removed[start:start+500])))
        for key, entry, points, vectors in upserts:
            session.execute(delete(KnowledgePoint).where(KnowledgePoint.collection_name == name, KnowledgePoint.entity_key == key))
            ids = list(points)
            for start in range(0, len(ids), 500):
                # A point id is unique per entity, but remove any stale copy first.
                session.execute(delete(KnowledgePoint).where(KnowledgePoint.collection_name == name, KnowledgePoint.point_id.in_(ids[start:start+500])))
            session.execute(delete(KnowledgeEntity).where(KnowledgeEntity.collection_name == name, KnowledgeEntity.entity_key == key))
            session.execute(KnowledgeEntity.__table__.insert().values(collection_name=name, entity_key=key, stamp=entry['stamp'],
                revision_stamp=entry.get('revision_stamp'), point_ids_json=json.dumps(entry.get('ids', [])), updated_at=now))
            if ids:
                session.execute(KnowledgePoint.__table__.insert(), [
                    {'collection_name': name, 'point_id': id, 'entity_key': key, 'source_type': payload.get('source_type', ''),
                     'document_id': payload.get('document_id'), 'payload_json': json.dumps(payload, ensure_ascii=False),
                     'vector_json': json.dumps(vectors[id]) if vectors and id in vectors else None, 'updated_at': now}
                    for id, payload in points.items()])
        if failures is not None: header.failures_json = json.dumps(list(failures))
        header.updated_at = now


def drop(name):
    """Delete every catalog row of one collection; returns the removed point count."""
    with core.Session.begin() as session:
        count = session.scalar(select(func.count()).select_from(KnowledgePoint).where(KnowledgePoint.collection_name == name)) or 0
        for model in TABLES:
            session.execute(delete(model).where(model.collection_name == name))
    return count


def counts():
    """Point rows per collection name, for health and orphan reporting."""
    with core.Session() as session:
        rows = session.execute(select(KnowledgePoint.collection_name, func.count()).group_by(KnowledgePoint.collection_name)).all()
    return {name: count for name, count in rows}


def entity_count(name):
    with core.Session() as session:
        return session.scalar(select(func.count()).select_from(KnowledgeEntity).where(
            KnowledgeEntity.collection_name == name, KnowledgeEntity.entity_key != 'application')) or 0
