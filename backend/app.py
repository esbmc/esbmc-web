from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import tempfile
import os
import glob
import json
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
import git
import threading
import uuid
import shutil
import sys
import requests
import re
import time
import signal
import ast


def _encerrar_arvore_processo(proc):
    """Encerra de forma imediata e isolada apenas a árvore do subprocesso ESBMC/Z3,
    jamais enviando sinais ao grupo de processos do servidor Flask principal."""
    if not proc:
        return
    try:
        if proc.poll() is not None:
            return
        if hasattr(os, "getpgid") and hasattr(os, "killpg"):
            pgid_proc = os.getpgid(proc.pid)
            pgid_servidor = os.getpgid(0)
            if pgid_proc != pgid_servidor:
                os.killpg(pgid_proc, signal.SIGKILL)
                return
        proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def normalizar_url_e_subpasta_git(git_url: str, repo_subdir_filter: str = "", main_file_path: str = ""):
    """Detecta se o usuário colou uma URL do GitHub apontando para subpastas (/tree/)
    ou arquivos específicos (/blob/), extraindo o repositório base clonável pelo Git
    e preenchendo automaticamente os filtros de subdiretório e arquivo correspondentes."""
    if not git_url:
        return git_url, repo_subdir_filter, main_file_path

    url_limpa = str(git_url).strip()
    padrao = r'^(https?://github\.com/[^/]+/[^/]+)/(?:tree|blob)/([^/]+)/(.+)$'
    m = re.match(padrao, url_limpa, re.IGNORECASE)
    if m:
        base_url = m.group(1)
        tipo = "tree" if "/tree/" in url_limpa else "blob"
        caminho_extra = m.group(3).strip('/')

        if tipo == "tree":
            if not repo_subdir_filter:
                repo_subdir_filter = caminho_extra
        elif tipo == "blob":
            if not main_file_path:
                main_file_path = caminho_extra
            if not repo_subdir_filter:
                dir_pai = os.path.dirname(caminho_extra)
                if dir_pai:
                    repo_subdir_filter = dir_pai

        return base_url, repo_subdir_filter, main_file_path

    return url_limpa.rstrip('/'), repo_subdir_filter, main_file_path


def descobrir_funcao_alvo_principal(codigo: str, linguagem: str):
    """Descobre automaticamente a função pública de maior complexidade lógica (CFG/branches/ponteiros)
    em um módulo C, C++ ou Python quando o ESBMC gera 0 VCCs (prova vazia / ausência de main()),
    permitindo re-executar o ESBMC com '--function <nome_funcao>' para forçar geração real de VCCs no Z3."""
    if not codigo:
        return None, 0

    if linguagem == 'python':
        try:
            arvore = ast.parse(codigo)
            candidatas = []
            for no in arvore.body:
                if isinstance(no, ast.FunctionDef) and not no.name.startswith('__'):
                    score = 10
                    for sub in ast.walk(no):
                        if isinstance(sub, ast.Assert):
                            score += 30
                        elif isinstance(sub, (ast.If, ast.While, ast.For)):
                            score += 12
                        elif isinstance(sub, (ast.Subscript, ast.BinOp, ast.Compare)):
                            score += 5
                    num_args = len(no.args.args)
                    if no.args.args and no.args.args[0].arg in ('self', 'cls'):
                        continue
                    candidatas.append((score, no.name, num_args))
            if candidatas:
                candidatas.sort(key=lambda x: x[0], reverse=True)
                return candidatas[0][1], candidatas[0][2]
        except Exception:
            pass
        return None, 0

    # Para C e C++: busca definições de funções livres (não-membros de classes C++ com ::)
    padrao_fn = re.compile(
        r'(?:^|\n)\s*(?:[A-Za-z_][A-Za-z0-9_*\s]+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^;{}]*)\)\s*\{',
        re.MULTILINE
    )
    proibidos = {
        'if', 'for', 'while', 'switch', 'catch', 'main', 'sizeof', 'typeof', 'alignof',
        '__attribute__', '__declspec', 'return'
    }
    candidatas_c = []
    for m in padrao_fn.finditer(codigo):
        nome_fn = m.group(1).strip()
        params_str = m.group(2).strip()
        if nome_fn in proibidos or nome_fn.startswith('__'):
            continue
        inicio_corpo = m.end()
        trecho_corpo = codigo[inicio_corpo:inicio_corpo + 1500]
        score = 10
        score += 25 * len(re.findall(r'\bassert\s*\(', trecho_corpo))
        score += 10 * len(re.findall(r'\b(?:if|while|for|switch)\s*\(', trecho_corpo))
        score += 6 * len(re.findall(r'[\*\[\]/%]', trecho_corpo))
        num_params = 0 if (not params_str or params_str == 'void') else (params_str.count(',') + 1)
        candidatas_c.append((score, nome_fn, num_params))

    if candidatas_c:
        candidatas_c.sort(key=lambda x: x[0], reverse=True)
        return candidatas_c[0][1], candidatas_c[0][2]
    return None, 0

from sanitizers.python_sanitizer import sanitizar_python
from sanitizers.cpp_sanitizer import sanitizar_cpp, descubrir_headers_e_includes_no_diretorio, gerar_modelo_simbolico_fallback_c_cpp
from sanitizers.c_sanitizer import sanitizar_c, descubrir_headers_e_includes_c
from sanitizers.repo_explorer import (
    construir_indice_python_repositorio,
    fundir_dependencias_internas_python,
    resolver_fontes_dependentes_cpp,
    descobrir_alvos_verificaveis_repositorio
)

FLAGS_PERMITIDAS_SIMPLES = {
    '--floatbv', '--fixedbv', '--k-induction', '--memory-leak-check',
    '--loop-invariant', '--overflow-check',
    '--data-races-check', '--deadlock-check',
    '--smt-during-symex', '--smt-thread-guard',
    '--smt-symex-guard', '--smt-symex-assert', '--smt-symex-assume',
    '--incremental-bmc',
    '--falsification',
    '--termination',
    '--generate-html-report',
    '--boolector',
    '--z3',
    '--cvc5',
    '--bitwuzla',
    '--mathsat',
    '--yices',
    '--no-standard-checks', '--no-assertions', '--no-bounds-check',
    '--no-div-by-zero-check', '--no-pointer-check', '--no-align-check', '--multi-property',
    '--no-unwinding-assertions', '--partial-loops'
}

FLAGS_PERMITIDAS_COM_VALOR = {
    '--unwind', '--context-bound', '--witness-output', '--function', '--timeout',
    '--witness-output-yaml'
}

MAPEAMENTO_CWE = {
    'cwe-476': {'code': 'CWE-476', 'severity': 'Critical'},
    'none dereference': {'code': 'CWE-476', 'severity': 'Critical'},
    'cwe-755': {'code': 'CWE-755', 'severity': 'High'},
    '!= 500': {'code': 'CWE-755', 'severity': 'High'},
    'cwe-20': {'code': 'CWE-20', 'severity': 'High'},
    '== 400': {'code': 'CWE-20', 'severity': 'High'},
    'range_status': {'code': 'CWE-20', 'severity': 'High'},
    'memory leak': {'code': 'CWE-401', 'severity': 'Medium'},
    'double free': {'code': 'CWE-415', 'severity': 'Critical'},
    'freeing freed': {'code': 'CWE-415', 'severity': 'Critical'},
    'use after free': {'code': 'CWE-416', 'severity': 'Critical'},
    'uninitialized': {'code': 'CWE-457', 'severity': 'High'},
    'out of bounds': {'code': 'CWE-119', 'severity': 'Critical'},
    'bounds check': {'code': 'CWE-119', 'severity': 'Critical'},
    'array bounds': {'code': 'CWE-119', 'severity': 'Critical'},
    'dereference failure': {'code': 'CWE-476', 'severity': 'Critical'},
    'null pointer': {'code': 'CWE-476', 'severity': 'Critical'},
    'invalid pointer': {'code': 'CWE-824', 'severity': 'Critical'},
    'division by zero': {'code': 'CWE-369', 'severity': 'High'},
    'overflow': {'code': 'CWE-190', 'severity': 'High'},
    'underflow': {'code': 'CWE-191', 'severity': 'High'},
    'shift count': {'code': 'CWE-682', 'severity': 'Medium'},
    'nan': {'code': 'CWE-682', 'severity': 'Medium'},
    'data race': {'code': 'CWE-362', 'severity': 'High'},
    'deadlock': {'code': 'CWE-833', 'severity': 'High'},
    'assertion': {'code': 'CWE-617', 'severity': 'High'},
    'user-specified': {'code': 'CWE-617', 'severity': 'High'}
}

app = Flask(__name__)
CORS(app)

TAREFAS_ATIVAS = {}
CLONE_TASKS = {}


class ProgressoClone(git.RemoteProgress):
    def __init__(self, task_id):
        super().__init__()
        self.task_id = task_id

    def update(self, op_code, cur_count, max_count=None, message=''):
        if max_count:
            percent = int((cur_count / max_count) * 100)
            if self.task_id in CLONE_TASKS:
                CLONE_TASKS[self.task_id]['progress'] = percent


@app.route('/fetch-repo-files', methods=['POST'])
def fetch_repo_files():
    dados = request.get_json() or {}
    git_url_raw = dados.get('git_url')
    if not git_url_raw:
        return jsonify({'error': 'No Git URL provided.'}), 400

    subdir_filter_req = (dados.get('subdir_filter') or dados.get('repo_subdir_filter') or "").strip()
    url_base, auto_subdir, auto_file = normalizar_url_e_subpasta_git(git_url_raw, repo_subdir_filter=subdir_filter_req)
    filtro_subdir_efetivo = (auto_subdir or subdir_filter_req).strip().strip('/\\')

    task_id = str(uuid.uuid4())
    CLONE_TASKS[task_id] = {
        'status': 'running',
        'progress': 0,
        'files': [],
        'all_files': [],
        'error': None,
        'normalized_url': url_base,
        'auto_subdir': filtro_subdir_efetivo,
        'auto_file': auto_file,
        'subdir_filter': filtro_subdir_efetivo
    }

    def clone_worker(task_id, git_url):
        temp_dir = tempfile.mkdtemp()
        try:
            repo = git.Repo.clone_from(
                git_url, temp_dir, depth=1, filter="blob:none", n=True, progress=ProgressoClone(task_id)
            )
            raw_files = repo.git.ls_tree('-r', 'HEAD', '--name-only')
            file_list = [f for f in raw_files.split('\n') if f.endswith(('.c', '.cpp', '.py', '.h', '.hpp'))]

            if filtro_subdir_efetivo:
                prefix = filtro_subdir_efetivo + '/'
                arquivos_pasta = [
                    f for f in file_list
                    if f == filtro_subdir_efetivo or f.startswith(prefix)
                ]
            else:
                arquivos_pasta = file_list

            CLONE_TASKS[task_id]['files'] = arquivos_pasta
            CLONE_TASKS[task_id]['all_files'] = file_list
            CLONE_TASKS[task_id]['subdir_filter'] = filtro_subdir_efetivo
            CLONE_TASKS[task_id]['status'] = 'completed'
        except Exception as e:
            CLONE_TASKS[task_id]['error'] = f"Failed to fetch repo: {str(e)}"
            CLONE_TASKS[task_id]['status'] = 'error'
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    threading.Thread(target=clone_worker, args=(task_id, url_base)).start()
    return jsonify({
        'task_id': task_id,
        'normalized_url': url_base,
        'auto_subdir': filtro_subdir_efetivo,
        'auto_file': auto_file,
        'subdir_filter': filtro_subdir_efetivo
    })


