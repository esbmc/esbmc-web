"""Verdict-correctness tests against a real ESBMC binary.

Tests marked xfail(strict=True) pin confirmed soundness defects: the assertion states the
correct behaviour, and the test turns into an XPASS failure once the defect is fixed.
"""
import sys

import pytest

from conftest import analyse, known_defect, requires_esbmc, wait_for_task

pytestmark = requires_esbmc

C_SAFE = '#include <assert.h>\nint main(){int x=5; assert(x==5); return 0;}\n'
C_UNSAFE = '#include <assert.h>\nint main(){int x=5; assert(x==6); return 0;}\n'
C_DEEP_LOOP_BUG = '#include <assert.h>\nint main(){for(int i=0;i<10;i++){ assert(i!=5);} return 0;}\n'
C_PARSE_ERROR = 'int main( { return 0 }\n'
C_SLOW = ('unsigned nondet_uint();\nint main(){ unsigned s=0; for (unsigned i=0;i<5000000;i++)'
          '{ s = s*31u + nondet_uint(); } __ESBMC_assert(s != 7u, "s"); return 0; }\n')


def result(status):
    if status['status'] != 'completed':
        pytest.fail(f"analysis did not complete: {status['logs'][-2000:]}")
    return status['resultado']


def has_violation(res):
    return any(isinstance(r, dict) and r.get('status') == 'violation' for r in res['dashboard_data'])


class TestSingleFileC:
    def test_safe_program_is_successful(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_SAFE, 'flags': []}))
        assert res['verificacao_sucesso'] is True
        assert not has_violation(res)

    def test_failing_assertion_is_reported_with_counterexample(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_UNSAFE, 'flags': []}))
        assert res['verificacao_sucesso'] is False
        violation = next(r for r in res['dashboard_data'] if r['status'] == 'violation')
        step = next(s for s in violation['steps'] if s['type'] == 'violation')
        assert step['line'] == '2'
        assert step['cwe'] == 'CWE-617'

    def test_out_of_bounds_write_is_found_with_initial_values(self, client):
        code = 'int nondet_int();\nint main(){int a[4]; int i=nondet_int(); if(i>=0 && i<=4) a[i]=1; return 0;}\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': []}))
        assert res['verificacao_sucesso'] is False
        violation = next(r for r in res['dashboard_data'] if r['status'] == 'violation')
        assert violation['initial_values']['i']['value'] == '4'

    def test_witnesses_and_html_report_are_returned(self, client):
        flags = ['--generate-html-report', '--witness-output', 'auto-witness.graphml',
                 '--witness-output-yaml', 'auto-witness.yaml']
        res = result(analyse(client, {'language': 'c', 'codigo': C_UNSAFE, 'flags': flags}))
        assert '<graphml' in res['graphml_report_data']
        assert res['yaml_report_data']
        assert '<html' in res['html_report_data'].lower()

    def test_parse_error_is_not_successful(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_PARSE_ERROR, 'flags': []}))
        assert res['verificacao_sucesso'] is False
        assert res['verdict'] == 'ERROR'
        assert not any(r.get('status') == 'successful' for r in res['dashboard_data'])

    def test_timeout_is_not_successful(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_SLOW,
                                      'flags': ['--unwind', '5000001', '--timeout', '3']}))
        assert res['verificacao_sucesso'] is False
        assert res['verdict'] == 'TIMEOUT'
        assert not any(r.get('status') == 'successful' for r in res['dashboard_data'])

    def test_user_dependency_is_compiled_and_name_is_confined(self, client):
        deps = [{'filename': '../../lib.h', 'content': 'int lib(int x);\n'},
                {'filename': 'lib.c', 'content': 'int lib(int x){ return x + 1; }\n'}]
        # SUCCESSFUL is only reachable if lib.h was stored under its basename (else it is mocked)
        # and lib.c was linked (else lib() is a nondet stub and the assertion can fail).
        code = '#include <assert.h>\n#include "lib.h"\nint main(){ assert(lib(1) == 2); return 0; }\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': [], 'dependencies': deps}))
        assert res['verificacao_sucesso'] is True

    def test_raw_mode_finds_deep_loop_bug(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_DEEP_LOOP_BUG, 'flags': [],
                                      'verification_engine_mode': 'raw_esbmc'}))
        assert res['verificacao_sucesso'] is False

    def test_assisted_mode_does_not_prove_deep_loop_bug_safe(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_DEEP_LOOP_BUG, 'flags': []}))
        assert res['verificacao_sucesso'] is False

    def test_loop_beyond_default_bound_reports_unwinding_assertion(self, client):
        code = '#include <assert.h>\nint main(){int s=0; for(int i=0;i<10;i++) s++; assert(s==10); return 0;}\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'FAILED'
        messages = ' '.join(str(s.get('message', '')) for r in res['dashboard_data'] for s in r.get('steps', []))
        assert 'unwinding assertion' in messages

    def test_loop_within_default_bound_is_successful(self, client):
        code = '#include <assert.h>\nint main(){int s=0; for(int i=0;i<2;i++) s++; assert(s==2); return 0;}\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'SUCCESSFUL'

    def test_cancelled_run_is_not_successful(self, client):
        res = result(analyse(client, {'language': 'c', 'codigo': C_SLOW, 'flags': ['--unwind', '5000001']},
                             cancel_after=3))
        assert res['verificacao_sucesso'] is False
        assert res['verdict'] == 'CANCELLED'
        assert not any(r.get('status') == 'successful' for r in res['dashboard_data'])

    def test_concurrent_requests_keep_independent_verdicts(self, client):
        ids = {}
        for name, code in (('safe', C_SAFE), ('unsafe', C_UNSAFE)) * 2:
            ids.setdefault(name, []).append(
                client.post('/analisar', json={'language': 'c', 'codigo': code, 'flags': []}).get_json()['task_id'])
        for name, expected in (('safe', True), ('unsafe', False)):
            for task_id in ids[name]:
                assert result(wait_for_task(client, task_id))['verificacao_sucesso'] is expected

    @known_defect(condition=sys.platform == 'darwin', reason='D8 (#18): -I <clang resource dir> shadows ESBMC headers -> PARSING ERROR on macOS')
    def test_c_program_using_stdint_parses(self, client):
        code = '#include <stdint.h>\n#include <assert.h>\nint main(){uint8_t x=1; assert(x==2); return 0;}\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': []}))
        assert has_violation(res)


