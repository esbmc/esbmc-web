import re
import subprocess

import pytest

from conftest import requires_esbmc
from sanitizers.caminhos import contido_em, remover_links_externos
from sanitizers.c_sanitizer import sanitizar_c
from sanitizers import cpp_sanitizer
from sanitizers.cpp_sanitizer import sanitizar_cpp
from sanitizers.harness_args import GrafoDeChamadas, declarar_argumento, escolher_raizes
from sanitizers.python_sanitizer import gerar_harness_python, precisa_homogeneizar_v2, sanitizar_python


class TestPythonHomogenizerDecision:
    def test_self_contained_script_runs_natively(self):
        assert precisa_homogeneizar_v2('x = 1\nassert x == 1\n')[0] is False

    def test_harness_with_entry_code_is_kept_as_is(self):
        assert precisa_homogeneizar_v2('import torch\nassert 1 == 1\n', is_harness=True)[0] is False
        assert precisa_homogeneizar_v2('def t(x: int):\n    assert x\n\nt(1)\n', is_harness=True)[0] is False

    def test_harness_that_only_defines_functions_gets_calls(self):
        assert precisa_homogeneizar_v2('def t(x: int):\n    assert x != 3\n', is_harness=True)[0] is True

    def test_external_import_triggers_homogenizer(self):
        assert precisa_homogeneizar_v2('import requests\n')[0] is True

    def test_local_stub_suppresses_homogenizer(self, tmp_path):
        (tmp_path / 'requests.py').write_text('')
        assert precisa_homogeneizar_v2('import requests\n', temp_dir=str(tmp_path))[0] is False

    def test_native_path_preserves_code(self, tmp_path):
        src, out = tmp_path / 'm.py', tmp_path / 'o.py'
        src.write_text('def f(x: int) -> int:\n    return 10 // x\n\nf(0)\n')
        info = sanitizar_python(str(src), str(out), temp_dir=str(tmp_path))
        assert info['usou_homogenizer_v2'] is False
        assert '10 // x' in out.read_text()

    def test_homogenized_output_preserves_function_body(self, tmp_path):
        src, out = tmp_path / 'm.py', tmp_path / 'o.py'
        src.write_text('import os\n\ndef f(x: int) -> int:\n    return 10 // x\n')
        sanitizar_python(str(src), str(out), temp_dir=str(tmp_path))
        assert '10 // x' in out.read_text()

class TestPythonHarness:
    def test_calls_each_function_with_nondet_arguments(self):
        code = 'def f(n: int, s: str, b: bool, x: float) -> int:\n    return n\n\ndef g(a):\n    return a\n'
        out, called, skipped = gerar_harness_python(code)
        assert out.startswith(code)
        assert called == ['f', 'g'] and not skipped
        assert 'f(_esbmc_f_n, _esbmc_f_s, _esbmc_f_b, _esbmc_f_x)' in out
        for decl in ('_esbmc_f_n: int = nondet_int()', '_esbmc_f_s: str = nondet_str()',
                     '_esbmc_f_b: bool = nondet_bool()', '_esbmc_f_x: float = nondet_float()',
                     '_esbmc_g_a: int = nondet_int()'):
            assert decl in out

    def test_skips_functions_it_cannot_call_and_adds_no_constraints(self):
        code = ('def a(x: list) -> None:\n    pass\n\ndef b(*args):\n    pass\n\n'
                'def c(*, k):\n    pass\n\ndef __d(x):\n    pass\n\nclass K:\n    def m(self, x: int):\n        pass\n')
        out, called, skipped = gerar_harness_python(code)
        assert (out, called, skipped) == (code, [], ['a', 'b', 'c', 'K.m'])
        assert '__ESBMC_assume' not in gerar_harness_python('def f(n: int):\n    pass\n')[0]
        assert gerar_harness_python('async def f(n: int):\n    pass\n')[2] == ['f']


