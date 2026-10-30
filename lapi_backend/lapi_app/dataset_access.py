"""Dataset grants govern shared content; conversations remain personal."""
from contextvars import ContextVar
from fastapi import HTTPException
from sqlalchemy import select
from . import core, relational

request_actor = ContextVar('lapi_request_actor', default=None)
SHARED = {'document', 'template', 'extraction'}
PRIVATE = {'conversation', 'agent_plan', 'agent_onboarding', 'temporary_session', 'temporary_document'}


def require_admin(actor):
    # Trusted internal CLI calls and synthetic dependency overrides have no
    # authenticated HTTP actor. Every normal API request sets it in auth().
    if request_actor.get() is not None and not core.is_administrator(actor):
        raise HTTPException(403, 'Only the administrator can manage collection and model configuration.')


RANK = {'viewer': 1, 'editor': 2, 'owner': 3}
LABEL = {'viewer': 'Viewer', 'editor': 'Editor', 'owner': 'Owner'}


def is_auditor(actor, session=None):
    """Auditors read users, access and activity across the workspace; they change nothing."""
    from . import authz
    if authz.enabled():
        return authz.is_auditor(actor)
    if session is None:
        with core.Session() as active:
            return is_auditor(actor, active)
    row = session.get(relational.WorkspaceRole, actor)
    return bool(row and row.role == 'auditor')


def is_contributor(actor, session=None):
    """Contributors are Owner on every dataset and may create datasets (not manage the workspace)."""
    from . import authz
    if authz.enabled():
        return authz.is_contributor(actor)
    if session is None:
        with core.Session() as active:
            return is_contributor(actor, active)
    return session.get(relational.WorkspaceContributor, actor) is not None


def manages_datasets(actor, session=None):
    return core.is_administrator(actor, session) or is_contributor(actor, session)


def require_contributor(actor):
    """Creating, deleting and restoring datasets: Administrators and Contributors."""
    if request_actor.get() is not None and not manages_datasets(actor):
        raise HTTPException(403, 'Only administrators and contributors can create, delete or restore collections.')


def _saved_levels(actor, session):
    """Highest saved level per dataset, from the person's own grants and their teams' grants."""
    levels = {}
    def keep(dataset_id, level):
        level = level if level in RANK else 'viewer'
        if RANK[level] > RANK.get(levels.get(dataset_id), 0):
            levels[dataset_id] = level
    for dataset_id, level in session.execute(select(relational.UserDataset.dataset_id, relational.UserDataset.access_level).where(
            relational.UserDataset.user_id == actor, relational.UserDataset.enabled == True)):
        keep(dataset_id, level)
    for dataset_id, level in session.execute(select(relational.TeamDataset.dataset_id, relational.TeamDataset.access_level).join(
            relational.TeamMember, relational.TeamMember.team_id == relational.TeamDataset.team_id).where(relational.TeamMember.user_id == actor)):
        keep(dataset_id, level)
    return levels


def dataset_levels(actor, session):
    """Each dataset this person can open, with their level: 'owner' for administrators and contributors."""
    live = select(core.Record.id).where(core.Record.kind == 'knowledge_base', core.Record.status != 'deleted')
    if manages_datasets(actor, session):
        return {id: 'owner' for id in session.scalars(live)}
    if not session.get(core.User, actor) and request_actor.get() is None:
        return {id: 'owner' for id in session.scalars(live.where(core.Record.owner == actor))}
    existing = set(session.scalars(live))
    from . import authz
    if authz.enabled():
        levels = {}
        for level in ('viewer', 'editor', 'owner'):  # Later levels overwrite: the highest wins.
            levels.update({id: level for id in authz.datasets_at(actor, level) & existing})
        return levels
    return {id: level for id, level in _saved_levels(actor, session).items() if id in existing}


def level_for(actor, dataset_id, session=None):
    if session is None:
        with core.Session() as active:
            return level_for(actor, dataset_id, active)
    return dataset_levels(actor, session).get(dataset_id)


def require_level(actor, dataset_id, needed):
    """Refuse unless the person has at least `needed` on the dataset. Trusted internal calls
    (no HTTP actor) pass, as with require_admin."""
    if request_actor.get() is None:
        return
    level = level_for(actor, dataset_id)
    if level is None:
        raise HTTPException(404, 'Not found or collection access removed.')
    if RANK[level] < RANK[needed]:
        raise HTTPException(403, f'This needs {LABEL[needed]} access to the collection; you have {LABEL[level]} access. Ask the collection owner or an administrator.')


