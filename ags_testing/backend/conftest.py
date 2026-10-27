"""Give each parallel test worker its own storage folder and SQLite database.

run_backend_tests.py runs files across pytest-xdist workers. The application reads
its storage root and database URL at import, so this must run before ags_app loads.
"""
import os
from pathlib import Path

worker = os.getenv('PYTEST_XDIST_WORKER')
if worker and os.getenv('AEGIS_STORAGE_ROOT'):
    state = Path(os.environ['AEGIS_STORAGE_ROOT']) / worker
    state.mkdir(parents=True, exist_ok=True)
    os.environ.update({'AEGIS_STORAGE_ROOT': str(state), 'DATA_DIR': str(state),
                       'DATABASE_URL': 'sqlite:///' + (state / 'test.db').as_posix()})
