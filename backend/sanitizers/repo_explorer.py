#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESBMC Repository Explorer & Inter-Directory Dependency Slicer (RepoSlice-BMC)
Developed for a Master's dissertation (UFAM).

4-phase algorithm for exploring and formally verifying multi-directory repositories:
  - Phase 1 (Repository Crawler & Symbol Graph): recursively walks the repository's directories,
    building the global symbol graph (functions, classes, headers and internal modules).
  - Phase 2 (Heuristic Target Prioritization): ranks the verifiable modules by symbolic
    criticality (entry points, HTTP handlers, memory/pointer manipulation, arithmetic).
  - Phase 3 (Inter-Directory Dependency Slicing): merges the dependencies that live in other
    folders of the same repository (AST inlining in Python, cross-resolution of translation units
    in C/C++), isolating only the external boundary for symbolic sanitization.
  - Phase 4 (Batch Bounded Model Checking & CWE Aggregation): runs ESBMC with per-module resource
    limits and consolidates the formal proofs (SAFE) and counterexamples (CWEs).
"""

import ast
import builtins
import os
import posixpath
import re
import symtable
from typing import Dict, FrozenSet, List, NamedTuple, Set, Tuple, Optional


PASTAS_SISTEMA = {
    '.git', '.github', '.vscode', '__pycache__', 'node_modules', 'venv', '.venv',
    'env', 'build', 'dist', 'docs', 'doc', 'migrations', 'static', 'templates',
    'assets', 'vendor', 'third_party', 'extern', 'external', 'cmake', 'disabled'
}
PASTAS_IGNORADAS = PASTAS_SISTEMA

PASTAS_HARNESS_PROFISSIONAIS = {
    'harness', 'harnesses', 'verification', 'verify', 'labs', 'lab',
    'proofs', 'proof', 'tests', 'test', 'testing'
}


def _extrair_diretivas_do_arquivo(conteudo: str) -> Tuple[Optional[str], List[str]]:
    """Extract expected-oracle directives and ESBMC flags from comments in the source code.
    Accepted examples:
      // esbmc-expected: FAILED (or SUCCESSFUL)
      // esbmc-flags: --unwind 6 --memory-leak-check
      # esbmc-expected: VERIFICATION FAILED
      # esbmc-flags: --overflow-check
    """
    expected = None
    flags: List[str] = []
    if not conteudo:
        return expected, flags

    for line in conteudo.splitlines()[:30]:
        line_clean = line.strip()
        m_exp = re.search(r'(?://|#)\s*(?:esbmc-)?expected(?:\s*verdict)?\s*:\s*([A-Za-z0-9_\-\s]+)', line_clean, re.IGNORECASE)
        if m_exp:
            raw_v = m_exp.group(1).strip().upper()
            if "FAIL" in raw_v:
                expected = "VERIFICATION FAILED"
            elif "SUCCESS" in raw_v or "PASS" in raw_v:
                expected = "VERIFICATION SUCCESSFUL"
            else:
                expected = raw_v

        m_flags = re.search(r'(?://|#)\s*(?:esbmc-)?flags\s*:\s*(.+)', line_clean, re.IGNORECASE)
        if m_flags:
            partes = m_flags.group(1).strip().split()
            for p in partes:
                if p.startswith('-') or (flags and flags[-1].startswith('-') and not flags[-1].startswith('--no-')):
                    flags.append(p)

    return expected, flags


def _extrair_manifesto_orquestrador(repo_dir: str) -> Dict[str, Dict[str, object]]:
    """Parse known orchestrator scripts in the repository (e.g. vLLM/AWS-Neuron's verify.py
    or the UNIFEI labs' run_checks.sh) and extract the mapping from files to their expected verdicts and flags."""
    mapa_manifesto: Dict[str, Dict[str, object]] = {}
    if not repo_dir or not os.path.isdir(repo_dir):
        return mapa_manifesto

    # 1. Look for shell check scripts (e.g. run_checks.sh, check.sh, run_tests.sh)
    for root, _, files in os.walk(repo_dir):
        for f in files:
            if f.endswith('.sh') or f in ('run_checks', 'verify'):
                caminho_sh = os.path.join(root, f)
                try:
                    with open(caminho_sh, 'r', encoding='utf-8', errors='replace') as f_sh:
                        linhas = f_sh.readlines()
                    for linha in linhas:
                        ln = linha.strip()
                        if ln.startswith('#') or not ln:
                            continue
                        # Pattern: check labs/lab2/overflow.c "VERIFICATION FAILED"
                        m_check = re.search(r'(?:check|verify|run_test)\s+["\']?([^"\'\s]+\.(?:c|cpp|cc|py))["\']?\s+["\']?([^"\'\n]+)["\']?', ln, re.IGNORECASE)
                        if m_check:
                            arq_rel = m_check.group(1).replace('\\', '/').lower().lstrip('./')
                            raw_ver = m_check.group(2).strip().upper()
                            ver_norm = "VERIFICATION FAILED" if "FAIL" in raw_ver else ("VERIFICATION SUCCESSFUL" if ("SUCCESS" in raw_ver or "PASS" in raw_ver) else raw_ver)
                            mapa_manifesto[arq_rel] = {
                                'expected_verdict': ver_norm,
                                'custom_flags': [],
                                'source': f
                            }
                            mapa_manifesto[os.path.basename(arq_rel)] = mapa_manifesto[arq_rel]

                        # Pattern: esbmc labs/lab2/overflow.c --unwind 1 ...
                        if 'esbmc ' in ln:
                            partes = ln.split()
                            arq_cand = None
                            flags_cand = []
                            for idx_p, p in enumerate(partes):
                                if p.endswith(('.c', '.cpp', '.py')) and not p.startswith('-'):
                                    arq_cand = p.replace('\\', '/').lower().lstrip('./')
                                elif p.startswith('-') and idx_p > 0 and partes[idx_p - 1] != 'check':
                                    flags_cand.append(p)
                            if arq_cand:
                                entry = mapa_manifesto.setdefault(arq_cand, {'expected_verdict': None, 'custom_flags': [], 'source': f})
                                if flags_cand:
                                    entry['custom_flags'] = flags_cand
                                mapa_manifesto[os.path.basename(arq_cand)] = entry
                except Exception:
                    pass

    # 2. Look for a verify.py orchestrator (vLLM / AWS-Neuron style)
    verify_py_path = os.path.join(repo_dir, "verify.py")
    if os.path.isfile(verify_py_path):
        try:
            with open(verify_py_path, 'r', encoding='utf-8', errors='replace') as f_vpy:
                conteudo_vpy = f_vpy.read()
            # Find strings naming referenced .py or .c files
            for m_arq in re.finditer(r'["\']([^"\']+\.(?:py|c|cpp))["\']', conteudo_vpy):
                c_rel = m_arq.group(1).replace('\\', '/').lower().lstrip('./')
                if c_rel not in mapa_manifesto:
                    mapa_manifesto[c_rel] = {
                        'expected_verdict': None,
                        'custom_flags': [],
                        'source': 'verify.py'
                    }
                    mapa_manifesto[os.path.basename(c_rel)] = mapa_manifesto[c_rel]
        except Exception:
            pass

    return mapa_manifesto


def _eh_arquivo_teste_ou_ignorado(rel_path: str, incluir_testes: bool = False) -> bool:
    norm = rel_path.replace('\\', '/').lower()
    partes = norm.split('/')
    if any(p in PASTAS_SISTEMA or (p.startswith('.') and p not in ('.', '..')) for p in partes[:-1]):
        return True
    fname = partes[-1]
    if fname in ('__init__.py', 'setup.py', 'conftest.py', 'manage.py', 'wsgi.py', 'asgi.py'):
        return True
    if fname.startswith(('esbmc_', 'sanitized_', 'codigo_esbmc', 'modulo_')):
        return True
    if not incluir_testes:
        # In classic test folders, outside test-suite mode
        if any(p in ('regression', 'unit', 'disabled', 'benchmarks', 'benchmark') for p in partes[:-1]):
            return True
        if fname.endswith(('_test.py', '_tests.py', '_test.cpp', '_test.c', 'test.cpp', 'test.c')):
            return True
        if fname.startswith(('test_', 'tests_')):
            return True
        if 'test/' in norm or 'tests/' in norm or 'testing/' in norm:
            return True
    return False


# ==============================================================================
# PHASES 1 & 3 (PYTHON): SYMBOL GRAPH AND INTER-DIRECTORY AST MERGING
# ==============================================================================

MAX_DEFINICOES_FUNDIDAS = 40

# Module attributes such as __name__ and __file__ would describe the target once copied, so they are left unresolved.
_NOMES_IMPLICITOS = frozenset(dir(builtins)) - {'__name__', '__doc__', '__spec__', '__loader__', '__package__'}
_ERROS_DE_ANALISE = (SyntaxError, ValueError, RecursionError, MemoryError)


class FusaoPythonIncompleta(Exception):
    """The in-repository dependencies of a module cannot all be copied into it."""


class _Unidade(NamedTuple):
    """A top-level statement (a single alias, for imports) and the module-level names it binds and reads."""
    stmt: ast.stmt
    liga: FrozenSet[str]
    le_agora: FrozenSet[str]
    le_depois: FrozenSet[str]


def _nome_modulo_python(rel_path: str) -> str:
    partes = os.path.splitext(rel_path)[0].split('/')
    if partes[-1] == '__init__':
        partes.pop()
    return '.'.join(partes)


def _importacao_isolada(stmt: ast.stmt, alias: ast.alias) -> ast.stmt:
    if isinstance(stmt, ast.ImportFrom):
        return ast.ImportFrom(module=stmt.module, names=[alias], level=stmt.level)
    return ast.Import(names=[alias])


def _variaveis_de_compreensao(stmt: ast.stmt) -> Set[str]:
    """Comprehension variables, which symtable reports as module-level names since PEP 709."""
    nomes: Set[str] = set()
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return nomes
    pilha: List[ast.AST] = [stmt]
    while pilha:
        for filho in ast.iter_child_nodes(pilha.pop()):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(filho, ast.comprehension):
                nomes.update(n.id for n in ast.walk(filho.target) if isinstance(n, ast.Name))
            pilha.append(filho)
    return nomes


def _analisar_nomes(stmt: ast.stmt) -> _Unidade:
    """Read binding and use from symtable. Class bodies run with the statement; function bodies and
    annotations run later, so their reads only matter if the function is used."""
    tabela = symtable.symtable(ast.unparse(stmt), '<slice>', 'exec')
    liga: Set[str] = set()
    le_agora: Set[str] = set()
    le_depois: Set[str] = set()
    for s in tabela.get_symbols():
        if s.is_assigned() or s.is_imported():
            liga.add(s.get_name())
        if s.is_referenced():
            le_agora.add(s.get_name())
    pilha = [(t, t.get_type() == 'class') for t in tabela.get_children()]
    while pilha:
        t, agora = pilha.pop()
        for s in t.get_symbols():
            if s.is_declared_global():
                liga.add(s.get_name())
            if s.is_global() and (s.is_referenced() or s.is_declared_global()):
                (le_agora if agora else le_depois).add(s.get_name())
        pilha.extend((f, agora and f.get_type() == 'class') for f in t.get_children())
    locais = _variaveis_de_compreensao(stmt)
    return _Unidade(stmt, frozenset(liga - locais), frozenset(le_agora - locais), frozenset(le_depois - locais))


def _eh_guarda_main(stmt: ast.stmt) -> bool:
    teste = getattr(stmt, 'test', None)
    return (isinstance(stmt, ast.If) and isinstance(teste, ast.Compare)
            and isinstance(teste.left, ast.Name) and teste.left.id == '__name__'
            and len(teste.ops) == 1 and isinstance(teste.ops[0], ast.Eq)
            and isinstance(teste.comparators[0], ast.Constant) and teste.comparators[0].value == '__main__')


def _unidades_do_modulo(tree: ast.Module, sem_guarda_main: bool = True) -> Tuple[List[_Unidade], Set[str]]:
    """Split a module into units, leaving out its `if __name__ == '__main__'` block unless told
    otherwise; also return its __future__ features."""
    unidades: List[_Unidade] = []
    futuros: Set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
            futuros.update(a.name for a in stmt.names)
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                liga = frozenset() if alias.name == '*' else frozenset({alias.asname or alias.name.split('.')[0]})
                unidades.append(_Unidade(_importacao_isolada(stmt, alias), liga, frozenset(), frozenset()))
        elif not (sem_guarda_main and _eh_guarda_main(stmt)):
            unidades.append(_analisar_nomes(stmt))
    return unidades, futuros


def _alcance_imediato(unidades: List[_Unidade]) -> List[FrozenSet[str]]:
    """For each unit, the module-level names it can touch while it runs, following the bodies of
    the module's own functions it calls or decorates with."""
    le_depois_de: Dict[str, Set[str]] = {}
    for unidade in unidades:
        for nome in unidade.liga:
            le_depois_de.setdefault(nome, set()).update(unidade.le_depois)
    alcances = []
    for unidade in unidades:
        alcance = set(unidade.le_agora)
        fila = list(alcance)
        while fila:
            for nome in le_depois_de.get(fila.pop(), ()):
                if nome not in alcance:
                    alcance.add(nome)
                    fila.append(nome)
        alcances.append(frozenset(alcance))
    return alcances


def construir_indice_python_repositorio(repo_dir: str) -> Dict[str, object]:
    """Build the Python symbol graph across every folder of the repository, keyed by dotted module name.
    A module that cannot be read or analysed maps to None."""
    modulos: Dict[str, Optional[Dict[str, object]]] = {}

    if not repo_dir or not os.path.isdir(repo_dir):
        return {'modulos': modulos}

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS and not d.startswith('.')]
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, repo_dir).replace('\\', '/')
            # Package __init__ files are never verification targets, but they do re-export names.
            if fname != '__init__.py' and _eh_arquivo_teste_ou_ignorado(rel_path):
                continue
            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    unidades, futuros = _unidades_do_modulo(ast.parse(f.read()))
                modulos[_nome_modulo_python(rel_path)] = {
                    'rel': rel_path, 'unidades': unidades, 'alcances': _alcance_imediato(unidades), 'futuros': futuros
                }
            except (OSError, *_ERROS_DE_ANALISE):
                modulos[_nome_modulo_python(rel_path)] = None

    return {'modulos': modulos}


