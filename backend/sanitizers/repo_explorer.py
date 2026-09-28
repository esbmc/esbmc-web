#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESBMC Repository Explorer & Inter-Directory Dependency Slicer (RepoSlice-BMC)
Desenvolvido para Dissertação de Mestrado (UFAM).

Algoritmo em 4 Fases para Exploração e Verificação Formal de Repositórios Multi-Diretórios:
  - Fase 1 (Repository Crawler & Symbol Graph): Varre recursivamente os diretórios do repositório
    construindo o Grafo de Símbolos Globais (Funções, Classes, Headers e Módulos Internos).
  - Fase 2 (Heuristic Target Prioritization): Classifica e ordena os módulos verificáveis por
    criticidade simbólica (entrypoints, handlers HTTP, manipulação de memória/ponteiros, aritmética).
  - Fase 3 (Inter-Directory Dependency Slicing): Realiza a fusão (inlining de AST em Python e
    resolução cruzada de unidades de tradução em C/C++) das dependências que pertencem a outras
    pastas do mesmo repositório, isolando apenas a fronteira externa para sanitização simbólica.
  - Fase 4 (Batch Bounded Model Checking & CWE Aggregation): Executa o ESBMC com controle de
    recursos por módulo e consolida as provas formais (SAFE) e contraexemplos (CWEs).
