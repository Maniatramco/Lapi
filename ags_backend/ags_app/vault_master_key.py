"""Master key held in OCI Vault instead of server configuration.

Every saved credential (model API keys, storage and database passwords) is
encrypted with one Fernet master key. When AEGIS_MASTER_KEY_SECRET_OCID is set,
that key is read from the OCI Vault secret with the server's own OCI identity
(instance principal by default) and is never written to disk or environment.
Without it, AEGIS_MASTER_KEY keeps working for local development.

Operator commands (the key is read from stdin and never printed):
  python -m ags_app.vault_master_key store --compartment-id ... --vault-id ... --key-id ...
  python -m ags_app.vault_master_key check
"""
import argparse
import base64
import os
import sys
import threading
from cryptography.fernet import Fernet
from .oci_adapters import _client, OCIProviderUnavailable

SECRET_ENV = 'AEGIS_MASTER_KEY_SECRET_OCID'
AUTH_ENV = 'AEGIS_VAULT_AUTH_MODE'
_cached = {}
_lock = threading.Lock()


class MasterKeyUnavailable(ValueError): pass


def _auth_mode():
    return os.getenv(AUTH_ENV, 'instance_principal')


def _valid(key):
    try:
        Fernet(key.encode())
        return True
    except Exception:
        return False


def read_secret(secret_id, client=None):
    """Return the current text of an OCI Vault secret; service details are not echoed."""
    client = client or _client('secrets', auth_mode=_auth_mode())
    try:
        content = client.get_secret_bundle(secret_id).data.secret_bundle_content.content
        return base64.b64decode(content).decode().strip()
    except OCIProviderUnavailable:
        raise
    except Exception:
        raise MasterKeyUnavailable('A secret could not be read from OCI Vault. Check the secret OCID, '
                                   'region and that this server may read secret bundles in the vault.') from None


def _fetch(secret_id, client=None):
    key = read_secret(secret_id, client)
    if not _valid(key):
        raise MasterKeyUnavailable('The OCI Vault secret does not contain a valid master key.')
    return key


def master_key(client=None):
    secret_id = os.getenv(SECRET_ENV, '').strip()
    local = os.getenv('AEGIS_MASTER_KEY', os.getenv('MASTER_KEY'))
    if not secret_id:
        return local
    if local:
        raise MasterKeyUnavailable(f'Set either {SECRET_ENV} or AEGIS_MASTER_KEY, not both. '
                                   'Remove AEGIS_MASTER_KEY once the key is stored in OCI Vault.')
    with _lock:
        if secret_id not in _cached:
            _cached[secret_id] = _fetch(secret_id, client)
        return _cached[secret_id]


def store(compartment_id, vault_id, key_id, name, key, client=None):
    if not _valid(key):
        raise MasterKeyUnavailable('Supply the existing Fernet master key (AEGIS_MASTER_KEY) on stdin.')
    from oci.vault.models import CreateSecretDetails, Base64SecretContentDetails
    client = client or _client('vaults', auth_mode=_auth_mode())
    details = CreateSecretDetails(
        compartment_id=compartment_id, vault_id=vault_id, key_id=key_id, secret_name=name,
        description='Lapi credential master key',
        secret_content=Base64SecretContentDetails(content_type='BASE64', content=base64.b64encode(key.encode()).decode()))
    return client.create_secret(details).data.id


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m ags_app.vault_master_key')
    commands = parser.add_subparsers(dest='command', required=True)
    put = commands.add_parser('store', help='Store the master key read from stdin as a new OCI Vault secret')
    put.add_argument('--compartment-id', required=True)
    put.add_argument('--vault-id', required=True)
    put.add_argument('--key-id', required=True)
    put.add_argument('--name', default='lapi-master-key')
    commands.add_parser('check', help=f'Confirm {SECRET_ENV} can be read and holds a valid key')
    args = parser.parse_args(argv)
    try:
        if args.command == 'store':
            key = sys.stdin.read(4096).strip()
            secret_id = store(args.compartment_id, args.vault_id, args.key_id, args.name, key)
            print(f'Stored. Set {SECRET_ENV}={secret_id} and remove AEGIS_MASTER_KEY from the server configuration.')
        else:
            if not os.getenv(SECRET_ENV, '').strip():
                raise MasterKeyUnavailable(f'{SECRET_ENV} is not set.')
            master_key()
            print('The master key was read from OCI Vault and is valid.')
        return 0
    except (MasterKeyUnavailable, OCIProviderUnavailable) as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print('The OCI Vault request failed. Check the OCIDs, region and permissions, then retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