def _modulos_e_pacotes(modulos: Dict[str, object]) -> Set[str]:
    conhecidos = set(modulos)
    for nome in modulos:
        partes = nome.split('.')
        conhecidos.update('.'.join(partes[:i]) for i in range(1, len(partes)))
    return conhecidos


def _origem_interna(modulos: Dict[str, object], conhecidos: Set[str], rel_importador: str,
                    importacao: ast.stmt) -> Optional[Tuple[str, Optional[str]]]:
    """For a single-alias import, return (repository module, name), with name None when the import
    takes a whole module, or None when it refers to nothing in the repository.

    Absolute imports are tried against every ancestor folder of the importer, as if that folder
    were on sys.path, from the innermost outwards.
    """
    pacote = _nome_modulo_python(rel_importador).split('.') if rel_importador else []
    if rel_importador and not rel_importador.endswith('__init__.py'):
        pacote = pacote[:-1]
    alias = importacao.names[0]

    if isinstance(importacao, ast.Import):
        for i in range(len(pacote), -1, -1):
            if '.'.join(pacote[:i] + [alias.name]) in conhecidos:
                return '.'.join(pacote[:i] + [alias.name]), None
        return None

    if importacao.level:
        if importacao.level - 1 > len(pacote):
            raise FusaoPythonIncompleta(f"relative import beyond the repository root in {rel_importador}")
        bases = [pacote[:len(pacote) - importacao.level + 1]]
    else:
        bases = [pacote[:i] for i in range(len(pacote), -1, -1)]
    for base in bases:
        modulo = '.'.join(base + ([importacao.module] if importacao.module else []))
        submodulo = f'{modulo}.{alias.name}'.lstrip('.')
        if submodulo in conhecidos:
            return submodulo, None
        if modulo in modulos:
            return modulo, alias.name
    if importacao.level:
        raise FusaoPythonIncompleta(f"relative import in {rel_importador} is outside the indexed repository")
    return None


