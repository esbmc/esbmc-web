import ast
import os
from typing import List, Tuple


MODULOS_PADRAO_ESBMC = {
    'typing', 'typing_extensions', 'math', 'random', 'enum', '__future__'
}


class LightImportFlattener(ast.NodeTransformer):
    """Lightweight import flattener for when the user uploads their own stub files (.py) in the Dependencies tab."""

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.blocklist = {'flask', 'werkzeug', 'google', 'testing_config', 'user_models'}

    def _stub_existe_no_temp(self, mod_name: str) -> bool:
        if not self.temp_dir or not mod_name:
            return False
        base = mod_name.split('.')[-1]
        return os.path.isfile(os.path.join(self.temp_dir, f"{base}.py"))

    def visit_Import(self, node: ast.Import):
        self.generic_visit(node)
        novos = []
        for n in node.names:
            raiz = n.name.split('.')[0]
            if raiz in self.blocklist and not self._stub_existe_no_temp(n.name):
                continue
            novos.append(n)
        node.names = novos
        return node if node.names else None

    def visit_ImportFrom(self, node: ast.ImportFrom):
        self.generic_visit(node)
        if not node.module:
            return node

        # If the user uploaded a local stub (e.g. basehandlers.py) for `from framework import basehandlers`,
        # flatten it to `import basehandlers` so ESBMC resolves it in temp_dir
        novos_imports = []
        restantes = []
        for n in node.names:
            if self._stub_existe_no_temp(n.name):
                novos_imports.append(ast.alias(name=n.name, asname=n.asname))
            elif self._stub_existe_no_temp(node.module):
                restantes.append(n)
            elif node.module.split('.')[0] not in self.blocklist:
                restantes.append(n)

        if novos_imports and not restantes:
            return ast.copy_location(ast.Import(names=novos_imports), node)
        if restantes:
            node.names = restantes
            return node
        return None


def precisa_homogeneizar_v2(
    codigo_fonte: str,
    temp_dir: str = "",
    is_git: bool = False,
    is_harness: bool = False
) -> Tuple[bool, str]:
    """Detect whether the Python code needs the ESBMC Homogenizer v2.0 (VeriBee).

    Returns (True, reason) when:
      - the code imports external frameworks/modules that do not exist in `temp_dir`;
      - the code comes from a Git repository (classes/handlers/APIs with no top-level `assert`);
      - the code defines classes or functions but has no entry harness/assertions.

    Returns (False, reason) when the code is already a formal harness (harness/verification/tests folders),
    has assertions or an entry point, or the repository contains local stubs (stubs.py, torch_stubs.py, etc.).
    """
    try:
        tree = ast.parse(codigo_fonte)
    except SyntaxError:
        return False, "Syntax error in the original code"

    # Already homogenized by VeriBee; no need to homogenize again
    if "_esbmc_get_int_arg" in codigo_fonte or "verify_security_contracts" in codigo_fonte:
        return False, "Code already homogenized by VeriBee v2.0"

    imports_faltantes = []
    tem_assert = False
    tem_classe_ou_funcao = False
    tem_chamada_toplevel = False

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            tem_classe_ou_funcao = True
        elif isinstance(node, ast.Assert):
            tem_assert = True
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            tem_chamada_toplevel = True
        elif isinstance(node, ast.If):
            # Check for `if __name__ == "__main__":`
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Assert, ast.Call)):
                    tem_chamada_toplevel = True

    # A repository test harness that runs its own entry code is kept as is; one that only defines
    # functions still gets calls appended, otherwise nothing in it would execute.
    if is_harness and (tem_assert or tem_chamada_toplevel):
        return False, "Formal test harness (keeping its assertions and native stubs)"

    for sub in ast.walk(tree):
        if isinstance(sub, ast.Import):
            for alias in sub.names:
                mod_root = alias.name.split('.')[0]
                if mod_root not in MODULOS_PADRAO_ESBMC:
                    # Check whether the repository has the stub (e.g. torch_stubs.py, nki_stubs.py, stubs.py or mod_root.py)
                    tem_stub = False
                    if temp_dir and os.path.isdir(temp_dir):
                        candidatos_stubs = [
                            f"{mod_root}.py", f"{mod_root}_stubs.py", "stubs.py",
                            f"stubs/{mod_root}.py", f"harness/{mod_root}.py"
                        ]
                        for c_stub in candidatos_stubs:
                            if os.path.isfile(os.path.join(temp_dir, c_stub)):
                                tem_stub = True
                                break
                    if not tem_stub:
                        imports_faltantes.append(alias.name)
        elif isinstance(sub, ast.ImportFrom):
            mod_name = sub.module or ""
            mod_root = mod_name.split('.')[0] if mod_name else ""
            if mod_root and mod_root not in MODULOS_PADRAO_ESBMC:
                tem_stub = False
                if temp_dir and os.path.isdir(temp_dir):
                    candidatos_stubs = [
                        f"{mod_root}.py", f"{mod_root}_stubs.py", "stubs.py",
                        f"stubs/{mod_root}.py", f"harness/{mod_root}.py"
                    ]
                    for alias in sub.names:
                        candidatos_stubs.append(f"{alias.name}.py")
                    for c_stub in candidatos_stubs:
                        if os.path.isfile(os.path.join(temp_dir, c_stub)):
                            tem_stub = True
                            break
                if not tem_stub:
                    imports_faltantes.append(mod_name)

    if imports_faltantes:
        return True, f"External dependencies detected ({', '.join(sorted(set(imports_faltantes))[:5])})"

    if is_git and tem_classe_ou_funcao and not tem_assert:
        return True, "Git repository module without a formal harness (generating VeriBee symbolic contracts)"

    if tem_classe_ou_funcao and not tem_assert and not tem_chamada_toplevel:
        return True, "Classes/functions without an entry point or assertions (generating VeriBee symbolic contracts)"

    return False, "Self-contained Python code, or stubs provided"