class TestSingleFileCpp:
    @known_defect(condition=sys.platform == 'darwin', reason='D8 (#18): -I <clang resource dir> shadows ESBMC headers -> PARSING ERROR on macOS')
    def test_failing_assertion_is_reported(self, client):
        code = '#include <cassert>\nint main(){int x=1; assert(x==2); return 0;}\n'
        res = result(analyse(client, {'language': 'cpp', 'codigo': code, 'flags': []}))
        assert has_violation(res)


class TestSingleFilePython:
    def test_safe_program_is_successful(self, client):
        res = result(analyse(client, {'language': 'python', 'codigo': 'x: int = 5\nassert x == 5\n', 'flags': []}))
        assert res['verificacao_sucesso'] is True

    def test_failing_assertion_is_reported(self, client):
        res = result(analyse(client, {'language': 'python', 'codigo': 'x: int = 5\nassert x == 6\n', 'flags': []}))
        assert res['verificacao_sucesso'] is False
        assert has_violation(res)

    def test_assertion_inside_called_function_is_reported(self, client):
        code = 'def f(x: int) -> int:\n    assert x != 3\n    return x\n\nf(3)\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verificacao_sucesso'] is False

    @known_defect('D4 (#14): homogenizer replaces the body of div() with "return 200"')
    def test_homogenized_function_keeps_original_body(self, client):
        code = 'def div(a: int, b: int) -> int:\n    return a // b\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert 'a // b' in res['codigo_analisado']

    def test_homogenized_run_is_never_reported_successful(self, client):
        code = 'import os\n\ndef f(n: int) -> int:\n    assert n >= 0\n    return n\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'MODEL_ONLY'
        assert res['verificacao_sucesso'] is False
        assert not any(r.get('status') == 'successful' for r in res['dashboard_data'])