def _simbolo_importado(origem: Tuple[str, Optional[str]], alias: ast.alias, rel: str) -> Tuple[str, str]:
    modulo, nome = origem
    if nome is None:
        raise FusaoPythonIncompleta(f"{rel} imports '{modulo}' as a whole")
    if nome == '*':
        raise FusaoPythonIncompleta(f"{rel} star-imports from '{modulo}'")
    if alias.asname and alias.asname != nome:
        raise FusaoPythonIncompleta(f"'{nome}' is imported from '{modulo}' under another name in {rel}")
    return modulo, nome


def _rejeitar_importacoes_internas_aninhadas(modulos: Dict[str, object], conhecidos: Set[str], rel: str, stmt: ast.stmt):
    for no in ast.walk(stmt):
        if no is not stmt and isinstance(no, (ast.Import, ast.ImportFrom)) and getattr(no, 'module', '') != '__future__':
            for alias in no.names:
                if _origem_interna(modulos, conhecidos, rel, _importacao_isolada(no, alias)):
                    raise FusaoPythonIncompleta(f"{rel}:{no.lineno} imports from the repository inside a block")


def _assinatura_importacao(importacao: ast.stmt) -> str:
    alias = importacao.names[0]
    if isinstance(importacao, ast.Import) and not alias.asname:
        return 'import ' + alias.name.split('.')[0]
    return ast.dump(importacao)


def _descrever_unidade(unidade: _Unidade, rel: str) -> str:
    stmt = unidade.stmt
    if isinstance(stmt, ast.ClassDef):
        return f"class {stmt.name} [{rel}]"
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{stmt.name}() [{rel}]"
    return f"{', '.join(sorted(unidade.liga)) or 'statement'} [{rel}:{stmt.lineno}]"


