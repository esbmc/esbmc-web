import os
import re
import subprocess

STDLIB_C = {
    'stdio.h', 'stdlib.h', 'string.h', 'math.h', 'stdbool.h',
    'stdint.h', 'stddef.h', 'assert.h', 'time.h', 'unistd.h', 'pthread.h',
    'limits.h', 'errno.h', 'ctype.h', 'float.h', 'stdarg.h', 'signal.h',
    'inttypes.h', 'setjmp.h', 'locale.h', 'sys/types.h', 'sys/stat.h', 'fcntl.h'
}

C_KEYWORDS = {
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if',
    'inline', 'int', 'long', 'register', 'restrict', 'return', 'short',
    'signed', 'sizeof', 'static', 'struct', 'switch', 'typedef', 'union',
    'unsigned', 'void', 'volatile', 'while', '_Bool', '_Complex', '_Imaginary',
    'bool', 'true', 'false', 'NULL', 'size_t', 'ssize_t', 'int8_t', 'int16_t',
    'int32_t', 'int64_t', 'uint8_t', 'uint16_t', 'uint32_t', 'uint64_t',
    'uintptr_t', 'intptr_t', 'ptrdiff_t', 'FILE', 'time_t', 'clock_t',
    'printf', 'fprintf', 'sprintf', 'snprintf', 'scanf', 'sscanf', 'malloc',
    'calloc', 'realloc', 'free', 'memcpy', 'memset', 'memmove', 'memcmp',
    'strlen', 'strcpy', 'strncpy', 'strcmp', 'strncmp', 'strcat', 'strncat',
    'exit', 'abort', 'assert', 'abs', 'labs', 'atoi', 'atol', 'atof',
    'strtol', 'strtoul', 'nondet_int', 'nondet_uint', 'nondet_char',
    'nondet_bool', '__VERIFIER_nondet_int', '__VERIFIER_nondet_uint',
    '__VERIFIER_assume', '__ESBMC_assume', '__ESBMC_assert'
}


def descubrir_headers_e_includes_c(root_dir: str):
    """Percorre recursivamente `root_dir` (ex: repositório Git clonado) e retorna:
    - `include_dirs`: lista ordenada de diretórios e raízes de include (ex: `src/`, `include/`)
      filtrando diretórios que sombreiam headers padrão da libc (como `openssllib/include`)
    - `headers_existentes`: conjunto de nomes e caminhos relativos de headers reais
    - `fontes_auxiliares`: lista de arquivos .c auxiliares (sem `main` e sem testes)
    """
    include_dirs_raizes = set()
    include_dirs_folhas = set()
    headers_existentes = set()
    fontes_auxiliares = []

    if not root_dir or not os.path.isdir(root_dir):
        return [], set(), []

    HEADERS_SISTEMA_SOMBREADOS = {
        'stdio.h', 'stdlib.h', 'string.h', 'limits.h', 'stdint.h', 'stddef.h',
        'assert.h', 'ctype.h', 'errno.h', 'float.h', 'math.h', 'time.h', 'unistd.h',
        'features.h', 'endian.h', 'byteswap.h', 'alloca.h', 'fcntl.h', 'signal.h',
        'pthread.h', 'inttypes.h', 'stdbool.h', 'stdarg.h', 'uchar.h', 'wchar.h',
        'wctype.h', 'semaphore.h', 'sched.h', 'fenv.h'
    }
    SEGMENTOS_IGNORADOS = (
        'os_stub', 'openssllib', 'verification/stubs', 'unit_test', 'selftests', 'fuzzing',
        'regression', 'unit', 'cpp/library', 'src/cpp/library', 'c2goto', 'src/c2goto',
        'disabled', 'benchmarks', 'benchmark', 'test', 'tests'
    )

    root_abs = os.path.abspath(root_dir)
    include_dirs_raizes.add(root_abs)

    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith('.')
            and d.lower() not in (
                'test', 'tests', 'build', 'cmake', 'docs', 'doc', 'regression', 'unit',
                'disabled', 'fuzz', 'fuzzing', 'benchmarks', 'benchmark'
            )
        ]
        rel_dir = os.path.relpath(dirpath, root_abs).replace('\\', '/').lower()
        if any(seg in rel_dir for seg in SEGMENTOS_IGNORADOS):
            continue

        nomes_lower = {fn.lower() for fn in filenames}
        sombreia_sistema = bool(nomes_lower & HEADERS_SISTEMA_SOMBREADOS) or any(seg in rel_dir for seg in SEGMENTOS_IGNORADOS)

        for fname in filenames:
            full_p = os.path.join(dirpath, fname)
            rel_p = os.path.relpath(full_p, root_abs).replace('\\', '/')
            if fname.endswith('.h'):
                headers_existentes.add(fname)
                headers_existentes.add(rel_p)
                if not sombreia_sistema:
                    include_dirs_folhas.add(dirpath)
                    anc = os.path.dirname(dirpath)
                    while anc and len(anc) >= len(root_abs) and anc != root_abs:
                        anc_rel = os.path.relpath(anc, root_abs).replace('\\', '/').lower()
                        if not any(seg in anc_rel for seg in SEGMENTOS_IGNORADOS):
                            include_dirs_raizes.add(anc)
                        novo_anc = os.path.dirname(anc)
                        if novo_anc == anc:
                            break
                        anc = novo_anc
            elif fname.endswith('.c') and fname != 'codigo.c':
                low = fname.lower()
                if 'test' in low or 'benchmark' in low or 'main' in low:
                    continue
                try:
                    with open(full_p, 'r', encoding='utf-8', errors='replace') as f:
                        conteudo = f.read()
                    if not _tem_funcao_main(conteudo):
                        fontes_auxiliares.append(full_p)
                except Exception:
                    pass

    raizes_ordenadas = sorted(include_dirs_raizes, key=lambda p: (p.count(os.sep), p))
    folhas_ordenadas = sorted(include_dirs_folhas - include_dirs_raizes, key=lambda p: (p.count(os.sep), p))
    todos_includes = (raizes_ordenadas + folhas_ordenadas)[:85]
    return todos_includes, headers_existentes, fontes_auxiliares


