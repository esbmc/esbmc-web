import pytest

import app as backend_app
from app import (JANELA_CORPO_FUNCAO, _fim_do_bloco, avaliar_status_teste, classificar_veredito, descobrir_funcao_alvo_principal,
                 escapar_latex, filtrar_flags_do_repositorio, funcoes_sem_corpo, normalizar_url_e_subpasta_git)


class TestGitUrlNormalisation:
    def test_tree_url_extracts_subdir(self):
        url, sub, main = normalizar_url_e_subpasta_git('https://github.com/esbmc/esbmc/tree/master/src/util')
        assert (url, sub, main) == ('https://github.com/esbmc/esbmc', 'src/util', '')

    def test_blob_url_extracts_file_and_parent_dir(self):
        url, sub, main = normalizar_url_e_subpasta_git('https://github.com/esbmc/esbmc/blob/master/src/util/arith_tools.cpp')
        assert (url, sub, main) == ('https://github.com/esbmc/esbmc', 'src/util', 'src/util/arith_tools.cpp')

    def test_explicit_filters_take_precedence(self):
        _, sub, main = normalizar_url_e_subpasta_git(
            'https://github.com/esbmc/esbmc/blob/master/src/a.c', 'other', 'x/y.c')
        assert (sub, main) == ('other', 'x/y.c')

    def test_plain_url_strips_trailing_slash(self):
        assert normalizar_url_e_subpasta_git(' https://github.com/esbmc/esbmc/ ')[0] == 'https://github.com/esbmc/esbmc'

    def test_empty_url_is_passthrough(self):
        assert normalizar_url_e_subpasta_git('', 'a', 'b') == ('', 'a', 'b')


class TestVerdictClassification:
    def test_esbmc_verdict_lines_decide(self):
        assert classificar_veredito('...\nVERIFICATION FAILED\n', 1, False) == 'FAILED'
        assert classificar_veredito('...\nVERIFICATION SUCCESSFUL\n', 0, False) == 'SUCCESSFUL'

    def test_only_unwinding_assertions_violated_is_bound_reached(self):
        single = 'Violated property:\n  file x.c line 2 function main\n  unwinding assertion loop 0\n\nVERIFICATION FAILED\n'
        multi = ('Violated property:\n  unwinding assertion loop 3\n'
                 '  FAILED       [main.assertion.1]  line 2  unwinding assertion loop 3\nVERIFICATION FAILED\n')
        mixed = multi.replace('VERIFICATION FAILED', '  FAILED       [main.assertion.2]  line 2  assertion s==3\nVERIFICATION FAILED')
        assert classificar_veredito(single, 1, False) == 'BOUND_REACHED'
        assert classificar_veredito(multi, 1, False) == 'BOUND_REACHED'
        assert classificar_veredito(mixed, 1, False) == 'FAILED'
        real = 'Violated property:\n  file x.c line 2 function main\n  assertion x==6\n  !(x == 6)\n\nVERIFICATION FAILED\n'
        assert classificar_veredito(real, 1, False) == 'FAILED'
        user_text = ('Violated property:\n  file x.c line 2 function main\n'
                     '  assertion x==2 && "unwinding assertion"\n  !(x == 2)\n\nVERIFICATION FAILED\n')
        assert classificar_veredito(user_text, 1, False) == 'FAILED'

    def test_unsupported_call_is_no_verdict_unless_a_real_property_fails(self):
        unsupported = ('Violated property:\n  file p.py line 4 column 11\n'
                       "  Unsupported function 'join' is reached\n  0\n\nVERIFICATION FAILED\n")
        assert classificar_veredito(unsupported, 1, False) == 'UNSUPPORTED'
        mixed = unsupported.replace('VERIFICATION FAILED', '  FAILED       [f.assertion.2]  line 3  assertion n != 3\nVERIFICATION FAILED')
        assert classificar_veredito(mixed, 1, False) == 'FAILED'

    def test_success_with_bodyless_user_function_is_partial(self):
        text = 'WARNING: no body for function helper\nVERIFICATION SUCCESSFUL\n'
        assert classificar_veredito(text, 0, False) == 'PARTIAL'
        assert funcoes_sem_corpo(text) == ['helper']
        stubs = ('WARNING: no body for function nondet_int\nWARNING: no body for function __VERIFIER_nondet_int\n'
                 'WARNING: no body for function allocator#\nVERIFICATION SUCCESSFUL\n')
        assert classificar_veredito(stubs, 0, False) == 'SUCCESSFUL'
        failed = 'WARNING: no body for function helper\nViolated property:\n  assertion x\n\nVERIFICATION FAILED\n'
        assert classificar_veredito(failed, 1, False) == 'FAILED'

    def test_completed_verdict_survives_late_cancel(self):
        assert classificar_veredito('VERIFICATION SUCCESSFUL\n', 0, True) == 'SUCCESSFUL'

    def test_no_verdict_line_is_never_successful(self):
        assert classificar_veredito('Parsing\n', 0, False) == 'UNKNOWN'
        assert classificar_veredito('Unwinding loop 3\n', -9, True) == 'CANCELLED'
        assert classificar_veredito('ERROR: Timed out\n', 1, False) == 'TIMEOUT'
        assert classificar_veredito('ERROR: PARSING ERROR\n', 1, False) == 'ERROR'
        assert classificar_veredito('', 6, False) == 'ERROR'


