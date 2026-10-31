"""OpenFGA permission checks: who administers Lapi and which datasets each person may open.

Set LAPI_OPENFGA_URL to turn it on. Lapi's database stays the record of users, roles
and dataset grants; OpenFGA holds the same facts as relationship tuples and answers
every check:

  user:<user id>  administrator  lapi:workspace
  user:<user id>  viewer         dataset:<dataset id>

OpenFGA runs with its in-memory store, so Lapi rebuilds the tuples from the database
whenever it (re)connects to the store, and writes each change after the database
commit. When OpenFGA cannot answer, access is refused (HTTP 503), never granted.
"""
import logging
import os
import threading
from contextvars import ContextVar
import httpx
from sqlalchemy import event, select
from sqlalchemy.orm import Session as ORMSession

log = logging.getLogger(__name__)

STORE_NAME = 'lapi'
WORKSPACE = 'lapi:workspace'
LEVELS = ('viewer', 'editor', 'owner')  # Each includes the ones before it.
_GRANTEES = [{'type': 'user'}, {'type': 'team', 'relation': 'member'}]
_DIRECT = lambda types: {'directly_related_user_types': types}
MODEL = {'schema_version': '1.1', 'type_definitions': [
    {'type': 'user'},
    {'type': 'team', 'relations': {'member': {'this': {}}},
     'metadata': {'relations': {'member': _DIRECT([{'type': 'user'}])}}},
    {'type': 'lapi', 'relations': {'administrator': {'this': {}}, 'auditor': {'this': {}}, 'contributor': {'this': {}}},
     'metadata': {'relations': {role: _DIRECT([{'type': 'user'}]) for role in ('administrator', 'auditor', 'contributor')}}},
    # Screens: enabled for everyone (user:*), a team's members, or a person (screens.py).
    {'type': 'screen', 'relations': {'enabled': {'this': {}}},
     'metadata': {'relations': {'enabled': _DIRECT([{'type': 'user'}, {'type': 'user', 'wildcard': {}}, {'type': 'team', 'relation': 'member'}])}}},
    {'type': 'dataset', 'relations': {
        'owner': {'this': {}},
        'editor': {'union': {'child': [{'this': {}}, {'computedUserset': {'relation': 'owner'}}]}},
        'viewer': {'union': {'child': [{'this': {}}, {'computedUserset': {'relation': 'editor'}}]}}},
     'metadata': {'relations': {level: _DIRECT(_GRANTEES) for level in LEVELS}}},
]}
WRITE_LIMIT = 100  # OpenFGA's default maximum tuples per write request.

_state = {'store': None}
_lock = threading.RLock()
# Answers already given during this request; reset by the HTTP middleware.
_answers = ContextVar('lapi_authz_answers', default=None)


class AuthorizationUnavailable(RuntimeError):
    """OpenFGA did not answer; callers refuse access."""


class _StoreMissing(Exception):
    """The store or its model is gone (OpenFGA restarted with an empty memory store)."""


def enabled():
    return bool(os.getenv('LAPI_OPENFGA_URL', '').strip())


def remember_answers():
    """Start a fresh per-request answer cache; returns the token for `forget_answers`."""
    return _answers.set({})


def forget_answers(token):
    _answers.reset(token)


def _client():
    return httpx.Client(timeout=5, trust_env=False, follow_redirects=False)


def _call(method, path, body=None):
    url = os.environ['LAPI_OPENFGA_URL'].strip().rstrip('/') + path
    try:
        with _client() as client:
            response = client.request(method, url, json=body)
    except httpx.HTTPError as exc:
        raise AuthorizationUnavailable('The OpenFGA permission service is unreachable.') from exc
    if response.status_code == 404 or (response.status_code == 400 and '_not_found' in response.text):
        raise _StoreMissing()
    if response.status_code >= 300:
        raise AuthorizationUnavailable(f'The OpenFGA permission service refused a request (HTTP {response.status_code}).')
    try:
        return response.json() if response.content else {}
    except ValueError as exc:
        raise AuthorizationUnavailable('The OpenFGA permission service returned invalid JSON.') from exc


def _find_store():
    """The oldest store named 'lapi', so containers that start together share one."""
    found, token = [], ''
    while True:
        page = _call('GET', '/stores?page_size=100' + ('&continuation_token=' + token if token else ''))
        found += [store for store in page.get('stores') or [] if store.get('name') == STORE_NAME]
        token = page.get('continuation_token') or ''
        if not token:
            break
    found.sort(key=lambda store: (store.get('created_at') or '', store['id']))
    return found[0]['id'] if found else None


