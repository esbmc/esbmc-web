import os
import shutil
import subprocess
import sys
import time

import pytest

BACKEND = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, os.path.abspath(BACKEND))

import app as backend_app  # noqa: E402

requires_esbmc = pytest.mark.skipif(shutil.which('esbmc') is None, reason='esbmc not on PATH')


def known_defect(reason, **kwargs):
    """Strict xfail that only counts an AssertionError, so crashes or setup errors still fail."""
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason, **kwargs)


@pytest.fixture
def client():
    backend_app.app.config['TESTING'] = True
    with backend_app.app.test_client() as c:
        yield c


def wait_for_task(client, task_id, timeout=180, cancel_after=None, status_route='/status'):
    start = time.time()
    cancelled = False
    while True:
        status = client.get(f'{status_route}/{task_id}').get_json()
        if cancel_after is not None and not cancelled and time.time() - start > cancel_after:
            client.post(f'/cancelar/{task_id}')
            cancelled = True
        if status['status'] in ('completed', 'error'):
            return status
        if time.time() - start > timeout:
            client.post(f'/cancelar/{task_id}')
            pytest.fail(f'task {task_id} did not finish within {timeout}s')
        time.sleep(0.3)


def analyse(client, body, **kwargs):
    resp = client.post('/analisar', json=body)
    assert resp.status_code == 200
    return wait_for_task(client, resp.get_json()['task_id'], **kwargs)


@pytest.fixture
def local_repo(tmp_path):
    """Build a throw-away git repository so repository features run without network access."""
    def build(files):
        repo = tmp_path / 'repo'
        for rel, content in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
        subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=repo, check=True, env=env)
        return str(repo)
    return build