class TestOracleComparison:
    def test_without_oracle_classifies_verdict(self):
        assert avaliar_status_teste('VIOLATION [NATIVE BUG] (k=1)', None)[0] == 'VIOLATION'
        assert avaliar_status_teste('VERIFICATION FAILED', None)[0] == 'VIOLATION'
        assert avaliar_status_teste('BOUNDED SAFE (k=1)', '-')[0] == 'SAFE'
        assert avaliar_status_teste('ERROR (NO VERDICT)', None)[0] == 'COMPLETED'

    def test_matching_oracles(self):
        assert avaliar_status_teste('VIOLATION [NATIVE BUG] (k=1)', 'VERIFICATION FAILED')[0] == 'PASS_BUG_FOUND'
        assert avaliar_status_teste('BOUNDED SAFE (k=1)', 'VERIFICATION SUCCESSFUL')[0] == 'PASS_SOUND'

    def test_sv_comp_style_oracle_words(self):
        assert avaliar_status_teste('BOUNDED SAFE (k=3)', 'UNSAFE')[0] == 'REGRESSION_FAILED'
        assert avaliar_status_teste('VIOLATION [NATIVE BUG] (k=1)', 'UNSAFE')[0] == 'PASS_BUG_FOUND'
        assert avaliar_status_teste('VIOLATION [NATIVE BUG] (k=1)', 'FALSE')[0] == 'PASS_BUG_FOUND'
        assert avaliar_status_teste('BOUNDED SAFE (k=3)', 'TRUE')[0] == 'PASS_SOUND'
        assert avaliar_status_teste('BOUNDED SAFE (k=3)', 'SAFE')[0] == 'PASS_SOUND'

    def test_divergent_oracle_is_regression(self):
        assert avaliar_status_teste('BOUNDED SAFE (k=1)', 'VERIFICATION FAILED')[0] == 'REGRESSION_FAILED'
        assert avaliar_status_teste('VIOLATION [CONTRACT] (k=1)', 'VERIFICATION SUCCESSFUL')[0] == 'REGRESSION_FAILED'

    def test_run_without_verdict_never_passes_an_oracle(self):
        for obtained in ('TIMEOUT (NO VERDICT)', 'ERROR (NO VERDICT)', 'BOUND_REACHED (NO VERDICT)',
                         'STOPPED (NO VERDICT)', 'RAW ERROR (Unresolved Deps)'):
            for oracle in ('VERIFICATION SUCCESSFUL', 'VERIFICATION FAILED', 'VERIFICATION TIMEOUT', 'UNKNOWN'):
                assert avaliar_status_teste(obtained, oracle)[0] == 'INCONCLUSIVE', (obtained, oracle)