"""

import ast
import os
import re
from typing import Dict, List, Set, Tuple, Optional


PASTAS_IGNORADAS = {
    '.git', '.github', '.vscode', '__pycache__', 'node_modules', 'venv', '.venv',
    'env', 'build', 'dist', 'docs', 'doc', 'migrations', 'static', 'templates',
    'assets', 'vendor', 'third_party', 'extern', 'external', 'cmake',
    'regression', 'unit', 'disabled', 'benchmarks', 'benchmark'
}


def _eh_arquivo_teste_ou_ignorado(rel_path: str, incluir_testes: bool = False) -> bool:
    norm = rel_path.replace('\\', '/').lower()
    partes = norm.split('/')
    if any(p in PASTAS_IGNORADAS or p.startswith('.') for p in partes[:-1]):
        return True
    fname = partes[-1]
    if fname in ('__init__.py', 'setup.py', 'conftest.py', 'manage.py', 'wsgi.py', 'asgi.py'):
        return True
    if fname.startswith(('esbmc_', 'sanitized_', 'codigo_esbmc', 'modulo_')):
        return True
    if not incluir_testes:
        if fname.endswith(('_test.py', '_tests.py', '_test.cpp', '_test.c', 'test.cpp', 'test.c')):
            return True
        if fname.startswith(('test_', 'tests_')):
            return True
        if 'test/' in norm or 'tests/' in norm or 'testing/' in norm:
            return True
    return False


# ==============================================================================
# FASE 1 & 3 (PYTHON): GRAFO DE SÍMBOLOS E FUSÃO INTER-DIRETÓRIOS DE AST
# ==============================================================================

def construir_indice_python_repositorio(repo_dir: str) -> Dict[str, object]:
    """Constrói o Grafo de Símbolos Python de todas as pastas do repositório."""
    mapa_modulos: Dict[str, str] = {}
    mapa_funcoes: Dict[str, Tuple[str, ast.AST]] = {}
    mapa_classes: Dict[str, Tuple[str, ast.ClassDef]] = {}

    if not repo_dir or not os.path.isdir(repo_dir):
        return {'modulos': mapa_modulos, 'funcoes': mapa_funcoes, 'classes': mapa_classes}

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS and not d.startswith('.')]
        for fname in filenames:
            if not fname.endswith('.py'):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, repo_dir).replace('\\', '/')
            if _eh_arquivo_teste_ou_ignorado(rel_path):
                continue

            mod_dot = os.path.splitext(rel_path)[0].replace('/', '.')
            mod_base = os.path.splitext(fname)[0]
            mapa_modulos[mod_dot] = full_path
            mapa_modulos[mod_base] = full_path

            try:
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    source = f.read()
                tree = ast.parse(source)
                for stmt in tree.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not stmt.name.startswith('__') and stmt.name != 'main':
                            mapa_funcoes[stmt.name] = (rel_path, stmt)
                    elif isinstance(stmt, ast.ClassDef):
                        mapa_classes[stmt.name] = (rel_path, stmt)
            except Exception:
                continue

    return {
        'modulos': mapa_modulos,
        'funcoes': mapa_funcoes,
        'classes': mapa_classes
    }


def fundir_dependencias_internas_python(
    codigo_alvo: str,
    repo_dir: str,
    caminho_rel_alvo: str = "",
    indice_precalculado: Optional[Dict[str, object]] = None
) -> Tuple[str, List[str]]:
    """Analisa a AST do arquivo Python alvo, identifica chamadas a funções e classes
    definidas em OUTROS diretórios do mesmo repositório Git e realiza o Inlining de AST
    (Fatiamento Inter-Modular) antes da passagem do Homogenizer v2.0.

    Retorna: (codigo_com_dependencias_fundidas, lista_de_simbolos_fundidos)
    """
    try:
        arvore_alvo = ast.parse(codigo_alvo)
    except SyntaxError:
        return codigo_alvo, []

    indice = indice_precalculado or construir_indice_python_repositorio(repo_dir)
    mapa_funcoes: Dict[str, Tuple[str, ast.AST]] = indice.get('funcoes', {})  # type: ignore
    mapa_classes: Dict[str, Tuple[str, ast.ClassDef]] = indice.get('classes', {})  # type: ignore

    definidos_no_alvo: Set[str] = set()
    for stmt in arvore_alvo.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definidos_no_alvo.add(stmt.name)

    nomes_referenciados: Set[str] = set()
    atributos_chamados: Set[str] = set()

    for node in ast.walk(arvore_alvo):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            nomes_referenciados.add(node.id)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                nomes_referenciados.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                atributos_chamados.add(node.func.attr)

    candidatos = (nomes_referenciados | atributos_chamados) - definidos_no_alvo
    nos_injetados: List[ast.stmt] = []
    simbolos_fundidos: List[str] = []

    rel_norm = caminho_rel_alvo.replace('\\', '/') if caminho_rel_alvo else ""

    # Injeta até 6 funções/classes internas de outros diretórios do repositório
    for simb in sorted(candidatos):
        if len(nos_injetados) >= 6:
            break
        if simb in mapa_funcoes:
            origem_rel, fn_node = mapa_funcoes[simb]
            if origem_rel != rel_norm:
                nos_injetados.append(fn_node)
                simbolos_fundidos.append(f"{simb}() [{origem_rel}]")
                definidos_no_alvo.add(simb)
        elif simb in mapa_classes:
            origem_rel, cls_node = mapa_classes[simb]
            if origem_rel != rel_norm:
                nos_injetados.append(cls_node)
                simbolos_fundidos.append(f"class {simb} [{origem_rel}]")
                definidos_no_alvo.add(simb)

    if not nos_injetados:
        return codigo_alvo, []

    # Insere as definições importadas de outros diretórios do repositório no início da AST
    arvore_alvo.body = nos_injetados + arvore_alvo.body
    ast.fix_missing_locations(arvore_alvo)
    try:
        codigo_fundido = ast.unparse(arvore_alvo)
        return codigo_fundido, simbolos_fundidos
    except Exception:
        return codigo_alvo, []


# ==============================================================================
# FASE 1 & 3 (C / C++): GRAFO DE UNIDADES DE TRADUÇÃO INTER-DIRETÓRIOS
# ==============================================================================

def resolver_fontes_dependentes_cpp(caminho_alvo: str, repo_dir: str) -> Tuple[List[str], List[str]]:
    """Constrói o grafo de símbolos C/C++ através dos subdiretórios do repositório e descobre
    quais arquivos `.cpp`/`.c` de outras pastas implementam as funções/classes declaradas nos
    headers incluídos pelo arquivo alvo.

    Retorna: (lista_caminhos_cpp_dependentes, lista_descricoes_vinculos)
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
        'make_true', 'make_false', 'make_nil',
        'diff', 'compare', 'equal', 'check', 'test', 'match', 'clone', 'copy', 'swap',
        'dump', 'show', 'display', 'validate', 'verify'
    }

    includes_brutos = re.findall(r'#include\s+["<]([^">]+)[">]', codigo_alvo)
    includes_alvo = [inc.replace('\\', '/').strip() for inc in includes_brutos if os.path.basename(inc).lower() not in HEADERS_PADRAO_IGNORADOS]
    if not includes_alvo:
        return [], []

    nomes_headers = {os.path.basename(inc).lower() for inc in includes_alvo}
    stem_para_caminhos: Dict[str, Set[str]] = {}
    for inc in includes_alvo:
        stem_inc = os.path.splitext(os.path.basename(inc))[0].lower()
        sem_ext = os.path.splitext(inc)[0].lower()
        stem_para_caminhos.setdefault(stem_inc, set()).add(sem_ext)

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

            # Ignora arquivos que tenham #include via macro (ex: #include NV_IPC_CONFIG_H) ou função `main()`
            if re.search(r'^\s*#include\s+[A-Z_][A-Z0-9_]*\b', conteudo_aux, flags=re.MULTILINE):
                continue
            sem_coment = re.sub(r'//.*?$|/\*.*?\*/', '', conteudo_aux, flags=re.DOTALL | re.MULTILINE)
            if re.search(r'\b(?:int|void)\s+main\s*\(', sem_coment):
                continue

            stem_aux = os.path.splitext(fname)[0].lower()
            rel_sem_ext = os.path.splitext(rel_p)[0].lower()

            # Critério 1: O arquivo .cpp/.c corresponde exatamente ao sufixo de caminho do header incluído
            if stem_aux in stem_para_caminhos:
                caminhos_esperados = stem_para_caminhos[stem_aux]
                if any(rel_sem_ext.endswith(c_esp) for c_esp in caminhos_esperados):
                    fontes_vinculadas.append(full_p)
                    descricoes_vinculos.append(f"{rel_p} (implementa {stem_aux}.h)")
                    continue

            # Critério 2: Mesmo header específico em comum resolvendo função específica
            # Aplicado estritamente para arquivos do mesmo subsistema/módulo (evita puxar symex/solvers/ASTs não relacionados)
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
                    defs_aux = set(re.findall(r'(?<!::)\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*\{', sem_coment))
                    simbolos_resolvidos = (defs_aux & chamadas_alvo) - NOMES_GENERICOS_IGNORADOS
                    if simbolos_resolvidos:
                        fontes_vinculadas.append(full_p)
                        amostra = ", ".join(sorted(simbolos_resolvidos)[:2])
                        descricoes_vinculos.append(f"{rel_p} (resolve {amostra})")

    return fontes_vinculadas[:3], descricoes_vinculos[:3]