class TestCSanitizer:
    def test_generates_harness_for_module_without_main(self, tmp_path):
        f = tmp_path / 'codigo.c'
        f.write_text('int add(int a, int b){ return a + b; }\n')
        sanitizar_c(str(f), str(tmp_path))
        text = f.read_text()
        assert 'int main(void)' in text
        assert 'add(' in text.split('int main(void)')[1]

    def test_harness_declares_arguments_with_their_own_unconstrained_types(self):
        decls = [line.strip() for decl in ('const unsigned long x', 'double d', 'struct s v', 'S s', 'int &r', 'int',
                                           'int n = 3')
                 for line in declarar_argumento(decl, 'v')]
        assert decls == ['unsigned long v;', 'double v;', 'struct s v;', 'S v;', 'int v;', 'int v;', 'int v;']

    @pytest.mark.parametrize('decl, lines', [
        ('const char *p', ['char v_buf[16];', 'v_buf[15] = 0;', 'char *v = nondet_harness_null() ? 0 : v_buf;']),
        ('unsigned char *u', ['unsigned char v_buf[16];', 'unsigned char *v = nondet_harness_null() ? 0 : v_buf;']),
        ('int a[]', ['int v_buf[16];', 'int *v = nondet_harness_null() ? 0 : v_buf;']),
        ('void *q', ['unsigned char v_buf[16];', 'unsigned char *v = nondet_harness_null() ? 0 : v_buf;']),
        ('int a[static 4]', ['int v_buf[16];', 'int *v = v_buf;']),
    ])
    def test_harness_pointer_is_null_or_a_buffer(self, decl, lines):
        assert [line.strip() for line in declarar_argumento(decl, 'v')] == lines

    def test_harness_calls_roots_and_drops_calls_that_do_not_compile(self, tmp_path):
        f = tmp_path / 'codigo.c'
        f.write_text(''.join(f'int f{i}(int x){{ return x; }}\n' for i in range(7))
                     + 'int top(int x){ return f0(x) + f1(x); }\n'
                     + '#if 0\nint legacy(int x){ return x; }\n#endif\n')
        _, harness = sanitizar_c(str(f), str(tmp_path))
        calls = f.read_text().split('int main(void)')[1]
        assert harness == {'raizes': ['f2', 'f3', 'f4', 'f5', 'f6', 'top'], 'nao_exercitadas': ['legacy']}
        assert 'top(' in calls and 'f0(' not in calls and 'legacy(' not in calls

    @pytest.mark.parametrize('code, roots, skipped', [
        ('static int h(int x){ return x; }\nint api(int x){ return h(x); }\n', ['api'], []),
        ('static int dead(int x){ return x; }\nint api(int x){ return x; }\n', ['api'], ['dead']),
        ('int g(int x){ return g(x - 1); }\n', ['g'], []),
        ('int b(int);\nint a(int x){ return b(x); }\nint b(int x){ return a(x); }\n', ['a'], []),
        ('static void cb(int x){ }\nvoid (*t)(int) = cb;\nvoid run(void){ cb(1); }\n', ['cb', 'run'], []),
        ('int h(int x){ return x; }\nint api(void){ const char *s = "h(1)"; return 0; }\n', ['h', 'api'], []),
        ('void dbg(int i){ }\nvoid api(int x){\n#if 0\n  dbg(0);\n#endif\n}\n', ['dbg', 'api'], []),
        ('void helper(int i){ }\nvoid api(int x){ void helper(int); }\n', ['helper', 'api'], []),
        ('int check(int x){ return x; }\nvoid helper(int i){ }\nstatic void dead(int x){ if (check(x)) { helper(0); } }\n',
         ['check', 'helper'], ['dead']),
        ('static int h(int x){ return x; }\nint api(void){ auto l = [](){ return h(1); }; return 0; }\n',
         ['h', 'api'], []),
        ('void helper(int i){ }\nlong api(int x){ return sizeof(helper(0), 1); }\n', ['helper', 'api'], []),
        ('void helper(int i){ }\nvoid api(int x){ (void)noexcept(helper(0)); }\n', ['helper', 'api'], []),
        ('int helper(int i){ return i; }\nvoid api(int x){ decltype(helper(0)) y = 0; }\n', ['helper', 'api'], []),
        ('int helper(void){ return 0; }\nvoid api(int x, int y = helper()){ }\n', ['helper', 'api'], []),
        ('namespace ext { void helper(int); }\nvoid helper(int i){ }\nvoid api(int x){ ext::helper(x); }\n',
         ['helper', 'api'], []),
        ('void helper(int i){ }\nvoid api(int x){ struct L { static void m(){ helper(0); } }; }\n',
         ['helper', 'api'], []),
        ('void helper(int i){ }\nvoid api(int x){ if constexpr (false) helper(0); }\n', ['helper', 'api'], []),
        ('void helper(int i){ }\nint api(int x){ return __builtin_choose_expr(0, (helper(0), 1), 2); }\n',
         ['helper', 'api'], []),
        ('int helper(int i){ return i; }\nint api(int x){ return __builtin_constant_p(helper(0)); }\n',
         ['helper', 'api'], []),
    ], ids=['helper', 'dead-static', 'recursion', 'entry-less-cycle', 'address-taken', 'call-in-string',
            'disabled-call', 'block-prototype', 'call-before-brace', 'call-in-lambda', 'sizeof',
            'noexcept', 'decltype', 'default-argument', 'other-namespace', 'local-class', 'if-constexpr', 'choose-expr', 'constant-p'])
    def test_harness_chooses_roots_from_the_call_graph(self, tmp_path, code, roots, skipped):
        nomes = re.findall(r'^(?:static )?\w+ \*?(\w+)\(\w+[^;{]*\{', code, re.MULTILINE)
        f = tmp_path / 'm.cpp'
        f.write_text(code)
        grafo = GrafoDeChamadas.ler(str(f), code, ['-x', 'c++', '-std=c++17'], nomes)
        assert escolher_raizes(nomes, grafo) == (roots, skipped)

    def test_member_definitions_and_calls_are_not_free_function_calls(self, tmp_path):
        code = ('void helper(int i){ }\nvoid run(int);\nstruct A { void run(); void helper(int); };\n'
                'void A::run(){ helper(0); }\nvoid run(int x){ }\nvoid api(A *p){ p-> helper(0); }\n')
        f = tmp_path / 'm.cpp'
        f.write_text(code)
        nomes = ['helper', 'run', 'api']
        assert escolher_raizes(nomes, GrafoDeChamadas.ler(str(f), code, ['-x', 'c++'], nomes)) == (nomes, [])

    def test_harness_falls_back_to_calling_every_function_without_an_ast(self, tmp_path):
        grafo = GrafoDeChamadas.ler(str(tmp_path / 'missing.c'), 'int a(void);', ['-x', 'c'], ['a', 'b'])
        assert escolher_raizes(['a', 'b'], grafo) == (['a', 'b'], [])

    def test_keeps_existing_main(self, tmp_path):
        f = tmp_path / 'codigo.c'
        original = 'int main(void){ return 0; }\n'
        f.write_text(original)
        assert sanitizar_c(str(f), str(tmp_path)) == ([], None)
        assert f.read_text() == original

    def test_mocks_missing_local_header(self, tmp_path):
        f = tmp_path / 'codigo.c'
        f.write_text('#include "missing.h"\nint main(void){ return 0; }\n')
        created, _ = sanitizar_c(str(f), str(tmp_path))
        assert (tmp_path / 'missing.h').is_file()
        assert str(tmp_path / 'missing.h') in created