def fundir_dependencias_internas_python(
    codigo_alvo: str,
    repo_dir: str,
    caminho_rel_alvo: str = "",
    indice_precalculado: Optional[Dict[str, object]] = None
) -> Tuple[str, List[str]]:
    """Replace the target's `from <repo module> import ...` statements with the imported definitions
    and everything they transitively need from the repository: callees, module-level names, the
    statements that mutate those names, and the external imports they use.

    Returns: (code_with_merged_dependencies, list_of_merged_symbols)
    Raises FusaoPythonIncompleta when the slice cannot be completed; the target is then left as is.
    """
    try:
        arvore_alvo = ast.parse(codigo_alvo)
    except _ERROS_DE_ANALISE:
        return codigo_alvo, []

    indice = indice_precalculado or construir_indice_python_repositorio(repo_dir)
    modulos: Dict[str, Optional[Dict[str, object]]] = indice.get('modulos', {})  # type: ignore
    rel_alvo = posixpath.normpath(caminho_rel_alvo.replace('\\', '/')) if caminho_rel_alvo else ''
    modulo_alvo = _nome_modulo_python(rel_alvo) if rel_alvo else None
    conhecidos = _modulos_e_pacotes(modulos)

    try:
        unidades_alvo, futuros = _unidades_do_modulo(arvore_alvo, sem_guarda_main=False)
    except _ERROS_DE_ANALISE as e:
        raise FusaoPythonIncompleta(f"cannot analyse the target: {e}") from e

    # Each top-level name of the merged program must come from exactly one origin.
    origem_do_nome: Dict[str, str] = {}

    def reservar(nome: str, origem: str):
        anterior = origem_do_nome.setdefault(nome, origem)
        if anterior != origem:
            raise FusaoPythonIncompleta(f"'{nome}' from {origem} clashes with {anterior}")

    importacoes_internas: List[Tuple[str, str]] = []
    aliases_removidos: Set[int] = set()
    nomes_lidos_alvo: Set[str] = set()
    for unidade in unidades_alvo:
        nomes_lidos_alvo |= unidade.le_agora | unidade.le_depois
        if not isinstance(unidade.stmt, (ast.Import, ast.ImportFrom)):
            _rejeitar_importacoes_internas_aninhadas(modulos, conhecidos, rel_alvo, unidade.stmt)
            for nome in unidade.liga:
                reservar(nome, rel_alvo or 'target')
            continue
        origem = _origem_interna(modulos, conhecidos, rel_alvo, unidade.stmt)
        if origem is None:
            for nome in unidade.liga:
                reservar(nome, _assinatura_importacao(unidade.stmt))
            continue
        importacoes_internas.append(_simbolo_importado(origem, unidade.stmt.names[0], rel_alvo or 'the target'))
        aliases_removidos.add(id(unidade.stmt.names[0]))

    if not importacoes_internas:
        return codigo_alvo, []

    selecionadas: Dict[str, Set[int]] = {}
    dependencias: Dict[Optional[str], List[str]] = {modulo_alvo: []}
    nomes_vistos: Set[Tuple[str, str]] = set()

    def precisar(modulo: str, nome: str):
        if (modulo, nome) in nomes_vistos:
            return
        nomes_vistos.add((modulo, nome))
        if modulo == modulo_alvo:
            raise FusaoPythonIncompleta(f"'{nome}' is imported back from the target")
        info = modulos[modulo]
        if info is None:
            raise FusaoPythonIncompleta(f"cannot analyse module '{modulo}'")
        unidades: List[_Unidade] = info['unidades']  # type: ignore
        ligadoras = [i for i, u in enumerate(unidades) if nome in u.liga]
        if not ligadoras:
            if nome in _NOMES_IMPLICITOS:
                return
            raise FusaoPythonIncompleta(f"cannot find '{nome}' in {info['rel']}")
        # Module code that touches a name while it runs may fill it (registries, initialisers), so it
        # comes along. Imported modules are exempt: almost every statement reads one.
        if not all(isinstance(unidades[i].stmt, (ast.Import, ast.ImportFrom)) for i in ligadoras):
            ligadoras += [i for i, alcance in enumerate(info['alcances']) if nome in alcance]  # type: ignore
        for i in ligadoras:
            selecionar(modulo, i)

    def selecionar(modulo: str, i: int):
        escolhidas = selecionadas.setdefault(modulo, set())
        if i in escolhidas:
            return
        info = modulos[modulo]
        rel: str = info['rel']  # type: ignore
        unidade: _Unidade = info['unidades'][i]  # type: ignore
        dependencias.setdefault(modulo, [])
        if isinstance(unidade.stmt, (ast.Import, ast.ImportFrom)):
            origem = _origem_interna(modulos, conhecidos, rel, unidade.stmt)
            if origem is not None:
                origem_modulo, nome = _simbolo_importado(origem, unidade.stmt.names[0], rel)
                dependencias[modulo].append(origem_modulo)
                precisar(origem_modulo, nome)
                return
        escolhidas.add(i)
        if sum(map(len, selecionadas.values())) > MAX_DEFINICOES_FUNDIDAS:
            raise FusaoPythonIncompleta(f"more than {MAX_DEFINICOES_FUNDIDAS} definitions needed")
        if isinstance(unidade.stmt, (ast.Import, ast.ImportFrom)):
            for nome in unidade.liga:
                reservar(nome, _assinatura_importacao(unidade.stmt))
            return
        _rejeitar_importacoes_internas_aninhadas(modulos, conhecidos, rel, unidade.stmt)
        for nome in unidade.liga:
            reservar(nome, rel)
        for nome in sorted(unidade.le_agora | unidade.le_depois):
            precisar(modulo, nome)

    for modulo, nome in importacoes_internas:
        if nome in nomes_lidos_alvo:
            dependencias[modulo_alvo].append(modulo)
            precisar(modulo, nome)

    # Emit modules in the order Python would finish importing them.
    ordem: List[str] = []
    em_curso: Set[Optional[str]] = set()

    def ordenar(modulo: Optional[str]):
        if modulo in em_curso:
            raise FusaoPythonIncompleta(f"circular import through '{modulo}'")
        if modulo in ordem:
            return
        em_curso.add(modulo)
        for dependencia in dependencias.get(modulo, []):
            ordenar(dependencia)
        em_curso.discard(modulo)
        if modulo != modulo_alvo:
            ordem.append(modulo)

    ordenar(modulo_alvo)

    copias: List[ast.stmt] = []
    importacoes_emitidas: Set[str] = set()
    simbolos_fundidos: List[str] = []
    for modulo in ordem:
        info = modulos[modulo]
        novos = info['futuros'] - futuros  # type: ignore
        if novos - {'annotations'}:
            raise FusaoPythonIncompleta(f"{info['rel']} uses __future__ features the target does not: {', '.join(sorted(novos))}")
        futuros |= novos
        for i in sorted(selecionadas.get(modulo, ())):
            unidade: _Unidade = info['unidades'][i]  # type: ignore
            if isinstance(unidade.stmt, (ast.Import, ast.ImportFrom)):
                if ast.dump(unidade.stmt) not in importacoes_emitidas:
                    importacoes_emitidas.add(ast.dump(unidade.stmt))
                    copias.append(unidade.stmt)
            else:
                copias.append(unidade.stmt)
                simbolos_fundidos.append(_descrever_unidade(unidade, info['rel']))  # type: ignore

    # The copies take the place of the first in-repository import, so earlier target code still runs first.
    corpo: List[ast.stmt] = []
    posicao = None
    for stmt in arvore_alvo.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
            continue
        if isinstance(stmt, ast.ImportFrom) and any(id(a) in aliases_removidos for a in stmt.names):
            posicao = len(corpo) if posicao is None else posicao
            continue
        corpo.append(stmt)
    docstring = corpo[:1] if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
        and isinstance(corpo[0].value.value, str) else []
    futuro = [ast.ImportFrom(module='__future__', names=[ast.alias(f) for f in sorted(futuros)], level=0)] if futuros else []
    arvore_alvo.body = docstring + futuro + corpo[len(docstring):posicao] + copias + corpo[posicao:]
    ast.fix_missing_locations(arvore_alvo)
    return ast.unparse(arvore_alvo), simbolos_fundidos