def _header_existe_no_projeto_c(inc: str, temp_dir: str, dir_arquivo: str, headers_existentes: set) -> bool:
    inc_norm = inc.replace('\\', '/')
    base = os.path.basename(inc_norm)
    if inc_norm in headers_existentes or base in headers_existentes:
        return True
    if os.path.exists(os.path.join(temp_dir, inc_norm)):
        return True
    if dir_arquivo and os.path.exists(os.path.join(dir_arquivo, inc_norm)):
        return True
    return False


def _tem_funcao_main(codigo: str) -> bool:
    codigo_sem_coment = re.sub(r'//.*?$|/\*.*?\*/', '', codigo, flags=re.DOTALL | re.MULTILINE)
    return bool(re.search(r'\b(?:int|void)\s+main\s*\(', codigo_sem_coment))


def _extrair_funcoes_definidas_c(codigo: str):
    codigo_limpo = re.sub(r'//.*?$|/\*.*?\*/', '', codigo, flags=re.DOTALL | re.MULTILINE)
    padrao = re.compile(
        r'^[ \t]*(?:static\s+|inline\s+|extern\s+)*([A-Za-z_][A-Za-z0-9_\s\*]*?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^;{}]*)\)\s*\{',
        re.MULTILINE
    )
    funcoes = []
    for m in padrao.finditer(codigo_limpo):
        ret_type = m.group(1).strip()
        fn_name = m.group(2).strip()
        params_raw = m.group(3).strip()
        if fn_name in ('if', 'while', 'for', 'switch', 'main') or fn_name.startswith('__'):
            continue
        if ret_type in ('else', 'return'):
            continue
        params = []
        if params_raw and params_raw != 'void':
            for p in params_raw.split(','):
                p = p.strip()
                if p and p != '...':
                    params.append(p)
        funcoes.append((fn_name, params))
    return funcoes


def _diagnosticar_erros_clang_c(caminho_arquivo: str, include_dirs: list):
    tipos_faltantes = set()
    structs_faltantes = set()
    identificadores_faltantes = set()
    funcoes_faltantes = set()

    cmd = ['clang', '-fsyntax-only', '-x', 'c', '-std=c11']
    for d in include_dirs:
        cmd.extend(['-I', d])
    cmd.append(caminho_arquivo)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        stderr = proc.stderr or ''
    except Exception:
        return tipos_faltantes, structs_faltantes, identificadores_faltantes, funcoes_faltantes

    for line in stderr.splitlines():
        m_type = re.search(r"unknown type name '([A-Za-z_][A-Za-z0-9_]*)'", line)
        if m_type:
            tipos_faltantes.add(m_type.group(1))

        m_struct = re.search(r"(?:variable has incomplete type|incomplete definition of type) 'struct ([A-Za-z_][A-Za-z0-9_]*)'", line)
        if m_struct:
            structs_faltantes.add(m_struct.group(1))

        m_fn = re.search(r"(?:implicit declaration of function|call to undeclared function) '([A-Za-z_][A-Za-z0-9_]*)'", line)
        if m_fn:
            funcoes_faltantes.add(m_fn.group(1))

        m_id = re.search(r"use of undeclared identifier '([A-Za-z_][A-Za-z0-9_]*)'", line)
        if m_id:
            identificadores_faltantes.add(m_id.group(1))

    return tipos_faltantes, structs_faltantes, identificadores_faltantes, funcoes_faltantes