# ==============================================================================
# FASE 2: DESCOBERTA E PRIORIZAÇÃO HEURÍSTICA DE MÓDULOS DO REPOSITÓRIO
# ==============================================================================

def calcular_score_criticidade_modulo(rel_path: str, conteudo: str, linguagem: str) -> Tuple[int, str]:
    """Calcula a pontuação de criticidade formal de um arquivo para priorizar a exploração."""
    score = 10
    motivos = []
    norm = rel_path.lower()

    if linguagem == 'python':
        if 'api/' in norm or 'handlers/' in norm or 'views/' in norm or 'routes/' in norm or 'controllers/' in norm:
            score += 40
            motivos.append("API/Handler")
        if 'get_int_arg' in conteudo or 'abort(' in conteudo:
            score += 30
            motivos.append("Input Validation")
        if 'get_by_id' in conteudo or 'get_attachment' in conteudo or 'is None' in conteudo:
            score += 20
            motivos.append("Nullable Entity")
        if 'raise ' in conteudo or 'try:' in conteudo:
            score += 15
            motivos.append("Exception Flow")
        if '//' in conteudo or '%' in conteudo or '+' in conteudo:
            score += 10
            motivos.append("Arithmetic")
    else:
        if 'main(' in conteudo:
            score += 35
            motivos.append("Main Entrypoint")
        if 'malloc(' in conteudo or 'free(' in conteudo or 'new ' in conteudo or 'delete ' in conteudo:
            score += 30
            motivos.append("Dynamic Memory")
        if '[' in conteudo and ']' in conteudo:
            score += 20
            motivos.append("Array/Bounds")
        if '*' in conteudo or '->' in conteudo:
            score += 15
            motivos.append("Pointers")

    resumo = ", ".join(motivos[:3]) if motivos else "Core Module"
    return score, resumo


def descobrir_alvos_verificaveis_repositorio(
    repo_dir: str,
    linguagem: str,
    filtro_subpasta: str = "",
    max_arquivos: int = 8
) -> List[Dict[str, object]]:
    """Varre todos os diretórios do repositório, filtra os módulos verificáveis da linguagem
    selecionada (ou todas as linguagens C, C++ e Python simultaneamente quando linguagem='all'),
    calcula o score heurístico de criticidade e retorna os alvos de forma estratificada."""
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

    filtro_norm = filtro_subpasta.strip().strip('/\\').replace('\\', '/').lower()
    # Se o filtro apontar para um arquivo exato (ex: api/channels_api.py), usa o diretório pai dele como filtro de pasta
    if filtro_norm.endswith(('.py', '.c', '.cpp', '.h', '.hpp')) and '/' in filtro_norm:
        filtro_norm = os.path.dirname(filtro_norm)
    elif filtro_norm.endswith(('.py', '.c', '.cpp', '.h', '.hpp')):
        filtro_norm = ""

    incluir_testes = (max_arquivos == -1)
    for dirpath, dirnames, filenames in os.walk(repo_dir):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS and not d.startswith('.')]
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
                if len(conteudo.strip()) < 30:
                    continue
                if lang_arq == 'python':
                    ast.parse(conteudo)
            except Exception:
                continue

            lang_counts[lang_arq] = lang_counts.get(lang_arq, 0) + 1
            score, categoria = calcular_score_criticidade_modulo(rel_p, conteudo, lang_arq)
            dir_rel = os.path.dirname(rel_p) or "(root)"
            motivos_lista = [m.strip() for m in categoria.split(',') if m.strip()] or ["Core Module"]
            candidatos.append({
                'rel_path': rel_p,
                'dir': dir_rel,
                'lang': lang_arq,
                'abs_path': full_p,
                'full_path': full_p,
                'score': score,
                'categoria': categoria,
                'motivos': motivos_lista,
                'conteudo': conteudo
            })

    # Round-Robin Estratificado em Dois Níveis:
    # Nível 1: Linguagem ('c', 'cpp', 'python') -> garante que TODAS as linguagens do repositório sejam verificadas!
    # Nível 2: Diretório ('dir') dentro de cada linguagem -> garante cobertura de todas as pastas!
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


# Alias de compatibilidade
descubrir_alvos_verificaveis_repositorio = descobrir_alvos_verificaveis_repositorio