NONDET_POR_TIPO = {
    None: 'nondet_int()', 'int': 'nondet_int()', 'bool': 'nondet_bool()',
    'float': 'nondet_float()', 'str': 'nondet_str()',
}


def gerar_harness_python(codigo_fonte: str) -> Tuple[str, List[str], List[str]]:
    """Append calls to every top-level function with unconstrained nondet arguments (#14).

    The user's source is kept verbatim, so line numbers in counterexamples still match. Functions it
    cannot call (unsupported parameter types, async functions, class methods) are returned as skipped,
    so a run that does not exercise them is never reported as fully SUCCESSFUL."""
    arvore = ast.parse(codigo_fonte)
    chamadas, ignoradas, linhas = [], [], []
    for no in arvore.body:
        if isinstance(no, ast.ClassDef):
            ignoradas.extend(f"{no.name}.{m.name}" for m in no.body
                             if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
            continue
        if isinstance(no, ast.AsyncFunctionDef):
            ignoradas.append(no.name)
            continue
        if not isinstance(no, ast.FunctionDef) or no.name.startswith('__'):
            continue
        args = no.args
        if args.vararg or args.kwarg or args.posonlyargs or any(d is None for d in args.kw_defaults):
            ignoradas.append(no.name)
            continue
        tipos = [a.annotation.id if isinstance(a.annotation, ast.Name) else (None if a.annotation is None else '?')
                 for a in args.args]
        if any(t not in NONDET_POR_TIPO for t in tipos):
            ignoradas.append(no.name)
            continue
        nomes = []
        for arg, tipo in zip(args.args, tipos):
            var = f"_esbmc_{no.name}_{arg.arg}"
            linhas.append(f"{var}: {tipo or 'int'} = {NONDET_POR_TIPO[tipo]}")
            nomes.append(var)
        linhas.append(f"{no.name}({', '.join(nomes)})")
        chamadas.append(no.name)
    if not linhas:
        return codigo_fonte, chamadas, ignoradas
    cabecalho = "\n\n# --- ESBMC-Web harness: each function called with unconstrained inputs ---\n"
    return codigo_fonte.rstrip('\n') + cabecalho + "\n".join(linhas) + "\n", chamadas, ignoradas


def sanitizar_python(
    caminho_arquivo: str,
    caminho_saida: str,
    temp_dir: str = "",
    is_git: bool = False,
    is_harness: bool = False
) -> dict:
    """Run Python sanitization/homogenization.

    Returns a dictionary of sanitization metadata:
      {
        'usou_homogenizer_v2': bool,
        'motivo': str,
        'alvos_extraidos': int,
        'caminho_saida': str,
        'codigo_final': str
      }
    """
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        codigo_fonte = f.read()

    if not temp_dir:
        temp_dir = os.path.dirname(caminho_arquivo)

    usar_v2, motivo = precisa_homogeneizar_v2(
        codigo_fonte, temp_dir=temp_dir, is_git=is_git, is_harness=is_harness
    )

    if usar_v2:
        codigo_final, chamadas, ignoradas = gerar_harness_python(codigo_fonte)
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(codigo_final)
        return {
            'usou_homogenizer_v2': True,
            'motivo': motivo,
            'alvos_extraidos': len(chamadas),
            'funcoes_ignoradas': ignoradas,
            'caminho_saida': caminho_saida,
            'codigo_final': codigo_final
        }

    # Otherwise apply only the lightweight flattening, preserving manual stubs uploaded by the user
    tree = ast.parse(codigo_fonte)
    flattener = LightImportFlattener(temp_dir=temp_dir)
    tree_modificada = flattener.visit(tree)
    ast.fix_missing_locations(tree_modificada)
    codigo_limpo = ast.unparse(tree_modificada)

    with open(caminho_saida, 'w', encoding='utf-8') as f:
        f.write(codigo_limpo)

    return {
        'usou_homogenizer_v2': False,
        'motivo': motivo,
        'alvos_extraidos': 0,
        'caminho_saida': caminho_saida,
        'codigo_final': codigo_limpo
    }