class TestCppSanitizer:
    def test_harness_instantiates_template_parameters(self, tmp_path):
        f = tmp_path / 'codigo.cpp'
        f.write_text('template<typename U> U twice(U x){ return x + x; }\n'
                     'template<class K>\nint first(K *p){ return 0; }\n')
        _, harness = sanitizar_cpp(str(f), str(tmp_path))
        calls = f.read_text().split('int __esbmc_main()')[1]
        assert harness['nao_exercitadas'] == []
        assert 'int _sym_arg_0_0;' in calls and 'int _sym_arg_1_0_buf[16];' in calls


    @pytest.mark.parametrize('expression', [
        '(std::ostringstream{} << a[i]).str()',
        'std::unreachable()',
        'std::chrono::system_clock::now()',
        'std::hash<int>{}(i)',
        'typeid(i).name()',
    ])
    def test_rewrite_keeps_user_expressions(self, tmp_path, expression):
        f = tmp_path / 'codigo.cpp'
        f.write_text(f'int main(){{ int a[2]; int i = 5; auto r = {expression}; return 0; }}\n')
        sanitizar_cpp(str(f), str(tmp_path))
        assert expression in f.read_text()

    @pytest.mark.parametrize('source, kept', [
        ('#include <string>\nchar f(const std::string &s, int i){ return s[i]; }\nint main(){ return f("ab", 10); }\n', 's[i]'),
        ('#include <string>\nint main(){ const std::string s = "ab"; return s[5]; }\n', 's[5]'),
        ('#define CFG "cfg.h"\n#include CFG\nint main(){ return 0; }\n', '#include CFG'),
    ])
    def test_rewrite_keeps_bounds_checked_indexing_and_macro_includes(self, tmp_path, source, kept):
        f = tmp_path / 'codigo.cpp'
        f.write_text(source)
        sanitizar_cpp(str(f), str(tmp_path))
        assert kept in f.read_text()

    @requires_esbmc
    def test_rewrite_preserves_virtual_dispatch_verdict(self, tmp_path):
        code = ('#include <cassert>\nstruct B{ virtual int f(){return 1;} };\n'
                'struct D : B { int f(){return 0;} };\n'
                'int main(){ D d; B *p=&d; assert(p->f()==1); return 0; }\n')
        f = tmp_path / 'codigo.cpp'
        f.write_text(code)
        sanitizar_cpp(str(f), str(tmp_path))
        proc = subprocess.run(['esbmc', str(f)], capture_output=True, text=True, timeout=120, check=False)
        out = proc.stdout + proc.stderr
        assert 'VERIFICATION FAILED' in out