# ==============================================================================
# PHASES 1 & 3 (C / C++): INTER-DIRECTORY TRANSLATION-UNIT GRAPH
# ==============================================================================

def resolver_fontes_dependentes_cpp(caminho_alvo: str, repo_dir: str) -> Tuple[List[str], List[str]]:
    """Build the C/C++ symbol graph across the repository's subdirectories and find which
    `.cpp`/`.c` files in other folders implement the functions/classes declared in the
    headers the target file includes.

    Returns: (dependent_cpp_paths, link_descriptions)
    """
    if not repo_dir or not os.path.isdir(repo_dir) or not os.path.isfile(caminho_alvo):
        return [], []

    with open(caminho_alvo, 'r', encoding='utf-8', errors='replace') as f:
        codigo_alvo = f.read()

    HEADERS_PADRAO_IGNORADOS = {
        'stdio.h', 'stdlib.h', 'string.h', 'math.h', 'stdbool.h', 'stdint.h', 'stddef.h',
        'assert.h', 'time.h', 'unistd.h', 'pthread.h', 'limits.h', 'errno.h', 'ctype.h',
        'iostream', 'vector', 'string', 'map', 'set', 'algorithm', 'array', 'memory',
        'utility', 'functional', 'chrono', 'cstring', 'cstdio', 'cstdlib', 'cstdint',
        'climits', 'cassert', 'cmath', 'type_traits', 'optional', 'span', 'tuple',
        'freertos.h', 'task.h', 'queue.h', 'timers.h', 'semphr.h', 'portmacro.h'
    }
    NOMES_GENERICOS_IGNORADOS = {
        'if', 'while', 'for', 'switch', 'return', 'sizeof', 'alignof', 'constexpr',
        'static_assert', 'main', 'init', 'read', 'write', 'make', 'inst', 'get', 'set',
        'open', 'close', 'start', 'stop', 'run', 'reset', 'clear', 'send', 'receive', 'task',
        'as_string', 'to_string', 'type', 'id', 'value', 'data', 'c_str', 'begin', 'end',
        'empty', 'size', 'front', 'back', 'push_back', 'pop_back', 'insert', 'erase',
        'find', 'count', 'contains', 'format', 'print', 'println', 'name', 'at', 'hash',
        'make_true', 'make_false', 'make_nil', 'is_nil_expr', 'is_nil_type',
        'is_true', 'is_false', 'is_zero', 'is_one', 'is_valid', 'is_empty', 'is_null',
        'diff', 'compare', 'equal', 'check', 'test', 'match', 'clone', 'copy', 'swap',
        'dump', 'show', 'display', 'validate', 'verify'
    }

    includes_brutos = re.findall(r'#include\s+["<]([^">]+)[">]', codigo_alvo)
    includes_alvo = [inc.replace('\\', '/').strip() for inc in includes_brutos if os.path.basename(inc).lower() not in HEADERS_PADRAO_IGNORADOS]
    if not includes_alvo:
        return [], []

    nomes_headers = {os.path.basename(inc).lower() for inc in includes_alvo}
    dir_alvo_rel = os.path.dirname(os.path.relpath(os.path.abspath(caminho_alvo), repo_dir))
    stem_para_caminhos: Dict[str, Set[str]] = {}
    for inc in includes_alvo:
        stem_inc = os.path.splitext(os.path.basename(inc))[0].lower()
        stem_para_caminhos.setdefault(stem_inc, set()).add(os.path.splitext(inc)[0].lower())
        # "../lib/lib.h" from app/main.c names lib/lib.h; match its implementation by repo path too
        relativo = os.path.normpath(os.path.join(dir_alvo_rel, inc)).replace('\\', '/')
        if not relativo.startswith('..'):
            stem_para_caminhos[stem_inc].add(os.path.splitext(relativo)[0].lower())

    chamadas_alvo = set(re.findall(r'(?<![\.\->])\b([A-Za-z_][A-Za-z0-9_]*)\s*\(', codigo_alvo)) - NOMES_GENERICOS_IGNORADOS

    fontes_vinculadas: List[str] = []
    descricoes_vinculos: List[str] = []
    alvo_abs = os.path.abspath(caminho_alvo)
    eh_alvo_c = alvo_abs.endswith('.c')
    extensoes_compativeis = ('.c',) if eh_alvo_c else ('.cpp', '.cc', '.cxx')

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS and not d.startswith('.')]
        for fname in filenames:
            if not fname.endswith(extensoes_compativeis):
                continue
            full_p = os.path.abspath(os.path.join(dirpath, fname))
            if full_p == alvo_abs or fname in ('codigo.cpp', 'codigo.c') or fname.startswith('modulo_'):
                continue
            rel_p = os.path.relpath(full_p, repo_dir).replace('\\', '/')
            if _eh_arquivo_teste_ou_ignorado(rel_p):
                continue

            try:
                with open(full_p, 'r', encoding='utf-8', errors='replace') as f:
                    conteudo_aux = f.read()
            except Exception:
                continue

            # Skip files with a macro #include (e.g. #include NV_IPC_CONFIG_H) or a `main()` function
            if re.search(r'^\s*#include\s+[A-Z_][A-Z0-9_]*\b', conteudo_aux, flags=re.MULTILINE):
                continue
            sem_coment = re.sub(r'//.*?$|/\*.*?\*/', '', conteudo_aux, flags=re.DOTALL | re.MULTILINE)
            if re.search(r'\b(?:int|void)\s+main\s*\(', sem_coment):
                continue

            stem_aux = os.path.splitext(fname)[0].lower()
            rel_sem_ext = os.path.splitext(rel_p)[0].lower()

            # Criterion 1: the .cpp/.c file matches the included header's path suffix exactly
            if stem_aux in stem_para_caminhos:
                caminhos_esperados = stem_para_caminhos[stem_aux]
                if any(rel_sem_ext.endswith(c_esp) for c_esp in caminhos_esperados):
                    fontes_vinculadas.append(full_p)
                    descricoes_vinculos.append(f"{rel_p} (implementa {stem_aux}.h)")
                    continue

            # Criterion 2: the same specific header in common, resolving a specific function
            # Applied strictly to files of the same subsystem/module (avoids pulling in unrelated symex/solvers/ASTs)
            rel_alvo = os.path.relpath(alvo_abs, repo_dir).replace('\\', '/')
            partes_alvo = [p for p in rel_alvo.split('/') if p]
            sub_alvo = f"{partes_alvo[0]}/{partes_alvo[1]}" if len(partes_alvo) >= 2 and partes_alvo[0] in ('src', 'lib', 'source', 'pkg', 'core') else (partes_alvo[0] if partes_alvo else "")
            partes_aux = [p for p in rel_p.split('/') if p]
            sub_aux = f"{partes_aux[0]}/{partes_aux[1]}" if len(partes_aux) >= 2 and partes_aux[0] in ('src', 'lib', 'source', 'pkg', 'core') else (partes_aux[0] if partes_aux else "")
            mesmo_subsistema = (sub_alvo == sub_aux) if (sub_alvo and sub_aux) else False

            if mesmo_subsistema:
                includes_aux = {os.path.basename(i).lower() for i in re.findall(r'#include\s+["<]([^">]+)[">]', conteudo_aux)} - HEADERS_PADRAO_IGNORADOS
                headers_em_comum = nomes_headers & includes_aux
                if headers_em_comum:
                    defs_aux = set(re.findall(
                        r'(?:^|[;\s])(?<!::)(?:(?:inline|static|virtual|explicit|constexpr|friend)\s+)*(?:void|bool|int|char|size_t|[A-Za-z_][A-Za-z0-9_]*[*&]?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{',
                        sem_coment
                    ))
                    simbolos_resolvidos = (defs_aux & chamadas_alvo) - NOMES_GENERICOS_IGNORADOS
                    if simbolos_resolvidos:
                        fontes_vinculadas.append(full_p)
                        amostra = ", ".join(sorted(simbolos_resolvidos)[:2])
                        descricoes_vinculos.append(f"{rel_p} (resolve {amostra})")

    return fontes_vinculadas[:3], descricoes_vinculos[:3]