def _gerar_harness_main_c(funcoes) -> str:
    if not funcoes:
        return "\n/* Harness Simbólico ESBMC Homogenizer */\nint main(void) {\n    return 0;\n}\n"

    linhas = [
        "\n/* ==========================================================================",
        " * HARNESS SIMBÓLICO GERADO PELO ESBMC C HOMOGENIZER (MÓDULO SEM MAIN)",
        " * ========================================================================== */",
        "extern int nondet_int(void);",
        "int main(void) {"
    ]

    for idx, (fn_name, params) in enumerate(funcoes[:5]):
        args_call = []
        for p_idx, p_decl in enumerate(params):
            if '*' in p_decl or '[' in p_decl:
                base_t = re.sub(r'\*.*|\[.*\]', '', p_decl).strip()
                tokens = base_t.split()
                tipo_limpo = " ".join(tokens[:-1]) if len(tokens) >= 2 else (tokens[0] if tokens else "int")
                if tipo_limpo in ('void', 'const void', 'const'):
                    tipo_limpo = 'char'
                tipo_limpo = re.sub(r'\bconst\b', '', tipo_limpo).strip() or 'int'
                buf_name = f"_sym_buf_{idx}_{p_idx}"
                linhas.append(f"    {tipo_limpo} {buf_name}[16];")
                args_call.append(buf_name)
            else:
                arg_name = f"_sym_arg_{idx}_{p_idx}"
                linhas.append(f"    int {arg_name} = nondet_int();")
                args_call.append(arg_name)
        linhas.append(f"    {fn_name}({', '.join(args_call)});")

    linhas.append("    return 0;")
    linhas.append("}\n")
    return "\n".join(linhas)


def sanitizar_c(caminho_arquivo: str, temp_dir: str, tem_flag_function: bool = False, sub_dir_repo: str = None):
    """Homogeneizador e Sanitizador Inteligente para C (C11)."""
    with open(caminho_arquivo, 'r', encoding='utf-8', errors='replace') as f:
        codigo_original = f.read()

    include_dirs, headers_existentes, _ = descubrir_headers_e_includes_c(temp_dir)
    if sub_dir_repo and os.path.isdir(sub_dir_repo) and sub_dir_repo not in include_dirs:
        include_dirs.insert(0, sub_dir_repo)

    includes_encontrados = set()
    for linha in codigo_original.splitlines():
        match = re.match(r'^\s*#include\s+["<]([^">]+)[">]', linha)
        if match:
            includes_encontrados.add(match.group(1))

    dir_arquivo = sub_dir_repo or os.path.dirname(caminho_arquivo)
    arquivos_gerados = []

    for inc in includes_encontrados:
        if inc in STDLIB_C:
            continue

        if _header_existe_no_projeto_c(inc, temp_dir, dir_arquivo, headers_existentes):
            continue

        caminho_mock = os.path.join(temp_dir, inc)
        os.makedirs(os.path.dirname(caminho_mock), exist_ok=True)
        macro_nome = "MOCK_" + re.sub(r'[^A-Za-z0-9]', '_', inc).upper()

        with open(caminho_mock, 'w', encoding='utf-8') as f:
            f.write(f"/* MOCK AUTOMÁTICO GERADO PELO ESBMC HOMOGENIZER PARA: {inc} */\n")
            f.write(f"#ifndef {macro_nome}\n")
            f.write(f"#define {macro_nome}\n\n")
            f.write("#include <stdint.h>\n#include <stddef.h>\n#include <stdbool.h>\n\n")
            f.write("#endif\n")

        arquivos_gerados.append(caminho_mock)

    declaracoes_injetadas = []
    nomes_ja_injetados = set()

    for _ in range(2):
        tipos, structs, idents, funcoes_ext = _diagnosticar_erros_clang_c(caminho_arquivo, include_dirs)
        novos = []

        for st in sorted(structs):
            if f"struct_{st}" not in nomes_ja_injetados:
                nomes_ja_injetados.add(f"struct_{st}")
                novos.append(f"struct {st} {{ int dummy; int value; int status; void *ptr; }};")

        for tp in sorted(tipos):
            if tp not in nomes_ja_injetados and tp not in C_KEYWORDS:
                nomes_ja_injetados.add(tp)
                novos.append(f"typedef int {tp};")

        for fn in sorted(funcoes_ext):
            if fn not in nomes_ja_injetados and fn not in C_KEYWORDS:
                nomes_ja_injetados.add(fn)
                novos.append(f"extern int {fn}();")

        for ident in sorted(idents):
            if ident not in nomes_ja_injetados and ident not in C_KEYWORDS and ident not in funcoes_ext:
                if ident.isupper():
                    nomes_ja_injetados.add(ident)
                    novos.append(f"#ifndef {ident}\n#define {ident} 16\n#endif")

        if not novos:
            break

        declaracoes_injetadas.extend(novos)
        bloco_cura = "/* === AUTO-HEALED DECLARATIONS (ESBMC HOMOGENIZER) === */\n" + "\n".join(declaracoes_injetadas) + "\n\n"
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            f.write(bloco_cura + codigo_original)

    with open(caminho_arquivo, 'r', encoding='utf-8', errors='replace') as f:
        codigo_atual = f.read()

    if not tem_flag_function and not _tem_funcao_main(codigo_atual):
        funcoes_definidas = _extrair_funcoes_definidas_c(codigo_original)
        harness_main = _gerar_harness_main_c(funcoes_definidas)
        codigo_atual = codigo_atual + "\n" + harness_main
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            f.write(codigo_atual)
        if not arquivos_gerados:
            arquivos_gerados.append("symbolic_main_harness")

    return arquivos_gerados