@pytest.mark.parametrize('sanitize, name', [(sanitizar_c, 'codigo.c'), (sanitizar_cpp, 'codigo.cpp')])
@pytest.mark.parametrize('include', ['../outside/escaped.h', '{outside}/abs/escaped.h', 'link/escaped.h'])
def test_mock_headers_stay_inside_work_dir(tmp_path, sanitize, name, include):
    work, outside = tmp_path / 'work', tmp_path / 'outside'
    work.mkdir()
    outside.mkdir()
    (work / 'link').symlink_to(outside, target_is_directory=True)
    f = work / name
    f.write_text(f'#include "{include.format(outside=outside)}"\nint main(void){{ return 0; }}\n')
    sanitize(str(f), str(work))
    assert not any(p.is_file() for p in outside.rglob('*'))


@pytest.mark.parametrize('sanitize, name', [(sanitizar_c, 'codigo.c'), (sanitizar_cpp, 'codigo.cpp')])
def test_nested_mock_header_inside_work_dir_is_still_created(tmp_path, sanitize, name):
    f = tmp_path / name
    f.write_text('#include "sub/dir/missing.h"\nint main(void){ return 0; }\n')
    sanitize(str(f), str(tmp_path))
    assert (tmp_path / 'sub' / 'dir' / 'missing.h').is_file()


def test_only_symlinks_leaving_the_root_are_removed(tmp_path):
    root, outside = tmp_path / 'repo', tmp_path / 'outside'
    (root / 'include').mkdir(parents=True)
    outside.mkdir()
    (root / 'include' / 'a.h').write_text('int a;')
    (root / 'inner.h').symlink_to(root / 'include' / 'a.h')
    (root / 'inc').symlink_to(root / 'include', target_is_directory=True)
    (root / 'include' / 'out.h').symlink_to(outside / 'x.h')
    (root / 'outdir').symlink_to(outside, target_is_directory=True)
    (root / 'chain').symlink_to(root / 'outdir', target_is_directory=True)
    assert remover_links_externos(str(root)) == ['chain', 'include/out.h', 'outdir']
    assert (root / 'inner.h').is_symlink() and (root / 'inc').is_symlink()
    assert contido_em(str(root), str(root / 'inc' / 'a.h'))
    assert not contido_em(str(root), str(root / '..' / 'outside'))


def test_failed_header_probe_keeps_shim_and_is_not_cached(tmp_path, monkeypatch):
    (tmp_path / 'vector').write_text('// shim')
    monkeypatch.setattr(cpp_sanitizer, '_CABECALHOS_STD_NATIVOS', {})
    monkeypatch.setattr(cpp_sanitizer, '_esbmc_analisa_cabecalho', lambda name: None)
    cpp_sanitizer._remover_shims_std_nativos(str(tmp_path))
    assert (tmp_path / 'vector').exists()
    assert all(not per_version for per_version in cpp_sanitizer._CABECALHOS_STD_NATIVOS.values())

    monkeypatch.setattr(cpp_sanitizer, '_esbmc_analisa_cabecalho', lambda name: True)
    cpp_sanitizer._remover_shims_std_nativos(str(tmp_path))
    assert not (tmp_path / 'vector').exists()


def test_cpp_sanitizer_does_not_rewrite_headers_outside_work_dir(tmp_path):
    work, outside = tmp_path / 'work', tmp_path / 'outside'
    work.mkdir()
    outside.mkdir()
    header = outside / 'lib.hpp'
    header.write_text('consteval int f(){ return 1; }\n')
    f = work / 'codigo.cpp'
    f.write_text('int main(){ return 0; }\n')
    sanitizar_cpp(str(f), str(work), sub_dir_repo=str(outside))
    assert header.read_text() == 'consteval int f(){ return 1; }\n'
