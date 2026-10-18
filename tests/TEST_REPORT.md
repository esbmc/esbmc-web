# ESBMC-Web Test Plan and Execution Report

Baseline: `main` @ `d17af99` · Run date: 2026-10-18 · Branch: `test/comprehensive-test-suite`

## 1. Environment

| Item | Value |
|---|---|
| OS | macOS (Darwin 25.6, arm64) |
| ESBMC | 8.6.0 64-bit aarch64 macos (default solver Bitwuzla 0.9.1) |
| Python / Flask / GitPython | 3.14.6 / 3.1.3 / 3.2.1 |
| Clang | Apple clang 21.0.0 |
| Browser | Google Chrome (headless, driven over DevTools protocol) |
| Not available | Windows/WSL (the `.bat` launchers and `runner.sh`'s `dpkg`/`ss` path), Linux ESBMC build |

## 2. Feature inventory

| # | Feature | Frontend | Backend | Status after testing |
|---|---|---|---|---|
| F1 | Single-file C verification | editor, `#lang-c`, Analyze | `POST /analisar`, `rodar_esbmc`, `sanitizar_c` | Works; unsound default bound (D1) |
| F2 | Single-file C++ verification | `#lang-cpp` | `sanitizar_cpp`, `mock_boost` | **Broken on macOS** (D8); unsound rewrites (D7) |
| F3 | Single-file Python verification | `#lang-py`, interpreter field | `sanitizar_python`, homogenizer v2 | Native path works; homogenizer unsound (D4) |
| F4 | Uploaded dependencies (multi-file) | dependency input | `dependencies[]` → temp dir, `.c/.cpp` linked | Works; names confined with `basename` |
| F5 | Git file listing / subfolder filter / `tree`/`blob` URL parsing | Fetch Repository | `/fetch-repo-files`, `/fetch-repo-status`, `normalizar_url_e_subpasta_git` | Works |
| F6 | Git file content fetch | file select | `/fetch-file-content` | Works; rejects `..` and absolute paths |
| F7 | Single repo file verification + dependency resolution | git URL + main file | clone, `resolver_fontes_dependentes_cpp`, `fundir_dependencias_internas_python` | Bug detection works; errors mislabelled SAFE (D5) |
| F8 | Repository exploration (RepoSlice-BMC), phases, language filter | Explore Repository | explore branch of `executar_background`, `descobrir_alvos_verificaveis_repositorio` | Unsound: D1, D5, D6 |
| F9 | Raw ESBMC baseline mode | engine mode select | `verification_engine_mode=raw_esbmc` | Works (finds deep-loop bug) |
| F10 | Counterexample / trace / initial values / CWE mapping | dashboard | JSON report parsing, `MAPEAMENTO_CWE` | Works |
| F11 | Witnesses (GraphML, YAML), HTML report | report tabs | glob of temp dir | Works |
| F12 | LaTeX table / CSV (exploration only) | Copy LaTeX / Download CSV | exploration summary | Generated; inherits wrong verdicts |
| F13 | Timeout | `--timeout` field | ESBMC `--timeout` + watchdog | Backend correct; UI shows success (D3) |
| F14 | Cancellation | Stop Analysis | `/cancelar/<id>` | **Reported as success** (D2, D3) |
| F15 | Health / help | startup overlay, help modal | `/health`, `/help` | Works (`solver` string in `/health` is hard-coded) |
| F16 | Professional test-suite mode / oracles | — | `test_suite_mode`, `avaliar_status_teste` | Unit-tested only |
| F17 | Windows launchers, port auto-free | `.bat`, `runner.sh` | — | Not testable here |

## 3. Risk-based plan and traceability

Priority follows the brief: soundness > security > robustness > coverage. Automated tests live in `tests/`; `xfail(strict=True)` marks a confirmed defect (the assertion encodes the correct behaviour).

| Test ID | Feature | Risk addressed | Automated test | Result |
|---|---|---|---|---|
| U-01..05 | F5 | wrong repo/subdir/file from URL | `test_helpers.py::TestGitUrlNormalisation` | PASS |
| U-06..09 | F16 | oracle mis-classification | `test_helpers.py::TestOracleComparison` | PASS |
| U-10 | F8 | wrong `--function` target | `test_helpers.py::...test_c_prefers_function_with_asserts_and_branches` | XFAIL → D10 |
| U-11..13 | F8 | target discovery edge cases | `test_helpers.py::TestTargetFunctionDiscovery` | PASS |
| U-14 | security | solver/interpreter override via flags | `test_flag_allowlist_excludes_solver_program_override` | PASS |
| A-01..07 | F14/F15/F6 | API validation, 404s, traversal | `test_api.py` | PASS |
| A-08..09 | input validation | empty code, non-JSON body | `test_api.py` | PASS |
| A-10..12 | F5/F6 | git listing, subdir filter, bad URL | `test_api.py` (local fixture repo) | PASS |
| V-C-01..04 | F1/F10/F11 | safe/unsafe classification, counterexample, witnesses | `test_verification.py::TestSingleFileC` | PASS |
| V-C-05 | F1 | parse error not success (backend) | `test_parse_error_is_not_successful` | PASS |
| V-C-06 | F13 | timeout not success (backend) | `test_timeout_is_not_successful` | PASS |
| V-C-07 | F4 | dependency linking, name confinement | `test_user_dependency_is_compiled_and_name_is_confined` | PASS |
| V-C-08 | F9 | raw mode completeness | `test_raw_mode_finds_deep_loop_bug` | PASS |
| V-C-09 | F1 | **bug beyond default unwind** | `test_assisted_mode_finds_deep_loop_bug` | XFAIL → D1 |
| V-C-10 | F14 | **cancel ≠ success** | `test_cancelled_run_is_not_successful` | XFAIL → D2 |
| V-C-11 | concurrency | 4 parallel tasks keep own verdicts | `test_concurrent_requests_keep_independent_verdicts` | PASS |
| V-CPP-01..02 | F2 | C++ / `<stdint.h>` parse | `TestSingleFileCpp` | XFAIL (macOS) → D8 |
| V-PY-01..03 | F3 | Python safe/unsafe/in-function assert | `TestSingleFilePython` | PASS |
| V-PY-04..05 | F3 | **homogenizer soundness** | `TestSingleFilePython::test_homogenized_*` | XFAIL → D4 |
| V-R-01..04 | F7/F8/F12 | repo bug detection, missing file, CSV/LaTeX, subdir filter | `TestRepository` | PASS |
| V-R-05..06 | F7/F8 | **parse error not SAFE** | `TestRepository::test_*parse*` / `unparseable` | XFAIL → D5 |
| V-R-07 | F8 | **repo directive cannot disable checks** | `test_repository_comment_cannot_disable_assertions` | XFAIL → D6 |
| V-R-08 | F8 | bug beyond default unwind (exploration) | `test_exploration_finds_deep_loop_bug` | XFAIL → D1 |
| S-01..05 | F3/F1 | homogenizer trigger, native path preserved, C harness, header mocks | `test_sanitizers.py` | PASS |
| S-06 | F3 | homogenizer preserves body | `test_homogenized_output_preserves_function_body` | XFAIL → D4 |
| S-07..08 | security | header mock path containment (C, C++) | `test_mock_headers_stay_inside_work_dir` | XFAIL → D9 |
| S-09 | F2 | C++ rewrite preserves verdict | `test_rewrite_preserves_virtual_dispatch_verdict` | XFAIL → D7 |
| E2E-01..02 | F1 UI | banner for FAILED / SUCCESSFUL | `tests/e2e/ui_verdicts.mjs` | PASS |
| E2E-03..05 | F13/F14 UI | **banner for parse error / timeout / cancel** | `tests/e2e/ui_verdicts.mjs` | FAIL → D3 |

Each test's steps, data and expected result are the test body itself; the probes used during exploratory testing are reproduced verbatim in the issues.

## 4. Execution

```
$ venv/bin/python -m pytest -q -p no:cacheprovider
50 passed, 15 xfailed in ~46s
$ node tests/e2e/ui_verdicts.mjs        # backend on :5000
E2E-01 PASS  E2E-02 PASS  E2E-03 FAIL  E2E-04 FAIL  E2E-05 FAIL
```

There were no pre-existing tests in the repository. A mutation check (forcing `verificacao_sucesso = True` in `app.py`) made 10 verdict tests fail, so the passing tests do detect a verdict regression. Every xfail was also run with `--runxfail` to confirm it fails on the documented assertion rather than an incidental error.

## 5. Defects

| ID | Severity | Summary | Issue |
|---|---|---|---|
| D1 | Critical | default `--unwind N --no-unwinding-assertions` → false SUCCESSFUL | [#11](https://github.com/esbmc/esbmc-web/issues/11) (new) |
| D2 | Critical | cancelled run reported as SUCCESSFUL (backend) | [#12](https://github.com/esbmc/esbmc-web/issues/12) (new) |
| D3 | Critical | UI shows SUCCESSFUL for parse error / timeout / cancel | [#13](https://github.com/esbmc/esbmc-web/issues/13) (new) |
| D4 | Critical | Python homogenizer replaces function bodies, restricts inputs | [#14](https://github.com/esbmc/esbmc-web/issues/14) (new) |
| D5 | Critical | unparseable repo modules replaced by template, reported SAFE | [#15](https://github.com/esbmc/esbmc-web/issues/15) (new) |
| D6 | Critical | repo `// esbmc-flags:` can disable checks | [#16](https://github.com/esbmc/esbmc-web/issues/16) (new) |
| D7 | Critical | C++ sanitizer strips `virtual` (and other semantic rewrites) | [#17](https://github.com/esbmc/esbmc-web/issues/17) (new) |
| D8 | High | C++ and `<stdint.h>` C fail to parse on macOS | [#18](https://github.com/esbmc/esbmc-web/issues/18) (new) |
| D9 | Medium | `#include`-driven file creation outside temp dir | [#19](https://github.com/esbmc/esbmc-web/issues/19) (new) |
| D10 | Low | anti-vacuity `--function` target scoring window | [#20](https://github.com/esbmc/esbmc-web/issues/20) (new) |

## 6. Coverage gaps and residual risk

- **Not executed:** Windows/WSL launchers, `runner.sh`, Linux. D8 is confirmed on macOS only.
- **Network git ingestion** (real GitHub clone, `blob:none` partial clone) was not exercised. Tests use local repositories, so GitHub-specific URL handling is covered only by unit tests.
- **Python repository slicing** (`fundir_dependencias_internas_python`) and **C++ cross-directory linking** (`resolver_fontes_dependentes_cpp`) are untested end-to-end. Code reading shows silent caps: at most 6 fused Python symbols and at most 3 C/C++ translation units. Dropped dependencies become bodyless functions, which can change verification semantics. This is high residual risk.
- **Phase 1/2, k-induction, concurrency inference** (`--context-bound`/`--data-races-check` auto-added) and **professional test-suite oracles** were exercised only through unit tests.
- **Security, not exploited, open for review:**
  - the backend has wildcard CORS on a localhost service that runs subprocesses
  - Flask `debug=True`
  - `python_interpreter` and `--witness-output` values are passed through from the request
  - symlinks in cloned repositories are followed by the in-place header rewriter
  - `innerHTML` rendering of ESBMC messages derived from analysed source
  - `TAREFAS_ATIVAS`/`CLONE_TASKS` are never evicted (unbounded memory)
  - there is no file-size or count limit on cloned repositories
- `/health` hard-codes `"solver": "Z3 v4.8.12 + Bitwuzla"` regardless of what is installed.

## 7. Conclusion

**Not ready for release.** The tool reports `VERIFICATION SUCCESSFUL` for programs that ESBMC itself proves buggy in its default (assisted) mode: bugs beyond the silent unwind bound, homogenized Python, unparseable repository modules, and repository-disabled assertions. It also reports success for cancelled runs, and in the UI for parse errors and timeouts. Raw ESBMC mode with native C or Python gives correct verdicts. At minimum, D1 through D6 must be fixed before any result can be trusted, and D8 makes C++ unusable on macOS.
