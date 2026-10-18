from conftest import requires_esbmc, wait_for_task


def test_health_reports_ready(client):
    body = client.get('/health').get_json()
    assert body['status'] == 'ready'
    assert 'esbmc_version' in body


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