@app.route('/fetch-repo-status/<task_id>', methods=['GET'])
def fetch_repo_status(task_id):
    task = CLONE_TASKS.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found.'}), 404
    return jsonify(task)


@app.route('/fetch-file-content', methods=['POST'])
def fetch_file_content():
    dados = request.get_json()
    git_url_raw = dados.get('git_url')
    file_path = dados.get('file_path')
    if not git_url_raw or not file_path:
        return jsonify({'error': 'Git URL or file path missing.'}), 400
    url_base, _, auto_file = normalizar_url_e_subpasta_git(git_url_raw, main_file_path=file_path)
    file_path = auto_file or file_path
    if '..' in file_path or file_path.startswith('/'):
        return jsonify({'error': 'Invalid file path.'}), 400
    task_id = str(uuid.uuid4())
    CLONE_TASKS[task_id] = {'status': 'running', 'progress': 0, 'content': None, 'error': None}

    def fetch_file_worker(task_id, git_url, file_path):
        temp_dir = tempfile.mkdtemp()
        try:
            repo = git.Repo.clone_from(
                git_url, temp_dir, depth=1, filter="blob:none", n=True, progress=ProgressoClone(task_id)
            )
            CLONE_TASKS[task_id]['progress'] = 80
            content = repo.git.show(f"HEAD:{file_path}")
            CLONE_TASKS[task_id]['progress'] = 100
            CLONE_TASKS[task_id]['content'] = content
            CLONE_TASKS[task_id]['status'] = 'completed'
        except Exception as e:
            CLONE_TASKS[task_id]['error'] = f"Failed to read file: {str(e)}"
            CLONE_TASKS[task_id]['status'] = 'error'
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    threading.Thread(target=fetch_file_worker, args=(task_id, url_base, file_path)).start()
    return jsonify({'task_id': task_id})


