"""Prepare the Keycloak hosted next to Lapi on OCI (lapi_deploy/lapi_containers, keycloak_hosted).

Keycloak keeps its data in Lapi's Autonomous Database as its own user, KEYCLOAK. At start-up
the api (which already connects as ADMIN) creates that user, or resets its password to the
one in Vault, then hands Keycloak its three secrets as owner-only files in the shared scratch
volume and writes READY; the Keycloak container waits for READY before it starts.

Only runs when LAPI_KEYCLOAK_DB_PASSWORD_SECRET_OCID is set. Nothing here stops Lapi from
starting: failures are logged (without secret values) and Lapi carries on.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)
DB_SECRET_ENV = 'LAPI_KEYCLOAK_DB_PASSWORD_SECRET_OCID'
ADMIN_SECRET_ENV = 'LAPI_KEYCLOAK_ADMIN_PASSWORD_SECRET_OCID'
CLIENT_SECRET_ENV = 'LAPI_KEYCLOAK_CLIENT_SECRET_OCID'  # Also read by keycloak_auth.py.
DIR_ENV = 'LAPI_KEYCLOAK_SECRETS_DIR'
USER = 'KEYCLOAK'
TABLESPACE = 'DATA'
QUOTA = '2G'
PRIVILEGES = ('CREATE SESSION', 'CREATE TABLE', 'CREATE SEQUENCE', 'CREATE VIEW', 'CREATE PROCEDURE', 'CREATE TRIGGER')
FILES = {'db-password': DB_SECRET_ENV, 'admin-password': ADMIN_SECRET_ENV, 'client-secret': CLIENT_SECRET_ENV}
READY = '.ready'


def directory():
    """The folder Keycloak sees as /secrets, or None when Keycloak is not hosted here."""
    if not os.getenv(DB_SECRET_ENV, '').strip():
        return None
    return Path(os.getenv(DIR_ENV, '').strip() or '/data/keycloak-secrets')


def _safe(error, secrets):
    """One line about an error, with every secret value removed (SQL errors quote the statement)."""
    message = str(error).splitlines()[0] if str(error) else ''
    for value in secrets:
        if value:
            message = message.replace(value, '***')
    return f'{type(error).__name__}: {message[:300]}'


def _read(read_secret):
    values = {}
    for name, env in FILES.items():
        secret_id = os.getenv(env, '').strip()
        if not secret_id:
            raise ValueError(f'{env} is not set.')
        values[name] = read_secret(secret_id)
        if not values[name]:
            raise ValueError(f'The Vault secret in {env} is empty.')
    if '"' in values['db-password']:
        raise ValueError('The Keycloak database password may not contain a double quote.')
    return values


def statements(password, exists):
    """DDL for the KEYCLOAK user. Oracle DDL takes no bind variables, so the password is quoted inline."""
    if exists:
        first = [f'ALTER USER {USER} IDENTIFIED BY "{password}" ACCOUNT UNLOCK',
                 f'ALTER USER {USER} QUOTA {QUOTA} ON {TABLESPACE}']
    else:
        first = [f'CREATE USER {USER} IDENTIFIED BY "{password}" DEFAULT TABLESPACE {TABLESPACE} QUOTA {QUOTA} ON {TABLESPACE}']
    return first + [f'GRANT {", ".join(PRIVILEGES)} TO {USER}']


def ensure_user(engine, password):
    """Create KEYCLOAK (or reset its password to the Vault value) under the schema lock the worker also takes."""
    from sqlalchemy import text
    from .core import document_lock
    if engine.dialect.name != 'oracle':
        raise ValueError(f'Hosted Keycloak needs the Oracle database, not {engine.dialect.name}.')
    with document_lock('database-schema'):
        with engine.begin() as connection:
            exists = connection.execute(text('SELECT COUNT(*) FROM all_users WHERE username = :name'), {'name': USER}).scalar() > 0
            for statement in statements(password, exists):
                connection.execute(text(statement))
    return exists


def _write(path, value):
    """Owner-only file, written to a temporary name first so Keycloak never reads half a secret."""
    temporary = path.with_name(path.name + '.tmp')
    if temporary.exists():
        temporary.unlink()
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, 'w', encoding='utf-8', newline='') as file:
        file.write(value)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def write_files(root, values):
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    for name, value in values.items():
        _write(root / name, value)
    (root / READY).write_text('ready', encoding='utf-8')


def prepare(root, engine=None, read_secret=None):
    """Returns whether Keycloak was released (READY written). Never raises."""
    values = {}
    try:
        if read_secret is None:
            from .vault_master_key import read_secret
        values = _read(read_secret)
    except Exception as error:
        log.error('Hosted Keycloak stays stopped: its secrets could not be read from Vault (%s).',
                  _safe(error, values.values()))
        return False
    try:
        if engine is None:
            from .core import current_engine
            engine = current_engine()
        existed = ensure_user(engine, values['db-password'])
        log.info('Keycloak database user %s %s.', USER, 'updated' if existed else 'created')
    except Exception as error:
        # Keycloak still starts: the user may already exist with this password.
        log.error('Could not prepare the Keycloak database user (%s).', _safe(error, values.values()))
    try:
        write_files(root, values)
        return True
    except Exception as error:
        log.error('Could not hand Keycloak its secrets in %s (%s).', root, _safe(error, values.values()))
        return False