def record_dataset(record):
    """The dataset a dataset-scoped record belongs to (None for personal records)."""
    if record.kind == 'knowledge_base':
        return record.id
    if record.kind in SHARED:
        return record.parent_id
    return None


def dataset_ids(actor, session):
    live = select(core.Record.id).where(core.Record.kind == 'knowledge_base', core.Record.status != 'deleted')
    if manages_datasets(actor, session):
        return set(session.scalars(live))
    if not session.get(core.User, actor) and request_actor.get() is None:
        return set(session.scalars(live.where(core.Record.owner == actor)))
    from . import authz
    if authz.enabled():
        # Intersect in Python: Oracle limits IN lists to 1000 values.
        return set(session.scalars(live)) & authz.viewable_datasets(actor)
    # Own grants and team grants (without OpenFGA, the database answers).
    return set(_saved_levels(actor, session)) & set(session.scalars(live))


def allowed(record, actor, session, datasets=None, models=None):
    if not record or record.status=='deleting':
        return False
    datasets = dataset_ids(actor, session) if datasets is None else datasets
    if record.kind == 'knowledge_base':
        return record.id in datasets
    if record.kind in SHARED and record.parent_id:
        return record.parent_id in datasets
    if record.kind in PRIVATE:
        dataset_id=record.parent_id
        if record.owner!=actor:return False
        if not dataset_id and record.kind in {'conversation','agent_plan','agent_onboarding'}:
            try:
                data=core.store.json(record.ref);dataset_id=data.get('dataset_id') or data.get('kb_id')
            except FileNotFoundError:pass
        return not dataset_id or dataset_id in datasets
    if record.kind == 'model':
        if core.is_administrator(actor,session) or record.owner == actor:
            return True
        models = set(session.scalars(select(relational.DatasetModel.model_id).where(
            relational.DatasetModel.dataset_id.in_(datasets), relational.DatasetModel.enabled == True))) if models is None else models
        return record.id in models
    return record.owner == actor or (core.is_administrator(actor,session) and record.kind == 'config_profile')


def visible_models(datasets, session):
    """Models mapped to accessible datasets plus the workspace Defaults they use.

    Used by the published knowledge view only; ownership checks stay unchanged.
    """
    from .workspace_defaults import WorkspaceDefaults, WORKSPACE
    models = set(session.scalars(select(relational.DatasetModel.model_id).where(
        relational.DatasetModel.dataset_id.in_(datasets), relational.DatasetModel.enabled == True)))
    row = session.get(WorkspaceDefaults, WORKSPACE) if datasets else None
    if row: models.update(id for id in (row.chat_model_id, row.extraction_model_id, row.embedding_model_id) if id)
    return models


def get_record(id, actor, kind=None, level='viewer'):
    """The record if the person may open it; with level 'editor' or 'owner', also requires
    that level on the record's dataset (personal records are already owner-only)."""
    with core.Session() as session:
        record = session.get(core.Record, id)
        if not record or (kind and record.kind != kind) or not allowed(record, actor, session):
            raise HTTPException(404, 'Not found or collection access removed.')
    if level != 'viewer' and (dataset_id := record_dataset(record)):
        require_level(actor, dataset_id, level)
    return record


def rows(actor, kind):
    with core.Session() as session:
        datasets = dataset_ids(actor, session)
        models = set(session.scalars(select(relational.DatasetModel.model_id).where(
            relational.DatasetModel.dataset_id.in_(datasets), relational.DatasetModel.enabled == True))) if kind == 'model' else set()
        return [row for row in session.scalars(select(core.Record).where(core.Record.kind == kind).order_by(core.Record.created_at.desc()))
                if allowed(row, actor, session, datasets, models)]


def job_allowed(job, actor, session):
    if not job:
        return False
    target = session.get(core.Record, job.target_id)
    return allowed(target, actor, session) if target else job.owner == actor


def require_job_change(job, actor):
    """Retrying or cancelling work changes the dataset: Editor, or the person who started it."""
    with core.Session() as session:
        target = session.get(core.Record, job.target_id) if job else None
    dataset_id = record_dataset(target) if target else None
    if dataset_id and job.owner != actor:
        require_level(actor, dataset_id, 'editor')


def jobs(actor):
    with core.Session() as session:
        return [job for job in session.scalars(select(core.Job).order_by(core.Job.created_at.desc()))
                if job_allowed(job, actor, session)]
