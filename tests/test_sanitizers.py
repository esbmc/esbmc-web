import subprocess

import pytest

from conftest import known_defect, requires_esbmc
from sanitizers.c_sanitizer import sanitizar_c
from sanitizers.cpp_sanitizer import sanitizar_cpp
from sanitizers.python_sanitizer import precisa_homogeneizar_v2, sanitizar_python


class TestPythonHomogenizerDecision:
    def test_self_contained_script_runs_natively(self):
        assert precisa_homogeneizar_v2('x = 1\nassert x == 1\n')[0] is False

    def test_harness_is_never_homogenized(self):
        assert precisa_homogeneizar_v2('import torch\n', is_harness=True)[0] is False

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

    @known_defect('D4 (#14): homogenizer drops the original function body')
    def test_homogenized_output_preserves_function_body(self, tmp_path):
        src, out = tmp_path / 'm.py', tmp_path / 'o.py'
        src.write_text('import os\n\ndef f(x: int) -> int:\n    return 10 // x\n')
        sanitizar_python(str(src), str(out), temp_dir=str(tmp_path))
        assert '10 // x' in out.read_text()

class TestCSanitizer:
    def test_generates_harness_for_module_without_main(self, tmp_path):
        f = tmp_path / 'codigo.c'
        f.write_text('int add(int a, int b){ return a + b; }\n')
        sanitizar_c(str(f), str(tmp_path))
        text = f.read_text()
        assert 'int main(void)' in text
        assert 'add(' in text.split('int main(void)')[1]

    def test_keeps_existing_main(self, tmp_path):
        f = tmp_path / 'codigo.c'
        original = 'int main(void){ return 0; }\n'
        f.write_text(original)
        assert sanitizar_c(str(f), str(tmp_path)) == []
        assert f.read_text() == original

    def test_mocks_missing_local_header(self, tmp_path):
        f = tmp_path / 'codigo.c'
        f.write_text('#include "missing.h"\nint main(void){ return 0; }\n')
        created = sanitizar_c(str(f), str(tmp_path))
        assert (tmp_path / 'missing.h').is_file()
        assert str(tmp_path / 'missing.h') in created

class TestCppSanitizer:

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


@known_defect('D9 (#19): #include names are joined to temp_dir unchecked')
@pytest.mark.parametrize('sanitize, name', [(sanitizar_c, 'codigo.c'), (sanitizar_cpp, 'codigo.cpp')])
def test_mock_headers_stay_inside_work_dir(tmp_path, sanitize, name):
    work = tmp_path / 'work'
    work.mkdir()
    f = work / name
    f.write_text('#include "../outside/escaped.h"\nint main(void){ return 0; }\n')
    sanitize(str(f), str(work))
    assert not (tmp_path / 'outside' / 'escaped.h').exists()