# ==============================================================================
# PHASE 2: HEURISTIC DISCOVERY AND PRIORITIZATION OF REPOSITORY MODULES
# ==============================================================================

def classificar_grau_prioridade_modulo(rel_path: str, conteudo: str, linguagem: str) -> Tuple[int, str, int, str]:
    """Classify the file on ESBMC-web's canonical grade matrix (grades 5 to 0),
    generalising the LSVerifier methodology (arXiv:2311.05281) to C, C++ and Python.

    ESBMC-web priority grades:
      - Grade 5: critical memory / pointer / nullability risk (CWE-476, CWE-416, CWE-824)
      - Grade 4: buffer, array and indexing bounds (CWE-119, CWE-120, CWE-787, CWE-125)
      - Grade 3: resource lifetime, allocation and exceptions (CWE-415, CWE-401, CWE-755, CWE-20)
      - Grade 2: concurrency, synchronisation and race conditions (CWE-362, CWE-667, CWE-820)
      - Grade 1: numeric and arithmetic integrity (CWE-369, CWE-190, CWE-191)
      - Grade 0: pure logic, data structures and helper functions

    Returns: (grade, grade_name, numeric_score, reason_summary)
    """
    norm = rel_path.lower()
    motivos: List[str] = []
    grau = 0
    score = 10

    if linguagem == 'python':
        eh_grau5 = ('get_by_id' in conteudo or 'get_attachment' in conteudo or 'is None' in conteudo or 'Optional[' in conteudo)
        eh_grau4 = bool(re.search(r'\[[A-Za-z0-9_]+\]', conteudo) or re.search(r'\[\s*\d+\s*:\s*\d*\s*\]', conteudo))
        eh_grau3 = ('api/' in norm or 'handlers/' in norm or 'views/' in norm or 'routes/' in norm or 'controllers/' in norm or 'get_int_arg' in conteudo or 'abort(' in conteudo or 'raise ' in conteudo or 'try:' in conteudo)
        eh_grau2 = ('async def' in conteudo or 'asyncio' in conteudo or 'Thread(' in conteudo or 'await ' in conteudo)
        eh_grau1 = ('//' in conteudo or '%' in conteudo or 'int(' in conteudo or 'float(' in conteudo)

        if eh_grau5:
            grau = 5
            score = 55
            motivos.append("Nullable/None Dereference")
        elif eh_grau4:
            grau = 4
            score = 45
            motivos.append("Collection Indexing/Bounds")
        elif eh_grau3:
            grau = 3
            score = 35
            motivos.append("API/Input Validation/Exception")
        elif eh_grau2:
            grau = 2
            score = 25
            motivos.append("Async/Concurrency")
        elif eh_grau1:
            grau = 1
            score = 15
            motivos.append("Arithmetic/Casting")
        else:
            grau = 0
            score = 10
            motivos.append("Core Logic")

        if eh_grau3 and "API" not in motivos[0]:
            motivos.append("API/Validation")
        if eh_grau1 and "Arithmetic" not in motivos[0]:
            motivos.append("Arithmetic")

    else:
        eh_grau5 = ('*' in conteudo or '->' in conteudo or 'unique_ptr' in conteudo or 'shared_ptr' in conteudo or 'release()' in conteudo)
        eh_grau4 = ('[' in conteudo and ']' in conteudo) or 'vector<' in conteudo or 'memcpy' in conteudo or 'strcpy' in conteudo or 'sprintf' in conteudo
        eh_grau3 = ('malloc(' in conteudo or 'free(' in conteudo or 'realloc(' in conteudo or 'calloc(' in conteudo or 'new ' in conteudo or 'delete ' in conteudo)
        eh_grau2 = ('pthread_' in conteudo or 'std::thread' in conteudo or 'atomic' in conteudo or 'mutex' in conteudo)
        eh_grau1 = bool(re.search(r'[\/%]', conteudo) or '<<' in conteudo or '>>' in conteudo or 'BigInt' in conteudo)

        if eh_grau5:
            grau = 5
            score = 55
            motivos.append("Raw/Smart Pointers")
        elif eh_grau4:
            grau = 4
            score = 45
            motivos.append("Array/Buffer Bounds")
        elif eh_grau3:
            grau = 3
            score = 35
            motivos.append("Dynamic Memory/RAII")
        elif eh_grau2:
            grau = 2
            score = 25
            motivos.append("Concurrency/Threads")
        elif eh_grau1:
            grau = 1
            score = 15
            motivos.append("Arithmetic/Shift")
        else:
            grau = 0
            score = 10
            motivos.append("Base Logic")

        if 'main(' in conteudo:
            score += 5
            motivos.append("Main Entrypoint")
        if eh_grau4 and "Array" not in motivos[0]:
            motivos.append("Array/Bounds")
        if eh_grau3 and "Dynamic" not in motivos[0]:
            motivos.append("Dynamic Memory")
        if eh_grau1 and "Arithmetic" not in motivos[0]:
            motivos.append("Arithmetic")

    NOMES_GRAUS = {
        5: "Critical Memory / Nullability Risk (CWE-476, CWE-416)",
        4: "Buffer Bounds and Indexing (CWE-119, CWE-787)",
        3: "Resource Lifecycle and Exceptions (CWE-415, CWE-755)",
        2: "Concurrency and Synchronisation (CWE-362, CWE-667)",
        1: "Numeric and Arithmetic Integrity (CWE-369, CWE-190)",
        0: "Pure Logic and Helper Functions"
    }
    nome_grau = NOMES_GRAUS.get(grau, "General Logic")
    resumo_motivos = ", ".join(motivos[:3]) if motivos else "General Module"

    return grau, nome_grau, score, resumo_motivos