def _bootstrap():
    store = _find_store() or _call('POST', '/stores', {'name': STORE_NAME})['id']
    _call('POST', f'/stores/{store}/authorization-models', MODEL)
    for attempt in (0, 1):
        try:
            _reconcile(store)
            break
        except AuthorizationUnavailable:
            # Another container reconciling at the same moment can make a write
            # collide with a tuple it just wrote: read again and retry once.
            if attempt:
                raise
    log.info('OpenFGA store %s is ready.', store)
    return store


def _with_store(action):
    for _ in (0, 1):
        with _lock:
            if _state['store'] is None:
                _state['store'] = _bootstrap()
            store = _state['store']
        try:
            return action(store)
        except _StoreMissing:
            with _lock:
                if _state['store'] == store:
                    _state['store'] = None
    raise AuthorizationUnavailable('The OpenFGA store could not be prepared.')


def prepare():
    """Connect to OpenFGA and load every tuple now (start-up), instead of on the first check."""
    with _lock:
        _state['store'] = None
    _with_store(lambda store: None)


def _key(user, relation, obj):
    return {'user': user, 'relation': relation, 'object': obj}


def _level(value):
    return value if value in LEVELS else 'viewer'


def _desired(user_id=None):
    """Tuples the database implies: for one person (their roles, grants and team
    memberships), or for everyone plus every team's grants when user_id is None."""
    from . import core, relational
    with core.Session() as session:
        admins = select(core.User.id).where(core.User.role == 'administrator')
        auditors = select(relational.WorkspaceRole.user_id).where(relational.WorkspaceRole.role == 'auditor')
        contributors = select(relational.WorkspaceContributor.user_id)
        grants = select(relational.UserDataset.user_id, relational.UserDataset.dataset_id, relational.UserDataset.access_level).where(relational.UserDataset.enabled == True)
        members = select(relational.TeamMember.user_id, relational.TeamMember.team_id)
        if user_id is not None:
            admins = admins.where(core.User.id == user_id)
            auditors = auditors.where(relational.WorkspaceRole.user_id == user_id)
            contributors = contributors.where(relational.WorkspaceContributor.user_id == user_id)
            grants = grants.where(relational.UserDataset.user_id == user_id)
            members = members.where(relational.TeamMember.user_id == user_id)
        tuples = {('user:' + admin, 'administrator', WORKSPACE) for admin in session.scalars(admins)}
        tuples |= {('user:' + auditor, 'auditor', WORKSPACE) for auditor in session.scalars(auditors)}
        tuples |= {('user:' + contributor, 'contributor', WORKSPACE) for contributor in session.scalars(contributors)}
        tuples |= {('user:' + user, _level(level), 'dataset:' + dataset) for user, dataset, level in session.execute(grants)}
        tuples |= {('user:' + user, 'member', 'team:' + team) for user, team in session.execute(members)}
        if user_id is None:
            team_grants = select(relational.TeamDataset.team_id, relational.TeamDataset.dataset_id, relational.TeamDataset.access_level)
            tuples |= {('team:' + team + '#member', _level(level), 'dataset:' + dataset) for team, dataset, level in session.execute(team_grants)}
            from . import screens
            tuples |= screens.tuples(session)
        else:
            from . import screens
            tuples |= {t for t in screens.tuples(session) if t[0] == 'user:' + user_id}
    return tuples


def _read(store, key=None):
    tuples, token = set(), ''
    while True:
        body = {'page_size': 100, **({'tuple_key': key} if key else {}), **({'continuation_token': token} if token else {})}
        page = _call('POST', f'/stores/{store}/read', body)
        for item in page.get('tuples') or []:
            k = item['key']
            tuples.add((k['user'], k['relation'], k['object']))
        token = page.get('continuation_token') or ''
        if not token:
            return tuples


def _write(store, add, remove):
    changes = [('writes', t) for t in sorted(add)] + [('deletes', t) for t in sorted(remove)]
    for start in range(0, len(changes), WRITE_LIMIT):
        body = {}
        for kind, t in changes[start:start + WRITE_LIMIT]:
            body.setdefault(kind, {'tuple_keys': []})['tuple_keys'].append(_key(*t))
        _call('POST', f'/stores/{store}/write', body)


