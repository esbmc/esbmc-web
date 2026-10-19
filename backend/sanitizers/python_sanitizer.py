import ast
import os
from typing import List, Tuple


MODULOS_PADRAO_ESBMC = {
    'typing', 'typing_extensions', 'math', 'random', 'enum', '__future__'
}


class LightImportFlattener(ast.NodeTransformer):
    """Achatador leve de imports para quando o usuário sobe os próprios arquivos de stub (.py) na aba Dependencies."""

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

        # Se o usuário enviou um stub local (ex: basehandlers.py) para `from framework import basehandlers`,
        # achata para `import basehandlers` para o ESBMC resolvê-lo no temp_dir
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
    """Detecta se o código Python precisa do ESBMC Homogenizer v2.0 (VeriBee).

    Retorna (True, motivo) quando:
      - O código possui imports de frameworks/módulos externos que não existem em `temp_dir`;
      - O código vem de um repositório Git profissional (classes/handlers/APIs sem `assert` top-level);
      - O código define classes ou funções profissionais mas não possui harness/assertions de entrada.

    Retorna (False, motivo) quando o código já é um harness formal (pastas harness/verification/tests),
    ou possui assertions/entrypoint, ou o repositório contém stubs locais (stubs.py, torch_stubs.py, etc.).
    """
    try:
        tree = ast.parse(codigo_fonte)
    except SyntaxError:
        return False, "Erro de sintaxe no código original"

    # Se já foi homogeneizado pelo VeriBee, não precisa homogeneizar novamente
    if "_esbmc_get_int_arg" in codigo_fonte or "verify_security_contracts" in codigo_fonte:
        return False, "Código já homogeneizado pelo VeriBee v2.0"

    # Se é explicitamente um harness de teste formal do repositório, preserva nativo
    if is_harness:
        return False, "Harness formal de teste profissional (preservando asserções e stubs nativos)"

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
            # Verifica `if __name__ == "__main__":`
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Assert, ast.Call)):
                    tem_chamada_toplevel = True

    for sub in ast.walk(tree):
        if isinstance(sub, ast.Assert):
            tem_assert = True
        elif isinstance(sub, ast.Import):
            for alias in sub.names:
                mod_root = alias.name.split('.')[0]
                if mod_root not in MODULOS_PADRAO_ESBMC:
                    # Verifica se o repositório possui o stub (ex: torch_stubs.py, nki_stubs.py, stubs.py ou mod_root.py)
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
        return True, f"Dependências externas detectadas ({', '.join(sorted(set(imports_faltantes))[:5])})"

    if is_git and tem_classe_ou_funcao and not tem_assert:
        return True, "Módulo de repositório Git sem harness formal (gerando contratos simbólicos VeriBee)"

    if tem_classe_ou_funcao and not tem_assert and not tem_chamada_toplevel:
        return True, "Classes/Funções sem ponto de entrada ou assertivas (gerando contratos simbólicos VeriBee)"

    return False, "Código Python autossuficiente ou com stubs fornecidos"


NONDET_POR_TIPO = {
    None: 'nondet_int()', 'int': 'nondet_int()', 'bool': 'nondet_bool()',
    'float': 'nondet_float()', 'str': 'nondet_str()',
}


def gerar_harness_python(codigo_fonte: str) -> Tuple[str, List[str], List[str]]:
    """Append calls to every top-level function with unconstrained nondet arguments (#14).

    The user's source is kept verbatim, so line numbers in counterexamples still match. A function
    is skipped (and listed) when a parameter's type has no nondet constructor in ESBMC-Python."""
    arvore = ast.parse(codigo_fonte)
    chamadas, ignoradas, linhas = [], [], []
    for no in arvore.body:
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
    is_harness: bool = False,
    forcar_homogenizer: bool = False
) -> dict:
    """Executa a sanitização/homogeneização Python de forma inteligente.

    Retorna um dicionário com metadados da sanitização:
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

    if forcar_homogenizer or usar_v2:
        codigo_final, chamadas, ignoradas = gerar_harness_python(codigo_fonte)
        with open(caminho_saida, 'w', encoding='utf-8') as f:
            f.write(codigo_final)
        return {
            'usou_homogenizer_v2': True,
            'motivo': motivo if not forcar_homogenizer else "Fallback automático para harness de entrada",
            'alvos_extraidos': len(chamadas),
            'funcoes_ignoradas': ignoradas,
            'caminho_saida': caminho_saida,
            'codigo_final': codigo_final
        }

    # Caso contrário, aplica apenas o achatamento leve para preservar stubs manuais enviados pelo usuário
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