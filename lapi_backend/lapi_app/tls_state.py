"""Keep the HTTPS certificate across deployments.

On OCI the Caddy container gets its certificate from Let's Encrypt and keeps it in the
instance's scratch volume, which is empty after every deployment. Let's Encrypt issues
only five certificates a week for one name, so the api saves Caddy's data folder to the
control store (Object Storage) and puts it back before Caddy starts.

Set LAPI_TLS_STATE_DIR to the folder Caddy sees as /data. Caddy waits for READY there.
"""
import asyncio
import hashlib
import io
import logging
import os
import tarfile
import time
from pathlib import Path
from . import core

log = logging.getLogger(__name__)
KEY = 'tls/caddy-data.tar.gz'
READY = '.lapi-restored'
LIMIT = 20 * 1024 * 1024  # Certificates, keys and ACME accounts: a few kilobytes.
INTERVAL = 300
_saved = {}  # Folder => fingerprint of what the control store holds, as far as this process knows.


def directory():
    value = os.getenv('LAPI_TLS_STATE_DIR', '').strip()
    return Path(value) if value else None


def _unreadable(error):
    log.warning('Cannot read %s to save the HTTPS certificate: %s', error.filename, error.strerror)


def _files(root):
    """Caddy's files worth keeping; locks and our marker change without meaning anything.
    A folder this process cannot read is logged, not skipped silently."""
    found = []
    for folder, _, names in os.walk(root, onerror=_unreadable):
        for name in names:
            path = Path(folder) / name
            if name != READY and 'locks' not in path.relative_to(root).parts and not name.endswith('.lock'):
                found.append(path)
    return sorted(found)


def fingerprint(root):
    digest = hashlib.sha256()
    for path in _files(root):
        digest.update(str(path.relative_to(root)).encode() + b'\0' + path.read_bytes() + b'\0')
    return digest.hexdigest()


def archive(root):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for path in _files(root):
            tar.add(path, arcname=str(path.relative_to(root)), recursive=False)
    return buffer.getvalue()


def restore(root, attempts=5, wait=3):
    """Put the saved folder back, then mark it ready so Caddy starts. Returns whether a copy was restored.

    If Object Storage cannot be read, Caddy still starts (and may request a new certificate)."""
    root.mkdir(parents=True, exist_ok=True)
    restored = False
    for attempt in range(attempts):
        try:
            if core.local_store.stat(KEY) is None:
                break
            data = core.local_store.get(KEY)
            if len(data) > LIMIT:
                raise ValueError('Saved HTTPS state is larger than expected.')
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
                tar.extractall(root, filter='data')  # No absolute paths, links out or devices.
            restored = True
            break
        except Exception as error:
            log.warning('Could not restore the HTTPS certificate (attempt %d): %s', attempt + 1, error)
            if attempt + 1 < attempts:
                time.sleep(wait)
    # Compare later saves with what was restored, not with the folder when the loop starts:
    # by then Caddy may already hold a new certificate that was never saved.
    _saved[str(root)] = fingerprint(root) if restored else ''
    (root / READY).write_text(str(int(time.time())))
    return restored


def save(root, last):
    """Save the folder when it changed since `last`; returns the fingerprint now saved."""
    current = fingerprint(root)
    if current != last and _files(root):
        core.local_store.put(KEY, archive(root))
        log.info('Saved the HTTPS certificate state.')
    return current


async def keep(root):
    last = _saved.get(str(root), '')
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            last = await asyncio.to_thread(save, root, last)
        except Exception as error:
            log.warning('Could not save the HTTPS certificate state: %s', error)