def _reconcile(store, user_id=None):
    desired = _desired(user_id)
    if user_id is None:
        current = _read(store)
    else:
        user = 'user:' + user_id
        current = (_read(store, {'user': user, 'object': 'dataset:'}) | _read(store, {'user': user, 'object': 'team:'}) | _read(store, {'user': user, 'object': 'screen:'})
                   | _read(store, _key(user, 'administrator', WORKSPACE)) | _read(store, _key(user, 'auditor', WORKSPACE))
                   | _read(store, _key(user, 'contributor', WORKSPACE)))
    _write(store, desired - current, current - desired)


def sync_user(user_id):
    """Make OpenFGA match the database for one user (after a role or grant change)."""
    _with_store(lambda store: _reconcile(store, user_id))


def sync_all():
    """Make OpenFGA match the database for everyone (after a team or team-grant change)."""
    _with_store(lambda store: _reconcile(store))


def _remembered(question, ask):
    answers = _answers.get()
    if answers is not None and question in answers:
        return answers[question]
    answer = _with_store(ask)
    if answers is not None:
        answers[question] = answer
    return answer


def is_administrator(user_id):
    if not user_id:
        return False
    return _remembered(('administrator', user_id), lambda store: _call(
        'POST', f'/stores/{store}/check', {'tuple_key': _key('user:' + user_id, 'administrator', WORKSPACE)}).get('allowed') is True)


def is_auditor(user_id):
    if not user_id:
        return False
    return _remembered(('auditor', user_id), lambda store: _call(
        'POST', f'/stores/{store}/check', {'tuple_key': _key('user:' + user_id, 'auditor', WORKSPACE)}).get('allowed') is True)


def is_contributor(user_id):
    if not user_id:
        return False
    return _remembered(('contributor', user_id), lambda store: _call(
        'POST', f'/stores/{store}/check', {'tuple_key': _key('user:' + user_id, 'contributor', WORKSPACE)}).get('allowed') is True)


def enabled_screens(user_id):
    """Screen objects (screen:<id>, screen:<id>-phone) the person may see."""
    def ask(store):
        objects = _call('POST', f'/stores/{store}/list-objects', {'type': 'screen', 'relation': 'enabled', 'user': 'user:' + user_id}).get('objects') or []
        return frozenset(objects)
    return _remembered(('screens', user_id), ask) if user_id else frozenset()


def datasets_at(user_id, level):
    """Dataset IDs where the user has at least this level, directly or through a team."""
    def ask(store):
        objects = _call('POST', f'/stores/{store}/list-objects',
                        {'type': 'dataset', 'relation': level, 'user': 'user:' + user_id}).get('objects') or []
        return frozenset(obj.split(':', 1)[1] for obj in objects)
    return _remembered(('datasets', level, user_id), ask) if user_id else frozenset()


def viewable_datasets(user_id):
    """Dataset IDs the user can open (administrators see every dataset by role, not by tuple)."""
    return datasets_at(user_id, 'viewer')


# Keep OpenFGA in step with the database: note which users' roles or grants a
# transaction touched, then sync those users once it commits.
@event.listens_for(ORMSession, 'after_flush')
def _note_changes(session, context):
    if not enabled():
        return
    from . import core, relational
    touched = session.info.setdefault('lapi_authz_users', set())
    for row in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(row, core.User):
            touched.add(row.id)
        elif isinstance(row, (relational.UserDataset, relational.WorkspaceRole, relational.WorkspaceContributor, relational.TeamMember)):
            touched.add(row.user_id)
        elif isinstance(row, (relational.Team, relational.TeamDataset, relational.ScreenGrant)):
            touched.add(None)  # A team's grants reach all its members: rebuild everything.


@event.listens_for(ORMSession, 'after_commit')
def _sync_committed(session):
    touched = session.info.pop('lapi_authz_users', None)
    if not touched:
        return
    answers = _answers.get()
    if answers is not None:
        answers.clear()
    for user_id in [None] if None in touched else sorted(touched):
        try:
            sync_all() if user_id is None else sync_user(user_id)
        except AuthorizationUnavailable:
            # The change is saved in the database; rebuild everything on the next check.
            log.warning('OpenFGA was not updated after a permission change; it will be rebuilt.')
            with _lock:
                _state['store'] = None
            return


@event.listens_for(ORMSession, 'after_rollback')
def _drop_changes(session):
    session.info.pop('lapi_authz_users', None)