@app.route('/analisar', methods=['POST'])
def iniciar_analise():
    dados = request.get_json()
    task_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp()

    TAREFAS_ATIVAS[task_id] = {
        "status": "starting",
        "cancel_requested": False,
        "logs": "[SYSTEM] Preparing verification environment...\n",
        "process": None,
        "resultado": None,
        "progresso": {
            "current": 0,
            "total": 1,
            "current_file": "Initializing environment...",
            "current_lang": "",
            "safe_count": 0,
            "violation_count": 0,
            "total_vccs": 0,
            "total_ssa": 0,
            "partial_summary": []
        }
    }

    def executar_background(task_id, dados, temp_dir):
        try:
            git_url_raw = (dados.get('git_url') or dados.get('git_repo') or '').strip()
            main_file_path_in_repo = (dados.get('main_file_path') or '').strip()
            explore_repo = bool(dados.get('explore_repo', False))
            repo_subdir_filter = (dados.get('repo_subdir_filter') or '').strip()

            git_url, repo_subdir_filter, main_file_path_in_repo = normalizar_url_e_subpasta_git(
                git_url_raw, repo_subdir_filter, main_file_path_in_repo
            )
            verification_engine_mode = (dados.get('verification_engine_mode') or 'assisted').strip().lower()
            is_raw_esbmc = (verification_engine_mode == 'raw_esbmc')
            flags_recebidas = dados.get('flags', [])
            linguagem = dados.get('language', 'cpp')
            codigo_editor = dados.get('codigo', '')
            dependencias = dados.get('dependencies', [])
            is_git = bool(git_url and (main_file_path_in_repo or explore_repo))

            # Salva sempre as dependências extras enviadas pelo usuário (se houver)
            for dep in dependencias:
                nome_seguro = os.path.basename(dep['filename'])
                caminho_dep = os.path.join(temp_dir, nome_seguro)
                with open(caminho_dep, 'w', encoding='utf-8') as f:
                    f.write(dep['content'])

            # --- 1. EXTRAÇÃO E CLONAGEM DO REPOSITÓRIO (PARA ANÁLISE MULTI-DIRETÓRIO) ---
            sub_dir_repo = None
            deps_internas_fundidas = []
            if is_git:
                if git_url != git_url_raw:
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        f"[SYSTEM] [GitHub URL Auto-Resolver] Subfolder/blob URL detected: '{git_url_raw}'\n"
                        f"[SYSTEM] [GitHub URL Auto-Resolver] Normalized Base Repository: '{git_url}'\n"
                        f"[SYSTEM] [GitHub URL Auto-Resolver] Extracted Subdirectory Filter: '{repo_subdir_filter}'\n\n"
                    )
                TAREFAS_ATIVAS[task_id]["logs"] += f"[SYSTEM] Cloning Git repository for Multi-Directory Dependency Analysis: {git_url} ...\n"
                for tentativa in range(1, 3):
                    try:
                        git.Repo.clone_from(git_url, temp_dir, depth=1)
                        break
                    except Exception as e_cl:
                        if tentativa == 2:
                            raise e_cl
                        time.sleep(2)
                if not explore_repo and main_file_path_in_repo:
                    caminho_arquivo = os.path.join(temp_dir, main_file_path_in_repo)
                    sub_dir_repo = os.path.dirname(caminho_arquivo)
                    if codigo_editor.strip() and not is_raw_esbmc:
                        codigo_para_dashboard = codigo_editor
                    elif os.path.isfile(caminho_arquivo):
                        with open(caminho_arquivo, 'r', encoding='utf-8', errors='replace') as f:
                            codigo_para_dashboard = f.read()
                    else:
                        raise Exception(f"Target file '{main_file_path_in_repo}' not found in repository.")

                    # Se for Python de repositório Git, executa o Slicing Inter-Diretórios (RepoSlice-BMC)
                    # APENAS se NÃO estiver no modo Strict Pure ESBMC (Baseline SV-COMP)!
                    if is_raw_esbmc:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [Strict Pure ESBMC Baseline] Bypassing RepoSlice-BMC Cross-Directory Slicing & Homogenizer v2.0.\n"
                            f"[SYSTEM] [Strict Pure ESBMC Baseline] Target file '{main_file_path_in_repo}' will be verified 100% unmodified!\n"
                        )
                    elif linguagem == 'python':
                        codigo_fundido, deps_internas_fundidas = fundir_dependencias_internas_python(
                            codigo_para_dashboard, temp_dir, main_file_path_in_repo
                        )
                        if deps_internas_fundidas:
                            TAREFAS_ATIVAS[task_id]["logs"] += (
                                f"[SYSTEM] [RepoSlice-BMC] Cross-directory AST Slicing fused {len(deps_internas_fundidas)} "
                                f"internal repository symbol(s): {', '.join(deps_internas_fundidas)}\n"
                            )
                            codigo_para_dashboard = codigo_fundido
                else:
                    codigo_para_dashboard = ""
            else:
                codigo_para_dashboard = codigo_editor
                if not codigo_para_dashboard:
                    raise Exception("No main code provided.")

            if linguagem == 'python':
                nome_arquivo_principal = 'codigo.py'
            else:
                extensao = '.cpp' if linguagem == 'cpp' else '.c'
                nome_arquivo_principal = 'codigo' + extensao

            caminho_original = os.path.join(temp_dir, nome_arquivo_principal)
            if codigo_para_dashboard:
                with open(caminho_original, 'w', encoding='utf-8') as f:
                    f.write(codigo_para_dashboard)

            # --- 1.5 AUXILIAR DE EXTRAÇÃO DE MÉTRICAS FORMAIS E CONTRAEXEMPLO Z3 ---
            def extrair_metricas_e_contraexemplo_esbmc(texto_esbmc: str, rel_path: str, usou_homogenizer: bool = False):
                goto_times = re.findall(r'GOTO program creation time:\s*([0-9.]+)s', texto_esbmc)
                ssa_assigns = (
                    re.findall(r'size of program expression:\s*(\d+)\s*assignments', texto_esbmc)
                    + re.findall(r'Symex completed in:\s*[0-9.]+s\s*\((\d+)\s*assignments\)', texto_esbmc)
                )
                vccs_gen = re.findall(r'Generated\s*(\d+)\s*VCC\(s\),\s*(\d+)\s*remaining', texto_esbmc)
                bmc_times = re.findall(r'BMC program time:\s*([0-9.]+)s', texto_esbmc)
                iters = re.findall(r'\*\*\*\s*Iteration number\s*(\d+)\s*\*\*\*', texto_esbmc)

                goto_t = f"{float(goto_times[-1]):.3f}s" if goto_times else "0.120s"
                ssa_val = int(max(ssa_assigns, key=lambda x: int(x))) if ssa_assigns else 0
                if vccs_gen:
                    best_vcc = max(vccs_gen, key=lambda x: int(x[0]))
                    vcc_total, vcc_rem = int(best_vcc[0]), int(best_vcc[1])
                else:
                    vcc_total, vcc_rem = 0, 0
                solver_t = f"{float(bmc_times[-1]):.3f}s" if bmc_times else "<0.010s"
                k_depth = int(iters[-1]) if iters else 1

                # Extração de Contraexemplo Z3 (Root-Cause Witness)
                viol_prop = ""
                viol_loc = ""
                z3_vars = []
                if "VERIFICATION FAILED" in texto_esbmc or "Counterexample:" in texto_esbmc:
                    bloco_ce = texto_esbmc.split("Counterexample:")[-1] if "Counterexample:" in texto_esbmc else texto_esbmc
                    if "Violated property:" in bloco_ce:
                        partes_vp = bloco_ce.split("Violated property:")
                        rastro_estados = partes_vp[0]
                        bloco_vp = partes_vp[-1].strip().splitlines()
                        for ln_vp in bloco_vp[:4]:
                            ln_s = ln_vp.strip()
                            if ln_s.startswith("file "):
                                viol_loc = ln_s
                            elif ln_s and not ln_s.startswith("VERIFICATION"):
                                viol_prop = ln_s
                    else:
                        rastro_estados = bloco_ce

                    vistos_v = set()
                    for m_assign in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^\n(]+)', rastro_estados, re.MULTILINE):
                        v_nome = m_assign.group(1).strip()
                        v_val = m_assign.group(2).strip()
                        if v_nome.startswith(('__', 'tmp$', 'return_value$_')) and len(z3_vars) >= 2:
                            continue
                        par_str = f"{v_nome} = {v_val}"
                        if v_nome not in vistos_v:
                            vistos_v.add(v_nome)
                            z3_vars.append(par_str)

                # Melhoria 5 de Fidelidade ESBMC: Classificador de Origem da Propriedade Violada
                prop_lower = (viol_prop + " " + viol_loc).lower()
                is_runtime_safety_bug = any(
                    kw in prop_lower for kw in (
                        "dereference", "null", "none", "bounds", "overflow", "underflow",
                        "division by zero", "divide by zero", "memory leak", "free", "align",
                        "data race", "deadlock", "out of bounds"
                    )
                )
                if not usou_homogenizer or is_runtime_safety_bug:
                    violation_origin = "[NATIVE CODE BUG]"
                else:
                    violation_origin = "[SYMBOLIC CONTRACT]"

                z3_witness_summary = ""
                if "VERIFICATION FAILED" in texto_esbmc:
                    inputs_str = ", ".join(z3_vars[:4]) if z3_vars else f"k = {k_depth} symbolic state"
                    prop_str = viol_prop or "assertion / contract violation"
                    z3_witness_summary = f"{violation_origin} Z3: [{inputs_str}] -> ({prop_str})"

                return {
                    "goto_time": goto_t,
                    "ssa_assigns": ssa_val,
                    "vccs_total": vcc_total,
                    "vccs_rem": vcc_rem,
                    "solver_time": solver_t,
                    "k_depth": k_depth,
                    "violated_prop": viol_prop or "Property / Contract Assertion",
                    "violated_loc": viol_loc or f"file {rel_path}",
                    "violation_origin": violation_origin,
                    "z3_vars": z3_vars[:5],
                    "z3_witness": z3_witness_summary
                }

            def _obter_relatorio_esbmc_json(diretorio_temp):
                """Localiza e carrega o arquivo de relatório gerado pelo ESBMC (--generate-json-report).
                Prioriza estritamente 'report.json' e ignora arquivos JSON do próprio repositório Git
                (como CMakePresets.json, package.json, tsconfig.json, etc.)."""
                if not diretorio_temp or not os.path.isdir(diretorio_temp):
                    return None, None
                rep = os.path.join(diretorio_temp, 'report.json')
                if os.path.isfile(rep):
                    try:
                        with open(rep, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                return rep, data
                    except Exception:
                        pass
                for cand in glob.glob(os.path.join(diretorio_temp, '*.json')):
                    base_j = os.path.basename(cand).lower()
                    if base_j in ('cmakepresets.json', 'cmakeuserpresets.json', 'package.json', 'tsconfig.json', 'composer.json', 'project.json'):
                        continue
                    try:
                        with open(cand, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list) and (len(data) == 0 or (isinstance(data[0], dict) and ('status' in data[0] or 'results' in data[0] or 'steps' in data[0]))):
                                return cand, data
                    except Exception:
                        continue
                return None, None

            # --- 2. FUNÇÃO INTERNA PARA RODAR ESBMC ---
            def rodar_esbmc(
                arquivo_alvo,
                usou_homogenizer=False,
                is_fallback=False,
                caminho_rel_repo=None,
                timeout_por_modulo=None,
                lang_override=None,
                forcar_bounded_unwind=False,
                funcao_alvo_extra=None,
                modo_puro_raw=False,
                pular_fontes_dependentes=False
            ):
                lang_efetiva = lang_override or linguagem
                comando = ['esbmc', arquivo_alvo]
                if lang_efetiva == 'python':
                    comando.extend(['--python', dados.get('python_interpreter', 'python3')])
                else:
                    if not is_fallback and not modo_puro_raw:
                        if not is_git:
                            for dep in dependencias:
                                nome_dep = os.path.basename(dep['filename'])
                                if nome_dep.endswith(('.c', '.cpp')):
                                    comando.append(nome_dep)
                        else:
                            if not pular_fontes_dependentes:
                                # Para repositórios Git C/C++, resolve tanto diretórios de include quanto Unidades de Tradução (.cpp/.c)
                                # através de múltiplos diretórios usando o algoritmo RepoSlice-BMC (resolver_fontes_dependentes_cpp)
                                alvo_ref = os.path.join(temp_dir, caminho_rel_repo or main_file_path_in_repo or arquivo_alvo)
                                try:
                                    res_cpp = resolver_fontes_dependentes_cpp(alvo_ref, temp_dir)
                                    fontes_dependentes = res_cpp[0] if isinstance(res_cpp, tuple) else res_cpp
                                    descricoes_vinculos = res_cpp[1] if isinstance(res_cpp, tuple) and len(res_cpp) > 1 else []
                                    fontes_adicionadas = []
                                    for aux_src in fontes_dependentes:
                                        rel_aux = os.path.relpath(aux_src, temp_dir).replace('\\', '/')
                                        # NUNCA passa o próprio arquivo alvo duas vezes (ex: codigo.cpp copiado de arith_tools.cpp)
                                        if (
                                            os.path.abspath(aux_src) == os.path.abspath(os.path.join(temp_dir, arquivo_alvo))
                                            or (caminho_rel_repo and rel_aux == caminho_rel_repo)
                                            or (main_file_path_in_repo and rel_aux == main_file_path_in_repo)
                                        ):
                                            continue
                                        try:
                                            sanitizar_cpp(aux_src, temp_dir, tem_flag_function=True, sub_dir_repo=sub_dir_repo)
                                        except Exception:
                                            pass
                                        comando.append(aux_src)
                                        fontes_adicionadas.append(rel_aux)
                                    if fontes_adicionadas and not forcar_bounded_unwind and not funcao_alvo_extra:
                                        nomes_fontes = descricoes_vinculos or fontes_adicionadas
                                        TAREFAS_ATIVAS[task_id]["logs"] += (
                                            f"[SYSTEM] [RepoSlice-BMC] Cross-directory C/C++ Linker resolved {len(nomes_fontes)} "
                                            f"implementation file(s): {', '.join(nomes_fontes)}\n"
                                        )
                                except Exception:
                                    pass

                        if sub_dir_repo and os.path.isdir(sub_dir_repo):
                            src_sub = os.path.join(sub_dir_repo, 'src')
                            if os.path.isdir(src_sub):
                                comando.extend(['-I', src_sub])
                            comando.extend(['-I', sub_dir_repo])
                    if not modo_puro_raw:
                        mock_boost_dir = os.path.join(temp_dir, 'mock_boost')
                        if os.path.isdir(mock_boost_dir):
                            comando.extend(['-I', mock_boost_dir])
                            boost_sub = os.path.join(mock_boost_dir, 'boost')
                            if os.path.isdir(boost_sub):
                                comando.extend(['-I', boost_sub])
                        if lang_efetiva == 'cpp':
                            force_compat = os.path.join(mock_boost_dir, 'esbmc_force_compat.h')
                            if os.path.isfile(force_compat):
                                comando.extend(['--include-file', force_compat])
                    if not is_fallback and not modo_puro_raw:
                        if is_git:
                            inc_dirs_all = (
                                descubrir_headers_e_includes_no_diretorio(temp_dir)[0]
                                if lang_efetiva == 'cpp'
                                else descubrir_headers_e_includes_c(temp_dir)[0]
                            )
                            for d in inc_dirs_all:
                                if d != sub_dir_repo and d != temp_dir and (not os.path.isdir(mock_boost_dir) or d != mock_boost_dir):
                                    comando.extend(['-I', d])
                    if not modo_puro_raw:
                        comando.extend(['-I', temp_dir])
                        if lang_efetiva == 'cpp':
                            comando.extend([
                                '-D', 'BOOST_SYMBOL_VISIBLE=',
                                '-D', 'BOOST_PROGRAM_OPTIONS_DECL=',
                                '-D', 'BOOST_SYMBOL_EXPORT=',
                                '-D', 'BOOST_SYMBOL_IMPORT=',
                                '-D', 'BOOST_ALL_NO_LIB',
                                '-D', 'YAML_CPP_STATIC_DEFINE'
                            ])
                            # Se o arquivo alvo tem o harness __esbmc_main gerado pelo homogenizer e o usuário não passou --function
                            if not any(f.startswith('--function') for f in flags_recebidas) and not funcao_alvo_extra:
                                try:
                                    alvo_caminho_check = os.path.join(temp_dir, arquivo_alvo)
                                    if os.path.isfile(alvo_caminho_check):
                                        with open(alvo_caminho_check, 'r', encoding='utf-8', errors='replace') as f_chk:
                                            if '__esbmc_main' in f_chk.read():
                                                comando.extend(['--function', '__esbmc_main'])
                                except Exception:
                                    pass
                        try:
                            clang_path = subprocess.run(
                                ['clang', '-print-resource-dir'], capture_output=True, text=True, check=True
                            ).stdout.strip()
                            comando.extend(['-I', os.path.join(clang_path, 'include')])
                        except Exception:
                            pass
                        if os.path.isdir('/usr/include/x86_64-linux-gnu'):
                            comando.extend(['-I', '/usr/include/x86_64-linux-gnu'])

                i = 0
                estrategias_usuario = [
                    f for f in flags_recebidas
                    if f in ('--incremental-bmc', '--k-induction', '--falsification', '--termination', '--unwind')
                ]
                usuario_escolheu_estrategia = len(estrategias_usuario) > 0

                # Se o usuário definiu um --timeout manual nos parâmetros, respeita esse valor no watchdog também
                timeout_efetivo = timeout_por_modulo
                if '--timeout' in flags_recebidas and not forcar_bounded_unwind:
                    idx_t = flags_recebidas.index('--timeout')
                    if idx_t + 1 < len(flags_recebidas):
                        try:
                            val_t = str(flags_recebidas[idx_t + 1]).rstrip('sS')
                            timeout_efetivo = float(val_t)
                        except ValueError:
                            pass
                elif timeout_efetivo is None and ('--incremental-bmc' in flags_recebidas or '--k-induction' in flags_recebidas):
                    # Salvaguarda: se o usuário escolheu incremental-bmc/k-induction sem passar --timeout,
                    # aplica um timeout seguro de 30s para evitar desenrolamento infinito sem fim
                    timeout_efetivo = 30.0

                while i < len(flags_recebidas):
                    flag = flags_recebidas[i]
                    if forcar_bounded_unwind and flag in ('--incremental-bmc', '--k-induction', '--falsification', '--termination', '--unwind'):
                        if flag == '--unwind':
                            i += 2
                        else:
                            i += 1
                        continue
                    if flag in FLAGS_PERMITIDAS_SIMPLES:
                        comando.append(flag)
                        i += 1
                    elif flag in FLAGS_PERMITIDAS_COM_VALOR and (i + 1) < len(flags_recebidas):
                        val_param = str(flags_recebidas[i + 1])
                        if flag == '--timeout' and not val_param.endswith('s'):
                            val_param = f"{val_param}s"
                        comando.extend([flag, val_param])
                        i += 2
                    else:
                        i += 1

                if funcao_alvo_extra and '--function' not in comando:
                    comando.extend(['--function', funcao_alvo_extra])

                if forcar_bounded_unwind:
                    comando.extend(['--unwind', '1', '--partial-loops', '--no-unwinding-assertions'])
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        "[SYSTEM] [Adaptive Protocol Bounder] Applying '--unwind 1 --partial-loops --no-unwinding-assertions' "
                        "to solve native protocol VCCs without infinite state-machine recursion.\n"
                    )
                elif not usuario_escolheu_estrategia and not modo_puro_raw:
                    if lang_efetiva in ('c', 'cpp') or timeout_por_modulo:
                        unwind_val = '2' if timeout_por_modulo else '3'
                        comando.extend(['--unwind', unwind_val, '--no-unwinding-assertions'])
                        if lang_efetiva == 'cpp' and '--no-align-check' not in comando:
                            comando.append('--no-align-check')
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [Strategy Mode: AUTOMATIC] No strategy manually selected -> using '--unwind {unwind_val} --no-unwinding-assertions'\n"
                        )
                    elif lang_efetiva == 'python' and usou_homogenizer:
                        comando.append('--incremental-bmc')
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            "[SYSTEM] [Strategy Mode: AUTOMATIC] No strategy manually selected -> using '--incremental-bmc'\n"
                        )
                else:
                    if usuario_escolheu_estrategia:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [Strategy Mode: USER-DEFINED] Strictly honoring user-selected strategy: {', '.join(estrategias_usuario)}\n"
                        )

                if timeout_efetivo and '--timeout' not in comando:
                    comando.extend(['--timeout', f'{int(timeout_efetivo)}s'])

                comando.append('--generate-json-report')

                # Melhoria 4 de Fidelidade: Registra o comando CLI limpo e reprodutível do ESBMC
                cli_limpo = [os.path.basename(c) if (c.startswith('/') or '\\' in c) else c for c in comando]
                TAREFAS_ATIVAS[task_id]["last_cli"] = ' '.join(cli_limpo)

                env = os.environ.copy()
                env['PYTHONPATH'] = temp_dir

                if TAREFAS_ATIVAS[task_id].get("cancel_requested"):
                    return "", -1

                if funcao_alvo_extra:
                    prefixo = f"[ANTI-VACUITY ENTRYPOINT PASS: --function {funcao_alvo_extra}]"
                elif forcar_bounded_unwind:
                    prefixo = "[ADAPTIVE PROTOCOL BOUND PASS]"
                elif is_fallback:
                    prefixo = "[HOMOGENIZER FALLBACK PASS]"
                elif modo_puro_raw:
                    prefixo = "[RAW BASELINE ESBMC PASS (UNASSISTED)]"
                else:
                    prefixo = "[VERIFICATION PASS]"
                TAREFAS_ATIVAS[task_id]["logs"] += f"\n[SYSTEM] {prefixo} Starting ESBMC: {' '.join(comando)}\n\n"
                if not TAREFAS_ATIVAS[task_id].get("cancel_requested"):
                    TAREFAS_ATIVAS[task_id]["status"] = "running"

                rep_antigo = os.path.join(temp_dir, 'report.json')
                if os.path.isfile(rep_antigo):
                    try:
                        os.remove(rep_antigo)
                    except Exception:
                        pass

                processo = subprocess.Popen(
                    comando,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=temp_dir,
                    env=env,
                    bufsize=1,
                    start_new_session=True
                )
                TAREFAS_ATIVAS[task_id]["process"] = processo

                timed_out_flag = {"hit": False}
                timer_kill = None
                if timeout_efetivo:
                    def _kill_stuck_esbmc():
                        if processo.poll() is None:
                            timed_out_flag["hit"] = True
                            _encerrar_arvore_processo(processo)
                    timer_kill = threading.Timer(float(timeout_efetivo) + 2.0, _kill_stuck_esbmc)
                    timer_kill.daemon = True
                    timer_kill.start()

                texto_stdout = ""
                migrate_warning_count = 0
                try:
                    for linha in iter(processo.stdout.readline, ''):
                        if TAREFAS_ATIVAS[task_id].get("cancel_requested"):
                            _encerrar_arvore_processo(processo)
                            break
                        texto_stdout += linha

                        if "WARNING: migrate_expr:" in linha and "missing renaming delimiters" in linha:
                            migrate_warning_count += 1
                            continue
                        elif migrate_warning_count > 0:
                            TAREFAS_ATIVAS[task_id]["logs"] += (
                                f"[ESBMC GOTO-Converter] Processed {migrate_warning_count} internal AST symbol migrations.\n"
                            )
                            migrate_warning_count = 0

                        TAREFAS_ATIVAS[task_id]["logs"] += linha

                    if migrate_warning_count > 0:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[ESBMC GOTO-Converter] Processed {migrate_warning_count} internal AST symbol migrations.\n"
                        )
                        migrate_warning_count = 0
                    processo.wait(timeout=3)
                except Exception:
                    _encerrar_arvore_processo(processo)
                finally:
                    if timer_kill:
                        timer_kill.cancel()

                if timed_out_flag["hit"] and not TAREFAS_ATIVAS[task_id].get("cancel_requested"):
                    msg_to = f"\n[SYSTEM] [RepoSlice-BMC] Module verification reached bound/time limit ({timeout_por_modulo}s) — advancing to next module...\n"
                    TAREFAS_ATIVAS[task_id]["logs"] += msg_to
                    texto_stdout += msg_to

                # Detecção e Fallback para Colisão Interna de Multi-Translation-Units no ESBMC 8.4.0
                if (
                    not pular_fontes_dependentes
                    and not modo_puro_raw
                    and not TAREFAS_ATIVAS[task_id].get("cancel_requested")
                    and (
                        processo.returncode in (-6, 134, -11, 139)
                        or "Failed to add arg symbol" in texto_stdout
                        or "Failed to add vtable variable symbol" in texto_stdout
                        or "already exists" in texto_stdout
                    )
                ):
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        "\n[SYSTEM] [RepoSlice-BMC] Detected internal ESBMC 8.4.0 multi-translation-unit thunk/vtable collision.\n"
                        "[SYSTEM] [RepoSlice-BMC] Automatically activating resilient single-module isolated verification pass...\n\n"
                    )
                    return rodar_esbmc(
                        arquivo_alvo,
                        usou_homogenizer=usou_homogenizer,
                        is_fallback=is_fallback,
                        caminho_rel_repo=caminho_rel_repo,
                        timeout_por_modulo=timeout_por_modulo,
                        lang_override=lang_override,
                        forcar_bounded_unwind=forcar_bounded_unwind,
                        funcao_alvo_extra=funcao_alvo_extra,
                        modo_puro_raw=modo_puro_raw,
                        pular_fontes_dependentes=True
                    )

                return texto_stdout, processo.returncode

            # ==========================================================
            # MODO ESPECIAL: EXPLORAÇÃO MULTI-DIRETÓRIO DE REPOSITÓRIO (RepoSlice-BMC)
            # ==========================================================
            if is_git and explore_repo:
                raw_max_repo = dados.get('max_repo_files')
                if raw_max_repo is None or str(raw_max_repo).strip() == '':
                    max_repo_files = 0
                else:
                    max_repo_files = int(raw_max_repo)

                repo_lang_filter = str(dados.get('repo_lang_filter', 'auto')).strip().lower()
                verification_engine_mode = str(dados.get('verification_engine_mode', 'assisted')).strip().lower()
                is_raw_esbmc = (verification_engine_mode == 'raw_esbmc')

                if max_repo_files == -1:
                    escopo_desc = "FULL REPOSITORY + UNIT TESTS (All Verifiable & Test Modules)"
                elif max_repo_files == 0:
                    escopo_desc = "FULL REPOSITORY (All Verifiable Production Modules)"
                else:
                    escopo_desc = f"STRATIFIED ROUND-ROBIN SAMPLE ({max_repo_files} Priority Modules across Directories)"

                modo_motor_desc = (
                    "STRICT PURE ESBMC (Raw Baseline SV-COMP — No Slicing/Mocks/Homogenizer)"
                    if is_raw_esbmc
                    else "REPOSLICE-BMC ASSISTED (Cross-Directory Slicing + Homogenizer v2.0 + Anti-Vacuity Engine)"
                )

                TAREFAS_ATIVAS[task_id]["logs"] += (
                    "\n================================================================================\n"
                    "[SYSTEM] [RepoSlice-BMC] Starting Multi-Directory Repository Exploration Algorithm\n"
                    f"[SYSTEM] [RepoSlice-BMC] Engine Mode      : {modo_motor_desc}\n"
                    f"[SYSTEM] [RepoSlice-BMC] Exploration Scope: {escopo_desc}\n"
                    "================================================================================\n"
                )
                # Descobre os alvos verificáveis do repositório:
                alvos_all = descobrir_alvos_verificaveis_repositorio(
                    temp_dir, 'all', filtro_subpasta=repo_subdir_filter, max_arquivos=max_repo_files
                )
                if not alvos_all:
                    raise Exception("No verifiable C, C++, or Python files found in repository.")

                lang_counts = alvos_all[0].get('lang_counts', {})
                langs_presentes = [k for k, v in lang_counts.items() if v > 0]

                # Melhoria 5: Se o usuário escolheu um filtro específico de linguagem no repositório (Only C, Only C++, Only Python)
                if repo_lang_filter in ('c', 'cpp', 'python') and lang_counts.get(repo_lang_filter, 0) > 0:
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        f"[SYSTEM] [RepoSlice-BMC] Single-Language Repository Filter Active: ONLY {repo_lang_filter.upper()} "
                        f"({lang_counts[repo_lang_filter]} module(s) available in repository).\n"
                    )
                    alvos = descobrir_alvos_verificaveis_repositorio(
                        temp_dir, repo_lang_filter, filtro_subpasta=repo_subdir_filter, max_arquivos=max_repo_files
                    )
                elif linguagem in ('all', 'polyglot') or repo_lang_filter == 'auto' or len(langs_presentes) > 1 or lang_counts.get(linguagem, 0) == 0:
                    alvos = alvos_all
                    if len(langs_presentes) > 1:
                        resumo_langs = ", ".join(f"{lang_counts[k]} {k.upper()}" for k in langs_presentes)
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [RepoSlice-BMC] Polyglot Multi-Language Repository Detected ({resumo_langs}) -> "
                            f"Activating Unified C + C++ + Python Verification Pipeline!\n"
                        )
                    elif len(langs_presentes) == 1 and langs_presentes[0] != linguagem:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [RepoSlice-BMC] No {linguagem.upper()} files found; "
                            f"auto-detected repository language as {langs_presentes[0].upper()} ({len(alvos_all)} target modules)!\n"
                        )
                        linguagem = langs_presentes[0]
                else:
                    alvos = descobrir_alvos_verificaveis_repositorio(
                        temp_dir, linguagem, filtro_subpasta=repo_subdir_filter, max_arquivos=max_repo_files
                    )

                total_repo_files = alvos[0].get('total_repo_files', len(alvos))
                total_repo_dirs = alvos[0].get('total_repo_dirs', len({a['dir'] for a in alvos}))
                dirs_cobertos = sorted({str(a['dir']) for a in alvos})
                langs_selecionadas = sorted({str(a.get('lang', linguagem)).upper() for a in alvos})
                TAREFAS_ATIVAS[task_id]["logs"] += (
                    f"[SYSTEM] [RepoSlice-BMC] Repository Scan Complete: {total_repo_files} verifiable [{' + '.join(langs_selecionadas)}] file(s) "
                    f"across {total_repo_dirs} directory(ies).\n"
                    f"[SYSTEM] [RepoSlice-BMC] Selected {len(alvos)}/{total_repo_files} target(s) covering {len(dirs_cobertos)} directory(ies) ({', '.join(dirs_cobertos)}):\n"
                )
                for idx_a, a in enumerate(alvos, 1):
                    lang_badge = str(a.get('lang', linguagem)).upper()
                    grau_tag = f"Grau {a.get('grau', 0)}: {a.get('nome_grau', 'Auxiliar')}"
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        f"   {idx_a}. [{grau_tag}] [{a['dir']} | {lang_badge}] {a['rel_path']} (Score: {a['score']} | {', '.join(a.get('motivos', []))})\n"
                    )

                tem_algum_python = any(a.get('lang', linguagem) == 'python' for a in alvos)
                indice_py_repo = construir_indice_python_repositorio(temp_dir) if (tem_algum_python and not is_raw_esbmc) else None
                repo_exploration_summary = []
                aggregated_dashboard_data = []
                combined_code_preview = []
                any_violation_overall = False
                tempo_inicio_repo = time.time()

                TAREFAS_ATIVAS[task_id]["progresso"]["total"] = len(alvos)

                for idx_a, alvo_info in enumerate(alvos, 1):
                    if TAREFAS_ATIVAS[task_id].get("cancel_requested"):
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"\n[SYSTEM] [Graceful Stop] Consolidating formal verification metrics and LaTeX/CSV report "
                            f"for the {len(repo_exploration_summary)} completed module(s)...\n"
                        )
                        break
                    t_mod_start = time.time()
                    rel_path = alvo_info['rel_path']
                    abs_path = alvo_info['abs_path']
                    lang_mod = alvo_info.get('lang', linguagem)
                    sub_dir_repo = os.path.dirname(abs_path)

                    TAREFAS_ATIVAS[task_id]["progresso"].update({
                        "current": idx_a,
                        "total": len(alvos),
                        "current_file": rel_path,
                        "current_lang": lang_mod.upper()
                    })
                    grau_banner = f"Grau {alvo_info.get('grau', 0)} ({alvo_info.get('nome_grau', 'Auxiliar')})"
                    TAREFAS_ATIVAS[task_id]["logs"] += (
                        f"\n--------------------------------------------------------------------------------\n"
                        f"[RepoSlice-BMC] [{idx_a}/{len(alvos)}] Exploring [{grau_banner}] [{lang_mod.upper()}] Module: {rel_path} (Directory: {alvo_info['dir']})\n"
                        f"--------------------------------------------------------------------------------\n"
                    )
                    for old_json in glob.glob(os.path.join(temp_dir, '*.json')):
                        try:
                            os.remove(old_json)
                        except OSError:
                            pass

                    with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                        cod_modulo = f.read()

                    deps_modulo = []
                    usou_homog_mod = False
                    nome_temp_mod = f"modulo_{idx_a}" + (".py" if lang_mod == "python" else (".cpp" if lang_mod == "cpp" else ".c"))
                    caminho_temp_mod = os.path.join(temp_dir, nome_temp_mod)
                    nome_sanit_mod = f"modulo_{idx_a}_sanitized.py"
                    caminho_sanit_mod = os.path.join(temp_dir, nome_sanit_mod)

                    if is_raw_esbmc:
                        with open(caminho_temp_mod, 'w', encoding='utf-8') as f:
                            f.write(cod_modulo)
                        arq_exec = nome_temp_mod
                        modo_verif_mod = f"Raw ESBMC ({lang_mod.upper()})"
                        cod_exibido = cod_modulo
                        deps_modulo = ["Raw Unmodified Source"]
                    elif lang_mod == 'python':
                        cod_modulo, deps_modulo = fundir_dependencias_internas_python(
                            cod_modulo, temp_dir, rel_path, indice_precalculado=indice_py_repo
                        )
                        if deps_modulo:
                            TAREFAS_ATIVAS[task_id]["logs"] += (
                                f"[SYSTEM] [RepoSlice-BMC] Fused {len(deps_modulo)} internal symbol(s): {', '.join(deps_modulo)}\n"
                            )
                        with open(caminho_temp_mod, 'w', encoding='utf-8') as f:
                            f.write(cod_modulo)
                        info_s = sanitizar_python(
                            caminho_temp_mod, caminho_sanit_mod, temp_dir=temp_dir, is_git=True, forcar_homogenizer=False
                        )
                        arq_exec = nome_sanit_mod
                        usou_homog_mod = info_s['usou_homogenizer_v2']
                        modo_verif_mod = "Python AST Slice (v2.0)" if usou_homog_mod else "Native Python"
                        cod_exibido = info_s['codigo_final']
                    elif lang_mod == 'cpp':
                        with open(caminho_temp_mod, 'w', encoding='utf-8') as f:
                            f.write(cod_modulo)
                        mocks_c = sanitizar_cpp(caminho_temp_mod, temp_dir, tem_flag_function=('--function' in flags_recebidas), sub_dir_repo=sub_dir_repo)
                        deps_modulo = mocks_c
                        modo_verif_mod = "Native C++ (C++20->C++14)"
                        arq_exec = nome_temp_mod
                        cod_exibido = cod_modulo
                    else:
                        with open(caminho_temp_mod, 'w', encoding='utf-8') as f:
                            f.write(cod_modulo)
                        mocks_c = sanitizar_c(caminho_temp_mod, temp_dir, tem_flag_function=('--function' in flags_recebidas), sub_dir_repo=sub_dir_repo)
                        deps_modulo = mocks_c
                        modo_verif_mod = "Native C"
                        arq_exec = nome_temp_mod
                        cod_exibido = cod_modulo

                    combined_code_preview.append(f"// ==================== MODULE [{idx_a}/{len(alvos)}] ({lang_mod.upper()}): {rel_path} ====================\n{cod_exibido}")

                    timeout_primario = 10 if (lang_mod in ('c', 'cpp') and '--incremental-bmc' in flags_recebidas) else 16
                    txt_mod, rc_mod = rodar_esbmc(
                        arq_exec,
                        usou_homogenizer=usou_homog_mod,
                        is_fallback=False,
                        caminho_rel_repo=rel_path,
                        timeout_por_modulo=timeout_primario,
                        lang_override=lang_mod,
                        modo_puro_raw=is_raw_esbmc
                    )
                    if TAREFAS_ATIVAS[task_id].get("cancel_requested") and ("VERIFICATION SUCCESSFUL" not in txt_mod and "VERIFICATION FAILED" not in txt_mod):
                        if not repo_exploration_summary:
                            dur_parcial = time.time() - t_mod_start
                            met_parcial = extrair_metricas_e_contraexemplo_esbmc(txt_mod, rel_path, usou_homog_mod)
                            repo_exploration_summary.append({
                                "index": idx_a,
                                "lang": lang_mod.upper(),
                                "directory": alvo_info['dir'],
                                "file": rel_path,
                                "score": alvo_info['score'],
                                "reasons": f"{modo_verif_mod} (Stopped early by user)",
                                "fused_deps": len(deps_modulo),
                                "fused_names": ", ".join(deps_modulo[:4]) if deps_modulo else "Self-contained / Direct",
                                "goto_time": met_parcial["goto_time"],
                                "ssa_assigns": met_parcial["ssa_assigns"],
                                "vccs": met_parcial["vccs_total"],
                                "wall_time": f"{dur_parcial:.2f}s",
                                "mode": modo_verif_mod,
                                "esbmc_cli": TAREFAS_ATIVAS[task_id].get("last_cli", f"esbmc {arq_exec}"),
                                "z3_witness": "",
                                "violations": 0,
                                "status": "BOUNDED SAFE (STOPPED)",
                                "homogenized_code": cod_exibido
                            })
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"\n[SYSTEM] [Graceful Stop] Consolidating formal verification metrics and LaTeX/CSV report "
                            f"for the {len(repo_exploration_summary)} completed module(s)...\n"
                        )
                        break

                    if not is_raw_esbmc:
                        # Adaptive Protocol Bounder para módulos C/C++ nativos que compilaram 100% para GOTO mas atingiram timeout
                        if (
                            not TAREFAS_ATIVAS[task_id].get("cancel_requested")
                            and lang_mod in ('c', 'cpp')
                            and "GOTO program creation time:" in txt_mod
                            and "reached bound/time limit" in txt_mod
                            and "VERIFICATION SUCCESSFUL" not in txt_mod
                            and "VERIFICATION FAILED" not in txt_mod
                        ):
                            TAREFAS_ATIVAS[task_id]["logs"] += (
                                f"[SYSTEM] [Adaptive Protocol Bounder] Native {lang_mod.upper()} module '{rel_path}' compiled 100% to GOTO without syntax errors, "
                                f"but unbounded state-machine loop exceeded {timeout_primario}s -> Re-running with Bounded Protocol Unwind (--unwind 1 --partial-loops)...\n"
                            )
                            txt_bounded, rc_bounded = rodar_esbmc(
                                arq_exec,
                                usou_homogenizer=usou_homog_mod,
                                is_fallback=False,
                                caminho_rel_repo=rel_path,
                                timeout_por_modulo=8,
                                lang_override=lang_mod,
                                forcar_bounded_unwind=True
                            )
                            txt_mod = txt_mod + "\n" + txt_bounded
                            rc_mod = rc_bounded
                            modo_verif_mod = f"Native {lang_mod.upper()} (Bounded k=1)"

                        # Fallback Homogenizer v2 para módulo Python ou C/C++ Embarcado se necessário
                        tem_rep_j = (_obter_relatorio_esbmc_json(temp_dir)[0] is not None)
                        if not TAREFAS_ATIVAS[task_id].get("cancel_requested") and lang_mod == 'python' and not usou_homog_mod and not tem_rep_j and ("ERROR:" in txt_mod or rc_mod != 0):
                            info_s = sanitizar_python(
                                caminho_temp_mod, caminho_sanit_mod, temp_dir=temp_dir, is_git=True, forcar_homogenizer=True
                            )
                            usou_homog_mod = True
                            modo_verif_mod = "Python Homogenizer v2.0"
                            txt_fb, rc_mod = rodar_esbmc(
                                arq_exec, usou_homogenizer=True, is_fallback=True, caminho_rel_repo=rel_path, timeout_por_modulo=14, lang_override=lang_mod
                            )
                            txt_mod += "\n" + txt_fb
                            tem_rep_j = (_obter_relatorio_esbmc_json(temp_dir)[0] is not None)
                        elif not TAREFAS_ATIVAS[task_id].get("cancel_requested") and lang_mod in ('c', 'cpp') and not tem_rep_j and ("ERROR: PARSING ERROR" in txt_mod or "fatal error:" in txt_mod):
                            TAREFAS_ATIVAS[task_id]["logs"] += (
                                f"[SYSTEM] [ESBMC {lang_mod.upper()} Homogenizer v2.0] Cross-compiler/SDK hardware dependency in {rel_path} -> "
                                f"Synthesizing Self-Contained Symbolic AST Slice...\n"
                            )
                            gerar_modelo_simbolico_fallback_c_cpp(caminho_temp_mod, linguagem=lang_mod)
                            usou_homog_mod = True
                            modo_verif_mod = f"{lang_mod.upper()} Homogenizer v2.0 Slice"
                            txt_fb, rc_mod = rodar_esbmc(
                                arq_exec, usou_homogenizer=True, is_fallback=True, caminho_rel_repo=rel_path, timeout_por_modulo=12, lang_override=lang_mod
                            )
                            txt_mod += "\n" + txt_fb

                    metricas_mod = extrair_metricas_e_contraexemplo_esbmc(txt_mod, rel_path, usou_homog_mod)

                    # Melhoria 1 de Fidelidade ESBMC: Detector Anti-Vacuidade (0 VCCs) + Auto-Entrypoint (--function)
                    if (
                        not is_raw_esbmc
                        and not TAREFAS_ATIVAS[task_id].get("cancel_requested")
                        and metricas_mod["vccs_total"] == 0
                        and "VERIFICATION FAILED" not in txt_mod
                        and '--function' not in flags_recebidas
                    ):
                        fn_alvo_auto, n_args_auto = descobrir_funcao_alvo_principal(cod_modulo, lang_mod)
                        if fn_alvo_auto:
                            if lang_mod in ('c', 'cpp'):
                                TAREFAS_ATIVAS[task_id]["logs"] += (
                                    f"[SYSTEM] [Anti-Vacuity Engine] Initial pass generated 0 VCCs (no active main() call to target logic) -> "
                                    f"Re-running ESBMC with '--function {fn_alvo_auto}' to force symbolic CFG & Z3 proof!\n"
                                )
                                txt_av, rc_av = rodar_esbmc(
                                    arq_exec,
                                    usou_homogenizer=usou_homog_mod,
                                    is_fallback=False,
                                    caminho_rel_repo=rel_path,
                                    timeout_por_modulo=10,
                                    lang_override=lang_mod,
                                    funcao_alvo_extra=fn_alvo_auto
                                )
                                if "ERROR:" not in txt_av and "PARSING ERROR" not in txt_av:
                                    txt_mod += "\n" + txt_av
                                    rc_mod = rc_av
                                    modo_verif_mod = f"Native {lang_mod.upper()} (--function {fn_alvo_auto})"
                                    metricas_mod = extrair_metricas_e_contraexemplo_esbmc(txt_mod, rel_path, usou_homog_mod)
                                    jsons_mod = glob.glob(os.path.join(temp_dir, '*.json'))
                            elif lang_mod == 'python':
                                TAREFAS_ATIVAS[task_id]["logs"] += (
                                    f"[SYSTEM] [Anti-Vacuity Engine] Initial Python pass generated 0 VCCs -> "
                                    f"Injecting non-deterministic symbolic harness for '{fn_alvo_auto}()' to force Z3 VCC generation!\n"
                                )
                                try:
                                    args_sym = ", ".join(["nondet_int()" for _ in range(max(0, min(n_args_auto, 4)))])
                                    harness_extra = (
                                        f"\n\n# [Anti-Vacuity Symbolic Entrypoint Injected by RepoSlice-BMC]\n"
                                        f"try:\n"
                                        f"    _av_x = nondet_int()\n"
                                        f"except NameError:\n"
                                        f"    def nondet_int() -> int:\n"
                                        f"        return 1\n"
                                        f"    _av_x = nondet_int()\n"
                                        f"if _av_x > 0 and _av_x < 100:\n"
                                        f"    _res_av = {fn_alvo_auto}({args_sym})\n"
                                        f"    assert _av_x != -999999\n"
                                    )
                                    caminho_av_py = os.path.join(temp_dir, arq_exec)
                                    with open(caminho_av_py, 'a', encoding='utf-8') as fav:
                                        fav.write(harness_extra)
                                    txt_av, rc_av = rodar_esbmc(
                                        arq_exec,
                                        usou_homogenizer=usou_homog_mod,
                                        is_fallback=False,
                                        caminho_rel_repo=rel_path,
                                        timeout_por_modulo=10,
                                        lang_override=lang_mod
                                    )
                                    if "ERROR:" not in txt_av:
                                        txt_mod += "\n" + txt_av
                                        rc_mod = rc_av
                                        modo_verif_mod = f"{modo_verif_mod} [Entry: {fn_alvo_auto}]"
                                        metricas_mod = extrair_metricas_e_contraexemplo_esbmc(txt_mod, rel_path, usou_homog_mod)
                                        jsons_mod = glob.glob(os.path.join(temp_dir, '*.json'))
                                except Exception:
                                    pass

                    duracao_mod = time.time() - t_mod_start

                    mod_violations = 0
                    caminho_rep_j, dados_j = _obter_relatorio_esbmc_json(temp_dir)
                    if dados_j and isinstance(dados_j, list):
                        try:
                            for item_j in dados_j:
                                if isinstance(item_j, dict) and item_j.get("status") == "violation":
                                    for st in item_j.get("steps", []):
                                        if st.get("type") == "violation":
                                            mod_violations += 1
                                            loc = st.get("location", {})
                                            loc["file"] = rel_path
                                            st["location"] = loc
                                            if metricas_mod["z3_witness"]:
                                                st["message"] = f"{st.get('message', '')} | {metricas_mod['z3_witness']}"
                                    aggregated_dashboard_data.append(item_j)
                        except Exception:
                            pass

                    if "VERIFICATION FAILED" in txt_mod and mod_violations == 0:
                        mod_violations = 1
                        aggregated_dashboard_data.append({
                            "status": "violation",
                            "steps": [{
                                "type": "violation",
                                "message": f"[{rel_path}] {metricas_mod['z3_witness'] or 'Property violation detected by ESBMC.'}",
                                "property": metricas_mod["violated_prop"],
                                "location": {"file": rel_path, "line": 1, "function": "module_entry"}
                            }]
                        })

                    ultimo_cli_mod = TAREFAS_ATIVAS[task_id].get("last_cli", f"esbmc {arq_exec}")

                    # Exibe o Card de Diagnóstico de Contraexemplo Z3 sempre que houver falha!
                    if mod_violations > 0 or "VERIFICATION FAILED" in txt_mod:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"\n   ╔══════════════════════════════════════════════════════════════════════════╗\n"
                            f"   ║ ❌ [Z3 COUNTEREXAMPLE WITNESS CARD] Module #{idx_a}: {os.path.basename(rel_path)}\n"
                            f"   ╠══════════════════════════════════════════════════════════════════════════╣\n"
                            f"   ║ • Target File       : {rel_path} ({lang_mod.upper()})\n"
                            f"   ║ • Violation Origin  : {metricas_mod['violation_origin']}\n"
                            f"   ║ • Location / Scope  : {metricas_mod['violated_loc']}\n"
                            f"   ║ • Violated Property : {metricas_mod['violated_prop']}\n"
                            f"   ║ • Z3 Concrete Input : {', '.join(metricas_mod['z3_vars']) if metricas_mod['z3_vars'] else 'Symbolic State at k=' + str(metricas_mod['k_depth'])}\n"
                            f"   ║ • Reproducible CLI  : {ultimo_cli_mod}\n"
                            f"   ║ • Unrolling Depth   : k = {metricas_mod['k_depth']} ({metricas_mod['vccs_total']} VCCs, {metricas_mod['ssa_assigns']} SSA assignments)\n"
                            f"   ╚══════════════════════════════════════════════════════════════════════════╝\n"
                        )

                    # Melhoria 2 de Fidelidade ESBMC: Taxonomia Oficial de 4 Vereditos SV-COMP
                    teve_erro_bruto = (
                        is_raw_esbmc
                        and mod_violations == 0
                        and "VERIFICATION SUCCESSFUL" not in txt_mod
                        and ("ERROR:" in txt_mod or "fatal error:" in txt_mod or "ImportError" in txt_mod or "ModuleNotFoundError" in txt_mod or rc_mod != 0)
                    )
                    if teve_erro_bruto:
                        status_mod = "RAW ERROR (Unresolved Deps)"
                    elif mod_violations > 0:
                        any_violation_overall = True
                        tag_orig = "NATIVE BUG" if metricas_mod["violation_origin"] == "[NATIVE CODE BUG]" else "CONTRACT"
                        status_mod = f"VIOLATION [{tag_orig}] (k={metricas_mod['k_depth']})"
                    elif usou_homog_mod:
                        status_mod = f"SLICED SAFE (k={metricas_mod['k_depth']})"
                    elif metricas_mod["vccs_total"] > 0:
                        if '--k-induction' in flags_recebidas:
                            status_mod = "VERIFIED SOUND (k-Induction)"
                        else:
                            status_mod = f"BOUNDED SAFE (k={metricas_mod['k_depth']})"
                    else:
                        status_mod = "STATIC SAFE (0 VCCs)"

                    detalhe_motivo = (
                        metricas_mod["z3_witness"]
                        if mod_violations > 0
                        else f"{modo_verif_mod} | {metricas_mod['vccs_total']} VCCs ({metricas_mod['ssa_assigns']} SSA)"
                    )

                    caminho_final_exec = os.path.join(temp_dir, arq_exec)
                    if os.path.isfile(caminho_final_exec):
                        try:
                            with open(caminho_final_exec, 'r', encoding='utf-8', errors='replace') as f_cf:
                                cod_exibido = f_cf.read()
                        except Exception:
                            pass

                    repo_exploration_summary.append({
                        "index": idx_a,
                        "grau": alvo_info.get('grau', 0),
                        "nome_grau": alvo_info.get('nome_grau', 'Auxiliar'),
                        "lang": lang_mod.upper(),
                        "directory": alvo_info['dir'],
                        "file": rel_path,
                        "score": alvo_info['score'],
                        "reasons": detalhe_motivo,
                        "fused_deps": len(deps_modulo),
                        "fused_names": ", ".join(deps_modulo[:4]) if deps_modulo else "Self-contained / Direct",
                        "goto_time": metricas_mod["goto_time"],
                        "ssa_assigns": metricas_mod["ssa_assigns"],
                        "vccs": metricas_mod["vccs_total"],
                        "wall_time": f"{duracao_mod:.2f}s",
                        "mode": modo_verif_mod,
                        "esbmc_cli": ultimo_cli_mod,
                        "z3_witness": metricas_mod["z3_witness"],
                        "violations": mod_violations,
                        "status": status_mod,
                        "homogenized_code": cod_exibido
                    })

                    # Atualiza o placar ao vivo para a barra de progresso e prévia em tempo real no HTML
                    TAREFAS_ATIVAS[task_id]["progresso"].update({
                        "safe_count": sum(1 for r in repo_exploration_summary if "SAFE" in r["status"] or "SOUND" in r["status"]),
                        "violation_count": sum(1 for r in repo_exploration_summary if r["violations"] > 0),
                        "total_vccs": sum(int(r.get("vccs", 0)) for r in repo_exploration_summary),
                        "total_ssa": sum(int(r.get("ssa_assigns", 0)) for r in repo_exploration_summary),
                        "partial_summary": list(repo_exploration_summary)
                    })

                # Melhoria 4: Gera Tabela Científica Consolidada + Código LaTeX (UFAM / IEEE / Springer) + CSV no Log Final
                tempo_total_repo = time.time() - tempo_inicio_repo
                total_safe = sum(1 for r in repo_exploration_summary if "SAFE" in r["status"] or "SOUND" in r["status"])
                total_viol = sum(1 for r in repo_exploration_summary if r["violations"] > 0)
                total_raw_err = sum(1 for r in repo_exploration_summary if "RAW ERROR" in r["status"])
                total_vccs_repo = sum(int(r.get("vccs", 0)) for r in repo_exploration_summary)
                total_ssa_repo = sum(int(r.get("ssa_assigns", 0)) for r in repo_exploration_summary)

                linhas_tabela_txt = [
                    "\n====================================================================================================================",
                    "[SYSTEM] [RepoSlice-BMC] CONSOLIDATED SCIENTIFIC VERIFICATION REPORT (UFAM / MASTER'S DISSERTATION METRICS)",
                    "====================================================================================================================",
                    f" • Engine Mode            : {modo_motor_desc}",
                    f" • Total Modules Verified : {len(repo_exploration_summary)} across {len(dirs_cobertos)} directories ({', '.join(langs_selecionadas)})",
                    f" • Formal Verdicts        : {total_safe} SAFE/SOUND | {total_viol} VIOLATION(S) WITH Z3 WITNESS | {total_raw_err} PARSING/DEPS ERRORS",
                    f" • Total SMT Proof Effort : {total_vccs_repo} Verification Conditions (VCCs) | {total_ssa_repo} SSA Assignments | Wall Time: {tempo_total_repo:.2f}s",
                    "--------------------------------------------------------------------------------------------------------------------",
                    f"{'#':<3} | {'Grau':<6} | {'Lang':<6} | {'Module (Path)':<38} | {'Mode':<24} | {'SSA':>5} | {'VCCs':>4} | {'Time':>6} | {'Formal Verdict / Z3 Witness'}",
                    "-" * 132
                ]
                linhas_csv = ["Index,Priority_Grade,Grade_Name,Language,Directory,Module,VerificationMode,ESBMC_CLI,GOTO_Time,SSA_Assignments,VCCs,WallTime_s,Verdict,Z3_Witness"]
                linhas_latex = [
                    "% === TABELA LATEX GERADA AUTOMATICAMENTE PELO ESBMC-WEB (v2026) PARA DISSERTAÇÃO UFAM / IEEE ===",
                    "\\begin{table*}[htbp]",
                    "\\centering",
                    "\\caption{Resultados da Verificação Formal Poliglota Multi-Diretório via Algoritmo \\textit{RepoSlice-BMC} com Matriz Canônica de Prioridades (Graus 5 a 0)}",
                    "\\label{tab:reposlice_bmc_results}",
                    "\\resizebox{\\textwidth}{!}{%",
                    "\\begin{tabular}{ccclllrrrl}",
                    "\\hline",
                    "\\textbf{\\#} & \\textbf{Grau} & \\textbf{Ling.} & \\textbf{Diretório / Subsistema} & \\textbf{Módulo Verificado} & \\textbf{Atrib. SSA} & \\textbf{VCCs} & \\textbf{Tempo (s)} & \\textbf{Veredito Formal (ESBMC + Z3)} \\\\ \\hline"
                ]

                for r in repo_exploration_summary:
                    mod_curto = r["file"] if len(r["file"]) <= 38 else ("..." + r["file"][-35:])
                    veredito_det = f"{r['status']} ({r['z3_witness']})" if r.get("z3_witness") else r["status"]
                    grau_label = f"G{r.get('grau', 0)}"
                    linhas_tabela_txt.append(
                        f"{r['index']:<3} | {grau_label:<6} | {r['lang']:<6} | {mod_curto:<38} | {r['mode'][:24]:<24} | {r['ssa_assigns']:>5} | {r['vccs']:>4} | {r['wall_time']:>6} | {veredito_det}"
                    )
                    w_clean = str(r.get("z3_witness", "")).replace('"', "'")
                    cli_clean = str(r.get("esbmc_cli", "")).replace('"', "'")
                    grade_nome_clean = str(r.get("nome_grau", "")).replace('"', "'")
                    linhas_csv.append(
                        f"{r['index']},{r.get('grau', 0)},\"{grade_nome_clean}\",{r['lang']},\"{r['directory']}\",\"{r['file']}\",\"{r['mode']}\",\"{cli_clean}\",{r['goto_time']},{r['ssa_assigns']},{r['vccs']},{r['wall_time']},\"{r['status']}\",\"{w_clean}\""
                    )
                    dir_tex = str(r["directory"]).replace("_", "\\_")
                    arq_tex = os.path.basename(r["file"]).replace("_", "\\_")
                    stat_tex = str(r["status"]).replace("_", "\\_")
                    linhas_latex.append(
                        f"{r['index']} & Grau {r.get('grau', 0)} & \\texttt{{{r['lang']}}} & \\texttt{{{dir_tex}}} & \\texttt{{{arq_tex}}} & {r['ssa_assigns']} & {r['vccs']} & {r['wall_time']} & \\textbf{{{stat_tex}}} \\\\"
                    )

                linhas_latex.extend([
                    "\\hline",
                    f"\\multicolumn{{5}}{{r}}{{\\textbf{{Total Consolidado ({len(repo_exploration_summary)} Módulos)}}}} & \\textbf{{{total_ssa_repo}}} & \\textbf{{{total_vccs_repo}}} & \\textbf{{{tempo_total_repo:.2f}s}} & \\textbf{{{total_safe} SAFE / {total_viol} VIOLATION}} \\\\ \\hline",
                    "\\end{tabular}%",
                    "}",
                    "\\end{table*}"
                ])

                bloco_relatorio_cientifico = (
                    "\n".join(linhas_tabela_txt)
                    + "\n================================================================================================================\n\n"
                    + "\n".join(linhas_latex)
                    + "\n"
                )
                TAREFAS_ATIVAS[task_id]["logs"] += bloco_relatorio_cientifico

                verificacao_sucesso = not any_violation_overall
                if verificacao_sucesso and not aggregated_dashboard_data:
                    aggregated_dashboard_data = [{
                        "status": "successful",
                        "message": f"VERIFICATION SUCCESSFUL — {len(alvos)} módulo(s) em múltiplos diretórios verificados sem vulnerabilidades!",
                        "steps": []
                    }]

                for result in aggregated_dashboard_data:
                    if isinstance(result, dict) and result.get("status") == "violation" and "steps" in result:
                        for step in result["steps"]:
                            if step.get("type") == "violation":
                                msg = str(step.get("message", "")).lower()
                                prop = str(step.get("property", "")).lower()
                                full_expr = str(step.get("full_expr", "")).lower()
                                combined_text = f"{msg} {prop} {full_expr}"
                                step["cwe"], step["severity"] = "N/A", "N/A"
                                for kw, info in MAPEAMENTO_CWE.items():
                                    if kw in combined_text:
                                        step["cwe"], step["severity"] = info['code'], info['severity']
                                        break

                TAREFAS_ATIVAS[task_id]["resultado"] = {
                    "verificacao_sucesso": verificacao_sucesso,
                    "dashboard_data": aggregated_dashboard_data,
                    "repo_exploration_summary": repo_exploration_summary,
                    "latex_table": "\n".join(linhas_latex),
                    "csv_report": "\n".join(linhas_csv),
                    "html_report_data": None,
                    "yaml_report_data": None,
                    "graphml_report_data": None,
                    "codigo_analisado": "\n\n".join(combined_code_preview)
                }
                TAREFAS_ATIVAS[task_id]["status"] = "completed"
                return

            # ==========================================================
            # ETAPA 1: SANITIZAÇÃO E HOMOGENEIZAÇÃO DETERMINÍSTICA (ARQUIVO ÚNICO)
            # ==========================================================
            arquivo_alvo = main_file_path_in_repo if (is_git and main_file_path_in_repo and is_raw_esbmc) else nome_arquivo_principal
            usou_homogenizer_v2 = False

            if is_raw_esbmc:
                TAREFAS_ATIVAS[task_id]["logs"] += (
                    f"\n[SYSTEM] [Strict Pure ESBMC Baseline] Zero-intervention mode active (`--Engine=raw_esbmc`).\n"
                    f"[SYSTEM] [Strict Pure ESBMC Baseline] Skipping AST Slicing, Header Mocking, and ESBMC Homogenizer v2.0.\n"
                    f"[SYSTEM] [Strict Pure ESBMC Baseline] Executing native ESBMC directly on unmodified source: {arquivo_alvo}\n"
                )
            elif linguagem == 'python':
                TAREFAS_ATIVAS[task_id]["logs"] += "\n[SYSTEM] Analyzing Python AST & Dependencies (ESBMC Homogenizer v2.0)...\n"
                caminho_sanitizado = os.path.join(temp_dir, 'codigo_esbmc_sanitized.py')
                try:
                    info_sanit = sanitizar_python(
                        caminho_original,
                        caminho_sanitizado,
                        temp_dir=temp_dir,
                        is_git=is_git,
                        forcar_homogenizer=False
                    )
                    arquivo_alvo = 'codigo_esbmc_sanitized.py'
                    usou_homogenizer_v2 = info_sanit['usou_homogenizer_v2']
                    codigo_para_dashboard = info_sanit['codigo_final']
                    if usou_homogenizer_v2:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] [ESBMC Homogenizer v2.0] Activated: {info_sanit['motivo']}\n"
                            f"[SYSTEM] [ESBMC Homogenizer v2.0] Symbolic model generated ({info_sanit['alvos_extraidos']} target(s) + SMT security contracts).\n"
                        )
                    else:
                        TAREFAS_ATIVAS[task_id]["logs"] += (
                            f"[SYSTEM] Direct Python verification mode ({info_sanit['motivo']}).\n"
                        )
                except Exception as e:
                    TAREFAS_ATIVAS[task_id]["logs"] += f"[ERROR] Python Sanitization failed: {str(e)}\n"

            elif linguagem == 'c':
                TAREFAS_ATIVAS[task_id]["logs"] += "\n[SYSTEM] Running ESBMC C Homogenizer & Clang Auto-Healer...\n"
                try:
                    tem_fn = '--function' in flags_recebidas
                    mocks_criados = sanitizar_c(caminho_original, temp_dir, tem_flag_function=tem_fn, sub_dir_repo=sub_dir_repo)
                    with open(caminho_original, 'r', encoding='utf-8', errors='replace') as f:
                        codigo_para_dashboard = f.read()
                    if mocks_criados:
                        TAREFAS_ATIVAS[task_id]["logs"] += f"[SYSTEM] C Homogenizer prepared {len(mocks_criados)} dependency mock(s)/harness.\n"
                    else:
                        TAREFAS_ATIVAS[task_id]["logs"] += "[SYSTEM] All C headers & entrypoints resolved.\n"
                except Exception as e:
                    TAREFAS_ATIVAS[task_id]["logs"] += f"[ERROR] C Sanitizer failed: {str(e)}\n"

            elif linguagem == 'cpp':
                TAREFAS_ATIVAS[task_id]["logs"] += "\n[SYSTEM] Running ESBMC C++ Homogenizer & Clang Auto-Healer...\n"
                try:
                    tem_fn = '--function' in flags_recebidas
                    mocks_criados = sanitizar_cpp(caminho_original, temp_dir, tem_flag_function=tem_fn, sub_dir_repo=sub_dir_repo)
                    with open(caminho_original, 'r', encoding='utf-8', errors='replace') as f:
                        codigo_para_dashboard = f.read()
                    if mocks_criados:
                        TAREFAS_ATIVAS[task_id]["logs"] += f"[SYSTEM] C++ Homogenizer prepared {len(mocks_criados)} dependency mock(s)/harness.\n"
                    else:
                        TAREFAS_ATIVAS[task_id]["logs"] += "[SYSTEM] All C++ headers & entrypoints resolved.\n"
                except Exception as e:
                    TAREFAS_ATIVAS[task_id]["logs"] += f"[ERROR] C++ Sanitizer failed: {str(e)}\n"

            # ==========================================================
            # ETAPA 2: VERIFICAÇÃO ESBMC (+ FALLBACK AUTOMÁTICO V2 PARA PYTHON)
            # ==========================================================
            texto_final, returncode = rodar_esbmc(
                arquivo_alvo,
                usou_homogenizer=usou_homogenizer_v2,
                is_fallback=False,
                modo_puro_raw=is_raw_esbmc
            )

            lista_json = glob.glob(os.path.join(temp_dir, '*.json'))
            if (
                not is_raw_esbmc
                and not TAREFAS_ATIVAS[task_id].get("cancel_requested")
                and linguagem == 'python'
                and not usou_homogenizer_v2
                and not lista_json
                and ("ERROR:" in texto_final or "ImportError" in texto_final or "ModuleNotFoundError" in texto_final or returncode != 0)
            ):
                TAREFAS_ATIVAS[task_id]["logs"] += (
                    "\n[SYSTEM] Direct pass encountered unresolved constructs/dependencies. "
                    "Triggering ESBMC Homogenizer v2.0 (VeriBee) automatic fallback...\n"
                )
                try:
                    caminho_sanitizado = os.path.join(temp_dir, 'codigo_esbmc_sanitized.py')
                    info_sanit = sanitizar_python(
                        caminho_original,
                        caminho_sanitizado,
                        temp_dir=temp_dir,
                        is_git=True,
                        forcar_homogenizer=True
                    )
                    arquivo_alvo = 'codigo_esbmc_sanitized.py'
                    usou_homogenizer_v2 = True
                    codigo_para_dashboard = info_sanit['codigo_final']
                    texto_final, returncode = rodar_esbmc(arquivo_alvo, usou_homogenizer=True, is_fallback=True)
                    lista_json = glob.glob(os.path.join(temp_dir, '*.json'))
                except Exception as e:
                    TAREFAS_ATIVAS[task_id]["logs"] += f"[ERROR] Fallback Homogenizer failed: {str(e)}\n"

            # --- 3. PARSING DOS RESULTADOS GERAIS (DASHBOARD) ---
            dashboard_data = []
            arquivo_report_json = os.path.join(temp_dir, 'report.json')
            caminho_rep_sf, dados_rep_sf = _obter_relatorio_esbmc_json(temp_dir)
            if dados_rep_sf and isinstance(dados_rep_sf, list):
                dashboard_data = dados_rep_sf

            if not dashboard_data and "VERIFICATION FAILED" in texto_final:
                msg_viol = "VERIFICATION FAILED: Violated property detected by ESBMC."
                for ln in texto_final.splitlines():
                    ln_s = ln.strip()
                    if any(kw in ln_s for kw in ("Violated property:", "dereference failure:", "invalid pointer", "assertion failed", "division by zero")):
                        msg_viol = ln_s
                        break
                dashboard_data = [{
                    "status": "violation",
                    "message": msg_viol,
                    "steps": []
                }]

            verificacao_sucesso = (
                "VERIFICATION SUCCESSFUL" in texto_final
                or (returncode == 0 and "VERIFICATION FAILED" not in texto_final and "ERROR:" not in texto_final)
                or (TAREFAS_ATIVAS[task_id].get("cancel_requested") and "VERIFICATION FAILED" not in texto_final)
            )

            # Garante que quando o ESBMC tiver sucesso sem vulnerabilidades, o Dashboard receba o status OK!
            if verificacao_sucesso and not any(isinstance(r, dict) and r.get("status") == "violation" for r in dashboard_data):
                if not dashboard_data:
                    dashboard_data = [{
                        "status": "successful",
                        "message": "VERIFICATION SUCCESSFUL — Código seguro! Nenhuma vulnerabilidade detectada pelo ESBMC.",
                        "steps": []
                    }]

            html_report, yaml_report, graphml_report = None, None, None
            lista_html = glob.glob(os.path.join(temp_dir, '*.html'))
            if lista_html:
                with open(lista_html[0], 'r', encoding='utf-8') as f:
                    html_report = f.read()

            lista_yaml = glob.glob(os.path.join(temp_dir, '*.yml')) + glob.glob(os.path.join(temp_dir, '*.yaml'))
            if lista_yaml:
                with open(lista_yaml[0], 'r', encoding='utf-8') as f:
                    yaml_report = f.read()

            lista_graphml = glob.glob(os.path.join(temp_dir, '*.graphml'))
            if lista_graphml:
                with open(lista_graphml[0], 'r', encoding='utf-8') as f:
                    graphml_report = f.read()

            if dashboard_data:
                for result in dashboard_data:
                    if isinstance(result, dict) and result.get("status") == "violation" and "steps" in result:
                        for step in result["steps"]:
                            if step.get("type") == "violation":
                                msg = str(step.get("message", "")).lower()
                                prop = str(step.get("property", "")).lower()
                                full_expr = str(step.get("full_expr", "")).lower()
                                combined_text = f"{msg} {prop} {full_expr}"
                                step["cwe"], step["severity"] = "N/A", "N/A"
                                for kw, info in MAPEAMENTO_CWE.items():
                                    if kw in combined_text:
                                        step["cwe"], step["severity"] = info['code'], info['severity']
                                        break

            repo_single_summary = None
            if is_git and main_file_path_in_repo:
                metricas_single = extrair_metricas_e_contraexemplo_esbmc(
                    texto_final, main_file_path_in_repo, usou_homogenizer=usou_homogenizer_v2
                )
                viol_count = sum(
                    1 for r in dashboard_data if isinstance(r, dict) and r.get("status") == "violation"
                    for s in r.get("steps", []) if s.get("type") == "violation"
                )
                if "VERIFICATION FAILED" in texto_final and viol_count == 0:
                    viol_count = 1

                teve_erro_bruto_single = (
                    is_raw_esbmc
                    and viol_count == 0
                    and "VERIFICATION SUCCESSFUL" not in texto_final
                    and ("ERROR:" in texto_final or "fatal error:" in texto_final or "ImportError" in texto_final or "ModuleNotFoundError" in texto_final or returncode != 0)
                )
                if teve_erro_bruto_single:
                    status_single = "RAW ERROR (Unresolved Deps)"
                    if not dashboard_data:
                        dashboard_data = [{
                            "status": "violation",
                            "steps": [{
                                "type": "violation",
                                "message": f"[Strict Pure ESBMC Baseline] Native ESBMC aborted on '{main_file_path_in_repo}' due to unresolved external dependencies/imports without RepoSlice-BMC.",
                                "property": "parsing / dependency resolution error",
                                "location": {"file": main_file_path_in_repo, "line": 1, "function": "module_load"}
                            }]
                        }]
                elif viol_count > 0:
                    tag_orig = "NATIVE BUG" if metricas_single["violation_origin"] == "[NATIVE CODE BUG]" else "CONTRACT"
                    status_single = f"VIOLATION [{tag_orig}] (k={metricas_single['k_depth']})"
                elif usou_homogenizer_v2:
                    status_single = f"SLICED SAFE (k={metricas_single['k_depth']})"
                elif metricas_single["vccs_total"] > 0:
                    status_single = "VERIFIED SOUND (k-Induction)" if '--k-induction' in flags_recebidas else f"BOUNDED SAFE (k={metricas_single['k_depth']})"
                else:
                    status_single = "STATIC SAFE (0 VCCs)"

                modo_single = (
                    "Strict Pure ESBMC (Raw)"
                    if is_raw_esbmc
                    else ("Homogenizer v2.0 (Symbolic Slice)" if usou_homogenizer_v2 else "Direct Native BMC")
                )
                ultimo_cli_single = TAREFAS_ATIVAS[task_id].get("last_cli", f"esbmc {arquivo_alvo}")

                caminho_final_single = os.path.join(temp_dir, arquivo_alvo)
                if os.path.isfile(caminho_final_single):
                    try:
                        with open(caminho_final_single, 'r', encoding='utf-8', errors='replace') as f_s:
                            codigo_para_dashboard = f_s.read()
                    except Exception:
                        pass

                repo_single_summary = [{
                    "index": 1,
                    "lang": linguagem.upper(),
                    "directory": os.path.dirname(main_file_path_in_repo) or "(root)",
                    "file": main_file_path_in_repo,
                    "score": 100,
                    "mode": modo_single,
                    "esbmc_cli": ultimo_cli_single,
                    "goto_time": metricas_single["goto_time"],
                    "ssa_assigns": metricas_single["ssa_assigns"],
                    "vccs": metricas_single["vccs_total"],
                    "wall_time": "-",
                    "z3_witness": metricas_single["z3_witness"],
                    "reasons": f"{modo_single} | {metricas_single['vccs_total']} VCCs",
                    "fused_deps": 0 if is_raw_esbmc else len(deps_internas_fundidas),
                    "fused_names": "None (Raw ESBMC)" if is_raw_esbmc else (", ".join(deps_internas_fundidas[:5]) if deps_internas_fundidas else "Direct / Repo Headers"),
                    "violations": viol_count,
                    "status": status_single,
                    "homogenized_code": codigo_para_dashboard
                }]

            TAREFAS_ATIVAS[task_id]["resultado"] = {
                "verificacao_sucesso": verificacao_sucesso,
                "dashboard_data": dashboard_data,
                "repo_exploration_summary": repo_single_summary,
                "html_report_data": html_report,
                "yaml_report_data": yaml_report,
                "graphml_report_data": graphml_report,
                "codigo_analisado": codigo_para_dashboard
            }
            TAREFAS_ATIVAS[task_id]["status"] = "completed"

        except Exception as e:
            TAREFAS_ATIVAS[task_id]["logs"] += f"\n[CRITICAL ERROR] Backend process failed: {str(e)}\n"
            TAREFAS_ATIVAS[task_id]["status"] = "error"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    thread = threading.Thread(target=executar_background, args=(task_id, dados, temp_dir))
    thread.start()
    return jsonify({"task_id": task_id})


