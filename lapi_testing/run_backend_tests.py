"""Run pytest with disposable local state; never inherit live cloud settings."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('LAPI_', 'ORACLE_', 'OCI_', 'OPENAI_', 'AZURE_', 'AWS_', 'GOOGLE_',
            'EMBEDDING_', 'MODEL_', 'QDRANT_', 'DATABASE_')
PRIVATE_SETTINGS = {'MASTER_KEY', 'DATA_DIR', 'ALLOWED_ORIGINS', 'API_INTERNAL_URL', 'PYTHONPATH'}

def parallel(args):
    """Spread test files across CPU cores; conftest.py isolates each worker's state.

    Pass -n 0 (or any -n) to choose the worker count yourself; one file or test runs serially.
    """
    try:
        import xdist  # noqa: F401
    except ImportError:
        return []
    if any(a == '-n' or a.startswith(('-n', '--numprocesses')) for a in args):
        return ['-p', 'xdist.plugin']
    targets = [a for a in args if not a.startswith('-')]
    if len(targets) == 1:
        return []
    return ['-p', 'xdist.plugin', '-n', 'auto', '--dist', 'loadfile']

def main():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(PREFIXES) and key not in PRIVATE_SETTINGS}
    # Short names: parallel workers add popen-gwN to every path, and deep OCR cache
    # paths would otherwise pass the 260-character Windows limit.
    with tempfile.TemporaryDirectory(prefix='at-') as directory:
        state = Path(directory)
        env.update({
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            'PYTHONPATH': str(ROOT / 'lapi_backend'), 'LAPI_STORAGE_ROOT': str(state),
            'DATA_DIR': str(state), 'DATABASE_PROVIDER': 'sqlite',
            'DATABASE_URL': 'sqlite:///' + (state / 'test.db').as_posix(),
            'LAPI_ALLOW_MOCK': 'true', 'MODEL_PROVIDER': 'mock',
            'EMBEDDING_PROVIDER': 'mock', 'SEARCH_PROVIDER': 'local', 'STORAGE_PROVIDER': 'local',
        })
        command = [sys.executable, '-B', '-m', 'pytest', '-c', str(ROOT / 'lapi_testing/pytest.ini'),
                   '-q', '-p', 'no:cacheprovider', '--basetemp', str(state / 'p'),
                   *parallel(sys.argv[1:]), *sys.argv[1:]]
        return subprocess.call(command, cwd=ROOT / 'lapi_testing', env=env)

if __name__ == '__main__':
    raise SystemExit(main())
