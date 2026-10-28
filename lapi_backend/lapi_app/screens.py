"""Which screens each person sees, per device, decided by OpenFGA.

Dashboard, Lapi Agent and Quick start are always on. Every other screen is an OpenFGA object
(`screen:<id>` for computers, `screen:<id>-phone` for phones) with one relation, `enabled`,
granted to everyone (`user:*`), a team (`team:<id>#member`) or a person. Administrators see
every screen on every device. Grants are kept in screen_grant_tbl and synced to OpenFGA like
dataset access; changing them in the Access map applies at once, with no deploy.

With no grant rows for a screen and device, the default applies: on computers everyone, on
phones off (the "agent only" phone version). Hiding a screen is a product choice, not a
security control: the route policy still protects every API route.
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from . import core, relational

DEVICES = ('computer', 'phone')
CORE = ('home', 'agent', 'quick-start')  # Always on; not grantable.
# id, label, the frontend views it covers, administrator-only
SCREENS = [
    ('about', 'About', ['About'], False),
    ('datasets', 'Datasets', ['Datasets'], False),
    ('add-knowledge', 'Add knowledge', ['Add knowledge'], False),
    ('extract', 'Extract', ['Extract Data'], False),
    ('review', 'Review', ['Extract', 'Review', 'Extraction Review', 'Re-extract'], False),
    ('prompts', 'Prompt templates', ['Prompt templates'], False),
    ('skills', 'Skills & memory', ['Skills & memory'], False),
    ('jobs', 'Jobs & activity', ['Jobs & activity'], False),
    ('users', 'Users & passwords', ['Users & passwords'], True),
    ('access-map', 'Access map', ['Access map'], True),
    ('storage', 'Storage', ['Storage'], True),
    ('files', 'Files & processing', ['Files & processing'], True),
    ('token-usage', 'Token usage', ['Token usage'], True),
    ('models', 'Model Registration', ['Model Registration', 'Model Mapping'], True),
]
IDS = [s[0] for s in SCREENS]
PRESETS = {
    'agent-only-phone': 'Phones show only Dashboard, Lapi Agent and Quick start; computers keep every screen.',
    'everything': 'Every screen on every device for everyone.',
}
_ID = re.compile(r'^[a-z][a-z0-9-]{0,40}$')


def obj(screen, device):
    """The OpenFGA object for a screen on a device."""
    return 'screen:' + screen + ('-phone' if device == 'phone' else '')


def parse_obj(value):
    name = value.split(':', 1)[1]
    if name.endswith('-phone'):
        return name[:-6], 'phone'
    return name, 'computer'


def default_everyone(screen, device):
    return device == 'computer'


def saved_grants(session):
    """{(screen, device): {'everyone': bool, 'teams': set, 'users': set}} for rows that exist."""
    grants = {}
    for row in session.scalars(select(relational.ScreenGrant)):
        entry = grants.setdefault((row.screen, row.device), {'everyone': False, 'teams': set(), 'users': set()})
        if row.grantee_kind == 'everyone':
            entry['everyone'] = True
        elif row.grantee_kind == 'team':
            entry['teams'].add(row.grantee_id)
        elif row.grantee_kind == 'user':
            entry['users'].add(row.grantee_id)
    return grants


def effective_grants(session):
    """Every screen and device, saved rows or the default."""
    saved = saved_grants(session)
    out = {}
    for screen in IDS:
        for device in DEVICES:
            out[(screen, device)] = saved.get((screen, device)) or {'everyone': default_everyone(screen, device), 'teams': set(), 'users': set()}
    return out


def tuples(session):
    """OpenFGA tuples the grants imply (authz._desired)."""
    out = set()
    for (screen, device), entry in effective_grants(session).items():
        target = obj(screen, device)
        if entry['everyone']:
            out.add(('user:*', 'enabled', target))
        out |= {('team:' + team + '#member', 'enabled', target) for team in entry['teams']}
        out |= {('user:' + user + '', 'enabled', target) for user in entry['users']}
    return out


def enabled_for(actor, device, session=None):
    """Screen ids the person may see on the device (administrators: all)."""
    device = device if device in DEVICES else 'computer'
    if session is None:
        with core.Session() as active:
            return enabled_for(actor, device, active)
    if core.is_administrator(actor, session):
        return list(IDS)
    from . import authz
    if authz.enabled():
        found = authz.enabled_screens(actor)
        return [s for s in IDS if obj(s, device) in found]
    teams = set(session.scalars(select(relational.TeamMember.team_id).where(relational.TeamMember.user_id == actor)))
    out = []
    for screen in IDS:
        entry = effective_grants(session)[(screen, device)]
        if entry['everyone'] or actor in entry['users'] or teams & entry['teams']:
            out.append(screen)
    return out


def views_for(screen_ids):
    views = []
    for screen, _, names, _ in SCREENS:
        if screen in screen_ids:
            views.extend(names)
    return views


class GrantInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    screen: str = Field(max_length=40)
    device: str = Field(max_length=10)
    everyone: bool = False
    teams: list[str] = Field(default_factory=list, max_length=200)
    users: list[str] = Field(default_factory=list, max_length=500)


class GrantsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    grants: list[GrantInput] = Field(max_length=len(SCREENS) * len(DEVICES))


class PresetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset: str = Field(max_length=40)


def _public(session):
    teams = {t.team_id: t.name for t in session.scalars(select(relational.Team))}
    users = {u.id: u.username for u in session.scalars(select(core.User))}
    saved = saved_grants(session)
    rows = []
    for screen, label, views, admin_only in SCREENS:
        for device in DEVICES:
            entry = effective_grants(session)[(screen, device)]
            rows.append({'screen': screen, 'label': label, 'device': device, 'admin_only': admin_only,
                         'everyone': entry['everyone'], 'teams': sorted(entry['teams']), 'users': sorted(entry['users']),
                         'default': (screen, device) not in saved})
    return {'grants': rows, 'teams': [{'id': id, 'name': name} for id, name in sorted(teams.items(), key=lambda t: t[1].lower())],
            'users': [{'id': id, 'username': name} for id, name in sorted(users.items(), key=lambda u: u[1].lower())],
            'core': list(CORE), 'presets': PRESETS}


def _write(session, grants):
    """Replace the saved rows for the given screen/device pairs."""
    for grant in grants:
        if grant.screen not in IDS or grant.device not in DEVICES:
            raise HTTPException(422, 'Unknown screen or device: ' + grant.screen + ' / ' + grant.device)
    known_teams = set(session.scalars(select(relational.Team.team_id)))
    known_users = set(session.scalars(select(core.User.id)))
    for grant in grants:
        bad = [t for t in grant.teams if t not in known_teams] + [u for u in grant.users if u not in known_users]
        if bad:
            raise HTTPException(422, 'Unknown team or person: ' + ', '.join(bad))
        session.execute(delete(relational.ScreenGrant).where(relational.ScreenGrant.screen == grant.screen, relational.ScreenGrant.device == grant.device))
        if grant.everyone:
            session.add(relational.ScreenGrant(screen=grant.screen, device=grant.device, grantee_kind='everyone', grantee_id='*'))
        for team in dict.fromkeys(grant.teams):
            session.add(relational.ScreenGrant(screen=grant.screen, device=grant.device, grantee_kind='team', grantee_id=team))
        for user in dict.fromkeys(grant.users):
            session.add(relational.ScreenGrant(screen=grant.screen, device=grant.device, grantee_kind='user', grantee_id=user))
        if not grant.everyone and not grant.teams and not grant.users:
            # An explicit "off" row, so the default does not come back.
            session.add(relational.ScreenGrant(screen=grant.screen, device=grant.device, grantee_kind='off', grantee_id='-'))


def install(app, auth):
    from . import dataset_access as access
    router = APIRouter()

    @router.get('/api/me/screens')
    def mine(device: str = 'computer', owner=Depends(auth)):
        device = device if device in DEVICES else 'computer'
        with core.Session() as session:
            ids = enabled_for(owner, device, session)
            admin = core.is_administrator(owner, session)
        return {'device': device, 'screens': ids, 'views': views_for(ids), 'core': list(CORE), 'administrator': admin}

    @router.get('/api/screens')
    def read(owner=Depends(auth)):
        access.require_admin(owner)
        with core.Session() as session:
            return _public(session)

    @router.put('/api/screens')
    def write(body: GrantsInput, owner=Depends(auth)):
        access.require_admin(owner)
        with core.Session.begin() as session:
            _write(session, body.grants)
        with core.Session() as session:
            return _public(session)

    @router.post('/api/screens/preset')
    def preset(body: PresetInput, owner=Depends(auth)):
        access.require_admin(owner)
        if body.preset not in PRESETS:
            raise HTTPException(422, 'Presets: ' + ', '.join(PRESETS))
        grants = [GrantInput(screen=s, device=d, everyone=(body.preset == 'everything' or d == 'computer')) for s in IDS for d in DEVICES]
        with core.Session.begin() as session:
            _write(session, grants)
        with core.Session() as session:
            return _public(session)

    app.include_router(router)
