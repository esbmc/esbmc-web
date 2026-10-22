"""Verdict-correctness tests against a real ESBMC binary.

Tests marked xfail(strict=True) pin confirmed soundness defects: the assertion states the
correct behaviour, and the test turns into an XPASS failure once the defect is fixed.
"""

import os

import pytest

import app as backend_app
from conftest import analyse, commit, requires_esbmc, wait_for_task

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
        assert res['verdict'] == 'BOUND_REACHED'
        assert res['verificacao_sucesso'] is False
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

    def test_c_program_using_stdint_parses(self, client):
        code = '#include <stdint.h>\n#include <assert.h>\nint main(){uint8_t x=1; assert(x==2); return 0;}\n'
        res = result(analyse(client, {'language': 'c', 'codigo': code, 'flags': []}))
        assert has_violation(res)


class TestSingleFileCpp:
    CONTAINERS = ('#include <cassert>\n#include <vector>\n#include <string>\n#include <map>\n'
                  'int main(){ std::vector<int> v{1,2,3}; std::map<int,int> m; m[1]=2;\n'
                  '  std::string s("ab"); assert(v.size()==3 && m[1]==2 && s.size()==2); return 0; }\n')

    def test_library_loop_beyond_default_bound_is_bound_reached(self, client):
        res = result(analyse(client, {'language': 'cpp', 'codigo': self.CONTAINERS, 'flags': []}))
        assert res['verdict'] == 'BOUND_REACHED'

    def test_safe_program_using_std_containers_is_successful_with_enough_unwinding(self, client):
        res = result(analyse(client, {'language': 'cpp', 'codigo': self.CONTAINERS, 'flags': ['--unwind', '101']}))
        assert res['verdict'] == 'SUCCESSFUL'

    def test_out_of_bounds_vector_access_is_found(self, client):
        code = '#include <vector>\nint main(){ std::vector<int> v(2); int a[2]; a[v.size()] = 1; return 0; }\n'
        res = result(analyse(client, {'language': 'cpp', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'FAILED'

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

    def test_harness_keeps_original_function_body(self, client):
        code = 'def div(a: int, b: int) -> int:\n    return a // b\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['codigo_analisado'].startswith(code)
        assert res['verdict'] != 'SUCCESSFUL'

    def test_harnessed_safe_function_is_successful(self, client):
        code = 'import os\n\ndef f(n: int) -> int:\n    if n > 0:\n        return n\n    return -n\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'SUCCESSFUL'

    def test_unsupported_library_call_is_not_reported_as_a_bug(self, client):
        code = 'import os\n\ndef f(p: str) -> str:\n    return os.path.join(p, "x")\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'UNSUPPORTED'

    def test_harness_reports_partial_when_functions_are_not_exercised(self, client):
        code = ('import os\n\nclass C:\n    def m(self, y: int) -> int:\n        return 10 // y\n\n'
                'def g(n: int) -> int:\n    return n\n')
        status = analyse(client, {'language': 'python', 'codigo': code, 'flags': []})
        res = result(status)
        assert res['verdict'] == 'PARTIAL'
        assert res['verificacao_sucesso'] is False
        assert 'not exercised: C.m' in status['logs']

    def test_real_bug_after_unsupported_call_is_still_found(self, client):
        code = 'import os\n\ndef f(x: int) -> int:\n    p = os.path.join("a", "b")\n    assert x != 3\n    return x\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'FAILED'

    def test_harness_explores_negative_inputs(self, client):
        code = 'import os\n\ndef f(n: int) -> int:\n    assert n >= 0\n    return n\n'
        res = result(analyse(client, {'language': 'python', 'codigo': code, 'flags': []}))
        assert res['verdict'] == 'FAILED'
        assert res['codigo_analisado'].startswith(code)

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

    def test_exploration_harness_finds_bug_in_uncalled_python_function(self, client, local_repo):
        repo = local_repo({'pkg/m.py': 'import os\n\ndef f(n: int) -> int:\n    assert n != 3\n    return n\n'})
        res = result(analyse(client, {'language': 'python', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'].startswith('VIOLATION')
        assert res['verdict'] == 'FAILED'

    def test_repository_directive_cannot_smuggle_flag_as_value(self, client, local_repo):
        code = '// esbmc-flags: --unwind 3 --unwind --no-assertions\n#include <assert.h>\nint main(){ assert(0); return 0; }\n'
        repo = local_repo({'src/d.c': code})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['verdict'] == 'FAILED'

    def test_oracles_grade_found_bug_and_proved_safe_as_passes(self, client, local_repo):
        repo = local_repo({
            'src/bug.c': '// esbmc-expected: FAILED\n' + C_UNSAFE,
            'src/ok.c': '// esbmc-expected: SUCCESSFUL\n' + C_SAFE,
        })
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True,
                                      'test_suite_mode': True, 'flags': []}))
        codes = {r['file']: r['test_status_code'] for r in res['repo_exploration_summary']}
        assert codes == {'src/bug.c': 'PASS_BUG_FOUND', 'src/ok.c': 'PASS_SOUND'}

    @staticmethod
    def _patch_esbmc(monkeypatch, fake_for):
        """Record esbmc commands; replace the first one for which fake_for(cmd) returns a shell script."""
        real_popen = backend_app.subprocess.Popen
        commands = []

        def popen(cmd, *args, **kwargs):
            if cmd and cmd[0] == 'esbmc':
                commands.append(list(cmd))
                script = fake_for(cmd)
                if script and not any(c[0] == 'fake' for c in commands):
                    commands[-1] = ['fake'] + commands[-1]
                    return real_popen(['sh', '-c', script], *args, **kwargs)
            return real_popen(cmd, *args, **kwargs)

        monkeypatch.setattr(backend_app.subprocess, 'Popen', popen)
        return commands

    def test_multi_tu_retry_keeps_phase_two_flags(self, client, local_repo, monkeypatch):
        commands = self._patch_esbmc(monkeypatch, lambda cmd: 'exit 134' if '--overflow-check' in cmd else None)
        repo = local_repo({'src/ok.c': C_SAFE})
        result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        aborted = next(i for i, c in enumerate(commands) if c[0] == 'fake')
        assert '--overflow-check' in commands[aborted + 1]

    def test_phase_two_without_verdict_is_not_reported_safe(self, client, local_repo, monkeypatch):
        self._patch_esbmc(monkeypatch, lambda cmd: 'echo "ERROR: Timed out"; exit 1' if '--overflow-check' in cmd else None)
        repo = local_repo({'src/ok.c': C_SAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'] == 'TIMEOUT (NO VERDICT)'
        assert res['verificacao_sucesso'] is False

    def test_phase_one_failure_survives_phase_two_only_mode(self, client, local_repo, monkeypatch):
        self._patch_esbmc(monkeypatch, lambda cmd: 'echo "ERROR: Timed out"; exit 1' if '--overflow-check' in cmd else None)
        repo = local_repo({'src/bug.c': C_UNSAFE})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True,
                                      'verification_phases': '2', 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'].startswith('VIOLATION')
        assert res['verdict'] == 'FAILED'

    def test_bound_only_phase_one_still_runs_phase_two(self, client, local_repo, monkeypatch):
        unwinding_only = "printf 'Violated property:\\n  unwinding assertion loop 0\\n\\nVERIFICATION FAILED\\n'; exit 1"
        commands = self._patch_esbmc(monkeypatch, lambda cmd: None if '--overflow-check' in cmd else unwinding_only)
        repo = local_repo({'src/ok.c': C_SAFE})
        result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert any('--overflow-check' in c for c in commands)

    def test_bound_reached_module_counts_no_violation(self, client, local_repo):
        code = '#include <assert.h>\nint main(){int s=0; for(int i=0;i<10;i++) s++; assert(s==10); return 0;}\n'
        repo = local_repo({'src/loop.c': code})
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        row = res['repo_exploration_summary'][0]
        assert row['status'] == 'BOUND_REACHED (NO VERDICT)'
        assert row['violations'] == 0

    def test_repository_symlinks_cannot_reach_outside_the_clone(self, client, local_repo, tmp_path):
        outside = tmp_path / 'outside'
        outside.mkdir()
        secret = outside / 'secret.txt'
        secret.write_text('top secret\n')
        repo = local_repo({'src/ok.cpp': '#include <cassert>\nint main(){ assert(1); return 0; }\n'})
        os.symlink(secret, os.path.join(repo, 'src', 'leak.cpp'))
        os.symlink(outside, os.path.join(repo, 'mock_boost'), target_is_directory=True)
        commit(repo)
        status = analyse(client, {'language': 'cpp', 'git_url': repo, 'explore_repo': True, 'flags': []})
        res = result(status)
        assert sorted(p.name for p in outside.iterdir()) == ['secret.txt']
        assert secret.read_text() == 'top secret\n'
        assert 'top secret' not in res['codigo_analisado']
        assert 'Removed symlink(s) pointing outside the repository: mock_boost, src/leak.cpp' in status['logs']

    @pytest.mark.parametrize('mode', ['assisted', 'raw_esbmc'])
    def test_main_file_path_cannot_read_outside_the_clone(self, client, local_repo, tmp_path, mode):
        secret = tmp_path / 'secret.c'
        secret.write_text('int top_secret_marker;\n')
        repo = local_repo({'src/ok.c': C_SAFE})
        for path in ('../' * 12 + str(secret).lstrip('/'), str(secret)):
            status = analyse(client, {'language': 'c', 'git_url': repo, 'main_file_path': path, 'flags': [],
                                      'verification_engine_mode': mode})
            assert status['status'] == 'error'
            assert 'top_secret_marker' not in status['logs']
            assert status['resultado'] is None

    def test_main_file_path_cannot_rewrite_headers_outside_the_clone(self, client, local_repo, tmp_path):
        victim = tmp_path / 'victim'
        victim.mkdir()
        header = victim / 'lib.hpp'
        header.write_text('consteval int f(){ return 1; }\n')
        repo = local_repo({'src/ok.cpp': 'int main(){ return 0; }\n'})
        status = analyse(client, {'language': 'cpp', 'git_url': repo, 'main_file_path': str(victim / 'nonexistent.cpp'),
                                  'codigo': 'int main(){ return 0; }\n', 'flags': []})
        assert status['status'] == 'error'
        assert header.read_text() == 'consteval int f(){ return 1; }\n'

    def test_exploration_marks_unsupported_library_call_as_no_verdict(self, client, local_repo):
        repo = local_repo({'pkg/p.py': 'import os\n\ndef f(p: str) -> str:\n    return os.path.join(p, "x")\n'})
        res = result(analyse(client, {'language': 'python', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        row = res['repo_exploration_summary'][0]
        assert row['status'] == 'UNSUPPORTED (NO VERDICT)'
        assert row['violations'] == 0
        assert res['verdict'] == 'UNKNOWN'

    def test_exploration_finds_real_bug_after_unsupported_call(self, client, local_repo):
        repo = local_repo({'pkg/p.py': 'import os\n\ndef f(x: int) -> int:\n    p = os.path.join("a", "b")\n    assert x != 3\n    return x\n'})
        res = result(analyse(client, {'language': 'python', 'git_url': repo, 'explore_repo': True, 'flags': []}))
        assert res['repo_exploration_summary'][0]['status'].startswith('VIOLATION')

    def test_implementation_in_another_directory_is_linked(self, client, local_repo):
        repo = local_repo({
            'lib/lib.c': '#include <assert.h>\n#include "lib.h"\nint helper(int x){ assert(x != 3); return x; }\n',
            'lib/lib.h': 'int helper(int x);\n',
            'app/main.c': '#include "../lib/lib.h"\nint nondet_int();\nint main(){ return helper(nondet_int()); }\n',
        })
        res = result(analyse(client, {'language': 'c', 'git_url': repo, 'main_file_path': 'app/main.c', 'flags': []}))
        assert res['verdict'] == 'FAILED'

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