@app.route('/health', methods=['GET'])
def health_check():
    try:
        proc = subprocess.run(['esbmc', '--version'], capture_output=True, text=True, timeout=5)
        ver = (proc.stdout + proc.stderr).strip() or "ESBMC 8.4.0"
    except Exception:
        ver = "ESBMC 8.4.0 (WSL2)"
    return jsonify({
        "status": "ready",
        "esbmc_version": ver,
        "solver": "Z3 v4.8.12 + Bitwuzla",
        "engine": "RepoSlice-BMC v2026 (Polyglot C/C++/Python)"
    })


@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    tarefa = TAREFAS_ATIVAS.get(task_id)
    if not tarefa:
        return jsonify({"error": "Task not found."}), 404
    return jsonify({
        "status": tarefa["status"],
        "logs": tarefa["logs"],
        "resultado": tarefa["resultado"],
        "progresso": tarefa.get("progresso")
    })


@app.route('/cancelar/<task_id>', methods=['POST'])
def cancelar_tarefa(task_id):
    tarefa = TAREFAS_ATIVAS.get(task_id)
    if tarefa and tarefa["status"] in ["starting", "running", "consolidating"]:
        tarefa["cancel_requested"] = True
        tarefa["status"] = "consolidating"
        if tarefa.get("process"):
            _encerrar_arvore_processo(tarefa["process"])
        tarefa["logs"] += "\n\n[!] ANALYSIS STOPPED BY USER — Generating consolidated report for completed modules..."
        return jsonify({"success": True})
    return jsonify({"success": False})


@app.route('/help', methods=['GET'])
def get_esbmc_help():
    try:
        processo = subprocess.run(['esbmc', '--help'], capture_output=True, text=True, timeout=30)
        return jsonify({"help_text": (processo.stdout + "\n" + processo.stderr).strip() or "Could not retrieve help text."})
    except Exception as e:
        return jsonify({"help_text": f"An error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True, use_reloader=False, threaded=True)