class TestRepository:
    def test_single_file_from_repo_finds_bug(self, client, local_repo):
        repo = local_repo({'src/bug.c': C_UNSAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'main_file_path': 'src/bug.c', 'flags': []}))
        assert res['verificacao_sucesso'] is False
        assert res['repo_exploration_summary'][0]['status'].startswith('VIOLATION')

    def test_missing_target_file_is_an_error(self, client, local_repo):
        repo = local_repo({'src/a.c': C_SAFE})
        status = analyse(client, {'language': 'c', 'git_url': repo, 'main_file_path': 'src/nope.c', 'flags': []})
        assert status['status'] == 'error'

    def test_exploration_reports_violation_and_generates_reports(self, client, local_repo):
        repo = local_repo({'src/ok.c': C_SAFE, 'src/bug.c': C_UNSAFE, 'docs/readme.md': 'x'})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        statuses = {r['file']: r['status'] for r in res['repo_exploration_summary']}
        assert set(statuses) == {'src/ok.c', 'src/bug.c'}
        assert statuses['src/bug.c'].startswith('VIOLATION')
        assert res['verificacao_sucesso'] is False
        assert len(res['csv_report'].splitlines()) == 3
        assert '\\begin{tabular}' in res['latex_table']

    def test_subdirectory_filter_limits_targets(self, client, local_repo):
        repo = local_repo({'src/ok.c': C_SAFE, 'other/bug.c': C_UNSAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True,
                                      'repo_subdir_filter': 'src', 'flags': []}))
        assert [r['file'] for r in res['repo_exploration_summary']] == ['src/ok.c']

    def test_exploration_does_not_report_unparseable_module_as_safe(self, client, local_repo):
        repo = local_repo({'src/broken.c': C_PARSE_ERROR, 'src/ok.c': C_SAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        statuses = {r['file']: r['status'] for r in res['repo_exploration_summary']}
        assert statuses['src/broken.c'] == 'ERROR (NO VERDICT)'
        assert res['verdict'] == 'UNKNOWN'
        assert res['verificacao_sucesso'] is False

    def test_exploration_of_safe_repository_is_successful(self, client, local_repo):
        repo = local_repo({'src/ok.c': C_SAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['verdict'] == 'SUCCESSFUL'

    def test_exploration_does_not_report_homogenized_python_as_safe(self, client, local_repo):
        repo = local_repo({'pkg/m.py': 'import os\n\ndef f(n: int) -> int:\n    return 10 // n\n'})
        res = result(analyse(client, {'language': 'python', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'] == 'MODEL_ONLY (NO VERDICT)'
        assert res['verificacao_sucesso'] is False

    def test_single_repo_file_parse_error_is_not_labelled_safe(self, client, local_repo):
        repo = local_repo({'src/broken.c': C_PARSE_ERROR})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'main_file_path': 'src/broken.c', 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'] == 'ERROR (NO VERDICT)'

    def test_repository_comment_cannot_disable_assertions(self, client, local_repo):
        code = '// esbmc-flags: --no-assertions\n#include <assert.h>\nint main(){ assert(0); return 0; }\n'
        repo = local_repo({'src/d.c': code})
        status = analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []})
        res = result(status)
        assert res['verdict'] == 'FAILED'
        assert res['repo_exploration_summary'][0]['status'].startswith('VIOLATION')
        assert 'Ignoring check-disabling repository directive(s) in src/d.c: --no-assertions' in status['logs']

    def test_exploration_does_not_prove_deep_loop_bug_safe(self, client, local_repo):
        repo = local_repo({'src/deep.c': C_DEEP_LOOP_BUG})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['verificacao_sucesso'] is False