def calcular_score_criticidade_modulo(rel_path: str, conteudo: str, linguagem: str) -> Tuple[int, str]:
    """Compute a file's formal criticality score to prioritise exploration."""
    grau, nome_grau, score, resumo = classificar_grau_prioridade_modulo(rel_path, conteudo, linguagem)
    return score, f"Grade {grau} ({nome_grau}) | {resumo}"


def descobrir_alvos_verificaveis_repositorio(
    repo_dir: str,
    linguagem: str,
    filtro_subpasta: str = "",
    max_arquivos: int = 8,
    modo_suite_profissional: bool = False
) -> List[Dict[str, object]]:
    """Walk every directory of the repository, keep the verifiable modules of the selected
    language (or C, C++ and Python together when linguagem='all'), support test-suite
    orchestrators (verify.py, run_checks.sh), extract oracle directives (expected verdict),
    and return the targets stratified and prioritised."""
    if linguagem in ('all', 'polyglot', 'auto'):
        extensoes = ('.py', '.c', '.cpp', '.cc', '.cxx')
    elif linguagem == 'python':
        extensoes = ('.py',)
    elif linguagem == 'c':
        extensoes = ('.c',)
    else:
        extensoes = ('.cpp', '.cc', '.cxx')

    candidatos = []
    lang_counts: Dict[str, int] = {'c': 0, 'cpp': 0, 'python': 0}

    # 1. Parse orchestrators and manifests in the repository (vLLM, AWS-Neuron, UNIFEI style)
    manifesto_orquestrador = _extrair_manifesto_orquestrador(repo_dir)

    filtro_norm = filtro_subpasta.strip().strip('/\\').replace('\\', '/').lower()
    # If the filter names an exact file (e.g. api/channels_api.py), use its parent directory as the folder filter
    if filtro_norm.endswith(('.py', '.c', '.cpp', '.h', '.hpp')) and '/' in filtro_norm:
        filtro_norm = os.path.dirname(filtro_norm)
    elif filtro_norm.endswith(('.py', '.c', '.cpp', '.h', '.hpp')):
        filtro_norm = ""

    partes_filtro = [p for p in filtro_norm.split('/') if p]
    eh_pasta_harness = any(p in PASTAS_HARNESS_PROFISSIONAIS for p in partes_filtro)
    incluir_testes = (max_arquivos == -1) or modo_suite_profissional or eh_pasta_harness

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_SISTEMA and not d.startswith('.')]
        for fname in filenames:
            if not fname.endswith(extensoes):
                continue
            full_p = os.path.join(dirpath, fname)
            rel_p = os.path.relpath(full_p, repo_dir).replace('\\', '/')
            if _eh_arquivo_teste_ou_ignorado(rel_p, incluir_testes=incluir_testes):
                continue
            if filtro_norm:
                rel_p_lower = rel_p.lower()
                caminho_com_barras = f"/{rel_p_lower}"
                filtro_com_barra_inicial = f"/{filtro_norm}"
                filtro_com_barras = f"/{filtro_norm}/"
                match_prefixo = rel_p_lower.startswith(filtro_norm)
                match_subpasta = (filtro_com_barras in caminho_com_barras) or (filtro_com_barra_inicial in caminho_com_barras)
                if not (match_prefixo or match_subpasta):
                    continue

            if fname.endswith('.py'):
                lang_arq = 'python'
            elif fname.endswith('.c'):
                lang_arq = 'c'
            else:
                lang_arq = 'cpp'

            try:
                with open(full_p, 'r', encoding='utf-8', errors='replace') as f:
                    conteudo = f.read()
                if len(conteudo.strip()) < 20:
                    continue
                if lang_arq == 'python':
                    ast.parse(conteudo)
            except Exception:
                continue

            lang_counts[lang_arq] = lang_counts.get(lang_arq, 0) + 1
            grau, nome_grau, score, resumo_m = classificar_grau_prioridade_modulo(rel_p, conteudo, lang_arq)
            dir_rel = os.path.dirname(rel_p) or "(root)"
            motivos_lista = [m.strip() for m in resumo_m.split(',') if m.strip()] or ["Core Module"]

            # Extract directives embedded in the code's header
            exp_dir, flags_dir = _extrair_diretivas_do_arquivo(conteudo)

            # Look up the orchestrator manifest
            info_orq = manifesto_orquestrador.get(rel_p.lower()) or manifesto_orquestrador.get(os.path.basename(rel_p).lower())
            exp_orq = info_orq.get('expected_verdict') if info_orq else None
            flags_orq = info_orq.get('custom_flags') if info_orq else []

            expected_verdict = exp_dir or exp_orq
            custom_flags = flags_dir or flags_orq
            partes_rel_p = rel_p.lower().split('/')
            eh_harness = (
                any(p in PASTAS_HARNESS_PROFISSIONAIS for p in partes_rel_p)
                or ('test' in partes_rel_p[-1])
                or ('harness' in partes_rel_p[-1])
                or ('assert' in conteudo)
                or ('__ESBMC_assert' in conteudo)
            )

            oraculo_origem = "Directives" if exp_dir else (info_orq.get('source') if (info_orq and exp_orq) else None)

            if expected_verdict:
                score += 25
                motivos_lista.append(f"Oracle: {expected_verdict.replace('VERIFICATION ', '')}")
            if eh_harness:
                score += 10
                if "Formal Testbed" not in motivos_lista:
                    motivos_lista.append("Formal Testbed/Harness")

            candidatos.append({
                'rel_path': rel_p,
                'dir': dir_rel,
                'lang': lang_arq,
                'abs_path': full_p,
                'full_path': full_p,
                'grau': grau,
                'nome_grau': nome_grau,
                'score': score,
                'categoria': f"Grade {grau}: {nome_grau}",
                'motivos': motivos_lista,
                'conteudo': conteudo,
                'is_harness': eh_harness,
                'expected_verdict': expected_verdict,
                'custom_flags': custom_flags,
                'oraculo_origem': oraculo_origem
            })

    # Two-level stratified round-robin:
    # Level 1: language ('c', 'cpp', 'python') -> ensures ALL of the repository's languages are verified!
    # Level 2: directory ('dir') within each language -> ensures every folder is covered!
    todos_diretorios = {str(c['dir']) for c in candidatos}
    filas_por_linguagem: Dict[str, List[Dict[str, object]]] = {}

    for lang_k in ('c', 'cpp', 'python'):
        cands_lang = [c for c in candidatos if c['lang'] == lang_k]
        if not cands_lang:
            continue
        por_dir_lang: Dict[str, List[Dict[str, object]]] = {}
        for c in cands_lang:
            por_dir_lang.setdefault(str(c['dir']), []).append(c)
        for d_k in por_dir_lang:
            por_dir_lang[d_k].sort(key=lambda x: (-int(x['score']), str(x['rel_path'])))
        dirs_ord = sorted(por_dir_lang.keys(), key=lambda d: (-int(por_dir_lang[d][0]['score']), d))

        fila_lang: List[Dict[str, object]] = []
        r_dir = 0
        while len(fila_lang) < len(cands_lang):
            prog = False
            for d_k in dirs_ord:
                if r_dir < len(por_dir_lang[d_k]):
                    fila_lang.append(por_dir_lang[d_k][r_dir])
                    prog = True
            if not prog:
                break
            r_dir += 1
        filas_por_linguagem[lang_k] = fila_lang

    selecionados: List[Dict[str, object]] = []
    limite = len(candidatos) if (not max_arquivos or max_arquivos <= 0) else max_arquivos
    langs_ativas = [lk for lk in ('c', 'cpp', 'python') if lk in filas_por_linguagem]
    indices_lang = {lk: 0 for lk in langs_ativas}

    while len(selecionados) < limite and langs_ativas:
        adicionou = False
        for lk in langs_ativas:
            idx_l = indices_lang[lk]
            fila_l = filas_por_linguagem[lk]
            if idx_l < len(fila_l):
                item = fila_l[idx_l]
                indices_lang[lk] += 1
                item['total_repo_files'] = len(candidatos)
                item['total_repo_dirs'] = len(todos_diretorios)
                item['lang_counts'] = dict(lang_counts)
                selecionados.append(item)
                adicionou = True
                if len(selecionados) >= limite:
                    break
        if not adicionou:
            break

    return selecionados


# Compatibility alias
descubrir_alvos_verificaveis_repositorio = descobrir_alvos_verificaveis_repositorio