class TestTargetFunctionDiscovery:
    def test_c_prefers_function_with_asserts_and_branches(self):
        code = 'int a(int x){return x;}\nint b(int x){ if(x) assert(x>0); return x; }\n'
        assert descobrir_funcao_alvo_principal(code, 'c') == ('b', 1)

    @pytest.mark.parametrize('body', [
        ' { int y = x; } return x; ',
        ' /* } */ return x; ',
        ' // }\n return x; ',
        ' const char *s = "}\\"}"; return x; ',
        " char c = '}'; char d = '\\''; return x; ",
        " int n = 1'000; return x; ",
        ' const char *r = R"x(a")}")x"; return x; ',
        '\n#define LBRACE {\n return x; ',
        "\n#error don't\n return x; ",
        ' // continued \\\n } still a comment\n return x; ',
    ])
    def test_block_end_skips_nested_blocks_comments_and_literals(self, body):
        code = 'int f(int x){' + body + '}\nint g(void){ return 0; }\n'
        start = code.index('{') + 1
        assert _fim_do_bloco(code, start) == code.index('}\nint g')

    def test_block_end_never_scans_past_the_window(self):
        code = 'int f(int x){ if (x) {' + ' x++;' * 2000
        assert _fim_do_bloco(code, code.index('{') + 1) == code.index('{') + 1 + JANELA_CORPO_FUNCAO

    def test_unterminated_block_does_not_absorb_later_functions(self):
        code = ('int h(void){ int n = 1\'000;\n#ifdef A\n if (n) {\n#else\n if (!n) {\n#endif\n }\n'
                + 'int pad(void){ return 0; }\n' * 200
                + 'int g(int x){ if (x) assert(x > 0); if (x > 1) assert(x > 1); return x; }\n')
        assert descobrir_funcao_alvo_principal(code, 'c')[0] == 'g'

    def test_c_skips_main(self):
        assert descobrir_funcao_alvo_principal('int main(void){return 0;}\n', 'c') == (None, 0)

    def test_python_skips_methods_and_dunders(self):
        code = 'def __x():\n    pass\n\ndef f(a, b):\n    assert a\n'
        assert descobrir_funcao_alvo_principal(code, 'python') == ('f', 2)

    def test_python_syntax_error_returns_none(self):
        assert descobrir_funcao_alvo_principal('def (:', 'python') == (None, 0)


def test_repository_flags_may_only_add_checks():
    flags = ['--overflow-check', '--no-assertions', '--function', 'helper', '--unwind', '5', '--no-bounds-check']
    accepted, ignored = filtrar_flags_do_repositorio(flags)
    assert accepted == [['--overflow-check'], ['--unwind', '5']]
    assert ignored == ['--no-assertions', '--function', 'helper', '--no-bounds-check']


def test_repository_flag_value_cannot_smuggle_another_flag():
    accepted, ignored = filtrar_flags_do_repositorio(['--unwind', '3', '--unwind', '--no-assertions'])
    assert accepted == [['--unwind', '3']]
    assert ignored == ['--unwind', '--no-assertions']


def test_repository_value_flag_without_value_is_ignored():
    accepted, ignored = filtrar_flags_do_repositorio(['--unwind', '--k-induction', '--timeout'])
    assert accepted == [['--k-induction']]
    assert ignored == ['--unwind', '--timeout']


def test_flag_allowlist_excludes_solver_program_override():
    allowed = backend_app.FLAGS_PERMITIDAS_SIMPLES | backend_app.FLAGS_PERMITIDAS_COM_VALOR
    assert '--smtlib-solver-prog' not in allowed
    assert '--python' not in allowed


def test_latex_escaping_covers_every_special_character():
    assert escapar_latex('a&b%c$d#e_f{g}h~i^j\\k') == (
        'a\\&b\\%c\\$d\\#e\\_f\\{g\\}h\\textasciitilde{}i\\textasciicircum{}j\\textbackslash{}k')
    assert escapar_latex('plain.c') == 'plain.c'
