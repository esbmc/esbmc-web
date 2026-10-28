import pytest

import app as backend_app
from conftest import requires_esbmc, wait_for_task


@requires_esbmc
def test_health_reports_ready_with_the_installed_version(client):
    body = client.get('/health').get_json()
    assert body['status'] == 'ready'
    assert body['esbmc_version'].startswith('ESBMC version')
    assert 'solver' not in body


def test_health_reports_unavailable_without_esbmc(client, monkeypatch):
    monkeypatch.setenv('PATH', '/nonexistent')
    resp = client.get('/health')
    assert resp.status_code == 503
    body = resp.get_json()
    assert body['status'] == 'unavailable' and body['error']
    assert 'esbmc_version' not in body


def test_status_of_unknown_task_is_404(client):
    assert client.get('/status/does-not-exist').status_code == 404


def test_fetch_repo_status_of_unknown_task_is_404(client):
    assert client.get('/fetch-repo-status/does-not-exist').status_code == 404


def test_cancel_unknown_task_is_rejected(client):
    assert client.post('/cancelar/does-not-exist').get_json() == {'success': False}


def test_fetch_repo_files_requires_url(client):
    assert client.post('/fetch-repo-files', json={}).status_code == 400


def test_fetch_file_content_requires_url_and_path(client):
    assert client.post('/fetch-file-content', json={'git_url': 'x'}).status_code == 400


def test_fetch_file_content_rejects_traversal(client):
    for bad in ('../etc/passwd', '/etc/passwd', 'a/../../b.c'):
        resp = client.post('/fetch-file-content', json={'git_url': 'https://github.com/esbmc/esbmc', 'file_path': bad})
        assert resp.status_code == 400, bad


def test_analysis_without_code_ends_in_error(client):
    task_id = client.post('/analisar', json={'language': 'c', 'codigo': '', 'flags': []}).get_json()['task_id']
    status = wait_for_task(client, task_id, timeout=30)
    assert status['status'] == 'error'
    assert status['resultado'] is None


def test_analysis_rejects_non_json_body(client):
    assert client.post('/analisar', data='x', content_type='text/plain').status_code == 415


def test_fetch_repo_files_lists_only_source_files_in_subdir(client, local_repo):
    repo = local_repo({'src/a.c': 'int a;', 'src/b.txt': 'x', 'other/c.py': 'x = 1\n'})
    task_id = client.post('/fetch-repo-files', json={'git_url': repo, 'subdir_filter': 'src'}).get_json()['task_id']
    status = wait_for_task(client, task_id, timeout=60, status_route='/fetch-repo-status')
    assert status['status'] == 'completed'
    assert status['files'] == ['src/a.c']
    assert sorted(status['all_files']) == ['other/c.py', 'src/a.c']


def test_fetch_file_content_reads_file_from_repo(client, local_repo):
    repo = local_repo({'src/a.c': 'int answer = 42;\n'})
    task_id = client.post('/fetch-file-content', json={'git_url': repo, 'file_path': 'src/a.c'}).get_json()['task_id']
    status = wait_for_task(client, task_id, timeout=60, status_route='/fetch-repo-status')
    assert status['status'] == 'completed'
    assert status['content'].strip() == 'int answer = 42;'


def test_fetch_repo_files_bad_url_reports_error(client, tmp_path):
    task_id = client.post('/fetch-repo-files', json={'git_url': str(tmp_path / 'missing')}).get_json()['task_id']
    status = wait_for_task(client, task_id, timeout=60, status_route='/fetch-repo-status')
    assert status['status'] == 'error'
    assert status['error']


@requires_esbmc
def test_help_returns_esbmc_usage(client):
    assert '--unwind' in client.get('/help').get_json()['help_text']


@pytest.mark.parametrize('route, body', [
    ('/fetch-repo-files', 'null'),
    ('/fetch-repo-files', '{"git_url": 5}'),
    ('/fetch-file-content', 'null'),
    ('/fetch-file-content', '[]'),
    ('/fetch-file-content', '{"git_url": "x", "file_path": 5}'),
    ('/analisar', 'null'),
    ('/analisar', '[]'),
    ('/analisar', '{"language": "c", "codigo": "int main(){}", "flags": "--unwind"}'),
    ('/analisar', '{"language": "c", "codigo": "int main(){}", "flags": ["--unwind", 3]}'),
    ('/analisar', '{"language": "c", "codigo": 5, "flags": []}'),
    ('/analisar', '{"language": "c", "codigo": "int main(){}", "flags": [], "dependencies": [{"filename": "a.h"}]}'),
    ('/analisar', '{"language": "c", "codigo": "int main(){}", "flags": [], "dependencies": {"filename": "a.h"}}'),
])
def test_malformed_body_is_rejected_with_400(route, body):
    backend_app.app.config['PROPAGATE_EXCEPTIONS'] = False
    with backend_app.app.test_client() as c:
        resp = c.post(route, data=body, content_type='application/json')
    assert resp.status_code == 400, (route, body, resp.status_code)
    assert resp.get_json()['error']


def test_debug_mode_is_off_by_default(monkeypatch):
    monkeypatch.delenv('ESBMC_WEB_DEBUG', raising=False)
    assert backend_app.modo_debug() is False
    monkeypatch.setenv('ESBMC_WEB_DEBUG', '1')
    assert backend_app.modo_debug() is True


def test_analysis_accepts_function_contract_flags(client):
    task_id = client.post('/analisar', json={
        'language': 'c',
        'codigo': 'int f(int x){ return x; }',
        'flags': ['--enforce-contract', 'f', '--replace-call-with-contract', 'g']
    }).get_json()['task_id']
    status = wait_for_task(client, task_id, timeout=30)
    assert status['status'] == 'completed'
    logs = status.get('logs', '')
    assert '--enforce-contract' in logs
    assert '--replace-call-with-contract' in logs
    assert "[SYSTEM] [Function Contracts] Enforcing contract for 'f'" in logs
    assert "[SYSTEM] [Function Contracts] Replacing calls to 'g' with contract abstraction" in logs

