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
from sanitizers import repo_explorer
from sanitizers.repo_explorer import FusaoPythonIncompleta, fundir_dependencias_internas_python


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


class TestPythonRepoSlicing:
    HELPERS = (
        'import re\n\n'
        'LIMITE = len(re.findall("x", "xx"))\n\n'
        'def _ajuda(n):\n    return n + LIMITE\n\n'
        'def montar(n):\n    return _ajuda(n)\n'
    )

    @staticmethod
    def repo(tmp_path, files):
        for rel, text in files.items():
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text(text)
        return str(tmp_path)

    def fuse(self, tmp_path, files, target):
        return fundir_dependencias_internas_python(files[target], self.repo(tmp_path, files), target)

    def test_copies_callees_module_names_and_imports(self, tmp_path):
        files = {
            'backend/pkg/helpers.py': self.HELPERS,
            'backend/pkg/alvo.py': 'from pkg.helpers import montar\n\nassert montar(1) == 3\n',
        }
        code, symbols = self.fuse(tmp_path, files, 'backend/pkg/alvo.py')
        assert 'pkg.helpers' not in code
        assert [s.split()[0] for s in symbols] == ['LIMITE', '_ajuda()', 'montar()']
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    def test_relative_import_and_re_export(self, tmp_path):
        files = {
            'pkg/__init__.py': 'from .helpers import montar\n',
            'pkg/helpers.py': self.HELPERS,
            'pkg/alvo.py': 'from . import montar\n\nassert montar(1) == 3\n',
        }
        code, _ = self.fuse(tmp_path, files, 'pkg/alvo.py')
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    def test_external_module_is_left_alone(self, tmp_path):
        files = {'lib/json.py': 'def loads(s):\n    return s\n',
                 'app/alvo.py': 'from json import loads\n\nloads("1")\n'}
        assert self.fuse(tmp_path, files, 'app/alvo.py') == (files['app/alvo.py'], [])

    @pytest.mark.parametrize('target, reason', [
        ('from pkg.helpers import nada\nnada()\n', "cannot find 'nada'"),
        ('from pkg.helpers import montar\n\ndef _ajuda():\n    pass\nmontar(1)\n', "'_ajuda' from"),
        ('from pkg.helpers import montar as m\nm(1)\n', 'under another name'),
    ])
    def test_incomplete_slice_raises(self, tmp_path, target, reason):
        files = {'pkg/helpers.py': self.HELPERS, 'pkg/alvo.py': target}
        with pytest.raises(FusaoPythonIncompleta, match=reason):
            self.fuse(tmp_path, files, 'pkg/alvo.py')

    def test_cap_raises_instead_of_truncating(self, tmp_path, monkeypatch):
        monkeypatch.setattr(repo_explorer, 'MAX_DEFINICOES_FUNDIDAS', 2)
        files = {'pkg/helpers.py': self.HELPERS, 'pkg/alvo.py': 'from pkg.helpers import montar\nmontar(1)\n'}
        with pytest.raises(FusaoPythonIncompleta, match='more than 2'):
            self.fuse(tmp_path, files, 'pkg/alvo.py')

    @pytest.mark.parametrize('helper, target', [
        ('T = {}\nT["a"] = 1\ndef f():\n    return T["a"]\n', 'assert f() == 1'),
        ('X = 1\nX = X + 1\ndef f():\n    return X\n', 'assert f() == 2'),
        ('class A:\n    def m(self):\n        return B()\nclass B(A):\n    pass\nf = A\n', 'assert isinstance(f().m(), f)'),
        ('N = 0\ndef f():\n    global N\n    N += 1\n    return N\n', 'assert f() == 1'),
        ('try:\n    import json\nexcept ImportError:\n    json = None\ndef f():\n    return json.dumps(1)\n', 'assert f() == "1"'),
        ('if True:\n    SEP = "/"\nelse:\n    SEP = "-"\ndef f():\n    return SEP\n', 'assert f() == "/"'),
        ('T = [1, 2]\nD = [t * 2 for t in T]\ndef f():\n    return D\n', 'assert f() == [2, 4]'),
        ('data = 5\ndef f(data):\n    return data\n', 'data = 1\nassert f(2) == 2'),
        ('import os.path\ndef f():\n    return os.path.join("a", "b")\n', 'import os\nassert f() == os.path.join("a", "b")'),
        ('R = {}\ndef reg(fn):\n    R[fn.__name__] = fn\n    return fn\n@reg\ndef a():\n    return 1\ndef f():\n    return R["a"]()\n',
         'assert f() == 1'),
        ('T = {}\nfor k in "ab":\n    T[k] = 1\ndef f():\n    return T["b"]\n', 'assert f() == 1'),
        ('R = {}\ndef _fill():\n    R["a"] = 1\n_fill()\ndef f():\n    return R["a"]\n', 'assert f() == 1'),
        ('R = {}\n_x = R.setdefault("a", 1)\ndef f():\n    return R["a"]\n', 'assert f() == 1'),
        ('X = 1\nif __name__ == "__main__":\n    X = 3\ndef f():\n    return X\n', 'assert f() == 1'),
        ('def f():\n    return 1\n', 'if __name__ == "__main__":\n    assert f() == 1'),
    ])
    def test_slice_runs_like_the_original(self, tmp_path, helper, target):
        files = {'pkg/h.py': helper, 'pkg/alvo.py': f'from pkg.h import f\n{target}\n'}
        code, _ = self.fuse(tmp_path, files, 'pkg/alvo.py')
        assert 'pkg.h' not in code
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    def test_dot_slash_target_path(self, tmp_path):
        files = {'pkg/h.py': self.HELPERS, 'pkg/alvo.py': 'from .h import montar\nassert montar(1) == 3\n'}
        code, _ = fundir_dependencias_internas_python(files['pkg/alvo.py'], self.repo(tmp_path, files), './pkg/alvo.py')
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    @pytest.mark.parametrize('extra, target, reason', [
        ({'pkg/h2.py': 'B = 5\ndef g():\n    return B\n', 'pkg/h.py': 'A, B = 1, 2\ndef f():\n    return A\n'},
         'from pkg.h2 import g\nfrom pkg.h import f\ng()\nf()\n', "'B' from"),
        ({'pkg/h.py': 'K = 10\ndef f():\n    return K\n'}, 'from pkg.h import f\nfor K in range(1):\n    pass\nf()\n', "'K' from"),
        ({'pkg/a.py': 'from pkg.b import x\n', 'pkg/b.py': 'from pkg.a import x\n'}, 'from pkg.a import x\nx()\n', 'circular'),
        ({'pkg/a.py': 'from pkg.a import x\n'}, 'from pkg.a import x\nx()\n', 'circular'),
        ({'pkg/h.py': 'def f():\n    return nada\n'}, 'from pkg.h import f\nf()\n', "cannot find 'nada'"),
        ({'pkg/h.py': 'def f():\n    pass\n'}, 'import pkg.h\nfrom pkg.h import f\nf()\n', 'as a whole'),
        ({'pkg/h.py': 'def f():\n    pass\n'}, 'from pkg.h import f\ndef g():\n    from pkg.h import f\nf()\n', 'inside a block'),
        ({'pkg/h.py': 'def f():\n    pass\n'}, 'from pkg.h import f\nif __name__ == "__main__":\n    from pkg.h import f\n', 'inside a block'),
        ({'pkg/h.py': 'from __future__ import barry_as_FLUFL\ndef f():\n    pass\n'}, 'from pkg.h import f\nf()\n', 'barry_as_FLUFL'),
        ({'pkg/h.py': 'def f():\n    return __file__\n'}, 'from pkg.h import f\nf()\n', "cannot find '__file__'"),
        ({'pkg/h.py': 'X = 1\nif __name__ != "__main__":\n    X = 2\ndef f():\n    return X\n'}, 'from pkg.h import f\nf()\n', "cannot find '__name__'"),
    ])
    def test_unsound_slice_raises(self, tmp_path, extra, target, reason):
        files = {**extra, 'pkg/alvo.py': target}
        with pytest.raises(FusaoPythonIncompleta, match=reason):
            self.fuse(tmp_path, files, 'pkg/alvo.py')

    def test_copies_go_where_the_import_was(self, tmp_path):
        files = {'pkg/h.py': 'import os\nMODO = os.environ.get("MODO_X", "lento")\n',
                 'pkg/alvo.py': 'import os\nos.environ["MODO_X"] = "rapido"\nfrom pkg.h import MODO\nassert MODO == "rapido"\n'}
        code, _ = self.fuse(tmp_path, files, 'pkg/alvo.py')
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    def test_unread_import_of_unreadable_module_is_dropped(self, tmp_path):
        files = {'pkg/bad.py': 'def (:\n', 'pkg/h.py': self.HELPERS,
                 'pkg/alvo.py': 'from pkg.bad import z\nfrom pkg.h import montar\nassert montar(1) == 3\n'}
        code, _ = self.fuse(tmp_path, files, 'pkg/alvo.py')
        exec(compile(code, 'alvo.py', 'exec'), {'__name__': '__main__'})

    def test_unreadable_module_does_not_abort_indexing(self, tmp_path):
        files = {'pkg/h.py': self.HELPERS, 'pkg/alvo.py': 'from pkg.ruim import f\nf()\n'}
        repo = self.repo(tmp_path, files)
        (tmp_path / 'pkg' / 'ruim.py').symlink_to(tmp_path / 'missing.py')
        assert repo_explorer.construir_indice_python_repositorio(repo)['modulos']['pkg.ruim'] is None
        with pytest.raises(FusaoPythonIncompleta, match='cannot analyse'):
            fundir_dependencias_internas_python(files['pkg/alvo.py'], repo, 'pkg/alvo.py')

    @requires_esbmc
    def test_esbmc_sees_the_copied_callees(self, tmp_path):
        files = {
            'pkg/helpers.py': 'def _ajuda(n: int) -> int:\n    return n + 1\n\ndef montar(n: int) -> int:\n    return _ajuda(n)\n',
            'pkg/alvo.py': 'from pkg.helpers import montar\n\nassert montar(1) == 2\n',
        }
        code, _ = self.fuse(tmp_path, files, 'pkg/alvo.py')
        out = tmp_path / 'out' / 'codigo.py'
        out.parent.mkdir()
        out.write_text(code)
        proc = subprocess.run(['esbmc', str(out)], capture_output=True, text=True, timeout=120, check=False)
        assert 'VERIFICATION SUCCESSFUL' in proc.stdout + proc.stderr
