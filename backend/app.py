from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import tempfile
import os
import glob
import json
import git # Importa a biblioteca GitPython

FLAGS_PERMITIDAS_SIMPLES = {
     '--floatbv', '--k-induction', '--memory-leak-check',
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
    '--no-div-by-zero-check', '--no-pointer-check', '--no-align-check', '--multi-property'
}
FLAGS_PERMITIDAS_COM_VALOR = {
    '--unwind', '--context-bound', '--witness-output', '--function', '--timeout',
    '--witness-output-yaml' 
}

app = Flask(__name__)
CORS(app)

# --- ENDPOINT DE LISTAGEM DE ARQUIVOS (Inalterado) ---
@app.route('/fetch-repo-files', methods=['POST'])
def fetch_repo_files():
    dados = request.get_json()
    git_url = dados.get('git_url')

    if not git_url:
        return jsonify({'error': 'No Git URL provided.'}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Otimização: depth=1 faz um "shallow clone" (superficial)
            git.Repo.clone_from(git_url, temp_dir, depth=1)
        except Exception as e:
            return jsonify({'error': f"Failed to clone repository: {str(e)}"}), 500

        file_list = []
        # Extensões que nos interessam
        extensions = ('.c', '.cpp', '.py', '.h', '.hpp')

        # Escaneia o diretório
        for root, dirs, files in os.walk(temp_dir):
            # Impede o os.walk de entrar no diretório .git
            if '.git' in dirs:
                dirs.remove('.git')
                
            for file in files:
                if file.endswith(extensions):
                    # Pega o caminho completo (ex: /tmp/xyz/src/main.c)
                    full_path = os.path.join(root, file)
                    # Converte para o caminho relativo (ex: src/main.c)
                    relative_path = os.path.relpath(full_path, temp_dir)
                    # Converte para o formato de barra (Linux)
                    file_list.append(relative_path.replace(os.path.sep, '/'))
        
        return jsonify({'files': file_list})

# --- NOVO ENDPOINT (PARA BUSCAR CONTEÚDO DE ARQUIVO) ---
@app.route('/fetch-file-content', methods=['POST'])
def fetch_file_content():
    dados = request.get_json()
    git_url = dados.get('git_url')
    file_path = dados.get('file_path')

    if not git_url or not file_path:
        return jsonify({'error': 'Git URL or file path missing.'}), 400
    
    # Validação de segurança simples
    if '..' in file_path or file_path.startswith('/'):
        return jsonify({'error': 'Invalid file path.'}), 400

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Otimização: depth=1, não precisamos do histórico
            git.Repo.clone_from(git_url, temp_dir, depth=1)
        except Exception as e:
            return jsonify({'error': f"Failed to clone repository: {str(e)}"}), 500
        
        # Constrói o caminho completo para o arquivo
        full_file_path = os.path.join(temp_dir, file_path)

        if not os.path.exists(full_file_path):
            return jsonify({'error': 'File not found in repository.'}), 404
        
        try:
            # Lê o conteúdo do arquivo
            with open(full_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({'content': content})
        except Exception as e:
            return jsonify({'error': f"Failed to read file content: {str(e)}"}), 500
# --- FIM DO NOVO ENDPOINT ---


# --- ENDPOINT DE ANÁLISE (Otimizado e Corrigido) ---
@app.route('/analisar', methods=['POST'])
def analisar_codigo():
    dados = request.get_json()
    
    git_url = dados.get('git_url')
    main_file_path_in_repo = dados.get('main_file_path') 
    
    flags_recebidas = dados.get('flags', [])
    linguagem = dados.get('language', 'cpp')
    
    codigo_para_dashboard = ""

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            nome_arquivo_principal = ""
            dependencias = [] 
            
            # --- FLUXO 1: GIT ---
            if git_url and main_file_path_in_repo:
                
                if '..' in main_file_path_in_repo or main_file_path_in_repo.startswith('/'):
                     return jsonify({'error': 'Invalid main file path.'}), 400
                
                try:
                    # Otimização: depth=1 (shallow) e recursive=True (pega submodulos)
                    git.Repo.clone_from(git_url, temp_dir, depth=1, recursive=True)
                except Exception as e:
                    return jsonify({'error': f"Failed to clone Git repository: {str(e)}"}), 500
                
                nome_arquivo_principal = main_file_path_in_repo 
                caminho_arquivo_principal_completo = os.path.join(temp_dir, nome_arquivo_principal)
                
                if not os.path.exists(caminho_arquivo_principal_completo):
                    return jsonify({'error': f"Main file '{main_file_path_in_repo}' not found in the repository."}), 400
                
                # Lê o código do arquivo principal para enviar de volta ao dashboard
                # (O frontend já terá esse código, mas é bom para o dashboard)
                with open(caminho_arquivo_principal_completo, 'r', encoding='utf-8') as f:
                    codigo_para_dashboard = f.read()

            # --- FLUXO 2: CÓDIGO LOCAL (Inalterado) ---
            else:
                codigo_principal = dados.get('codigo', '')
                if not codigo_principal:
                    return jsonify({'error': 'No main code was provided (and no Git URL).'}), 400
                
                codigo_para_dashboard = codigo_principal

                if linguagem == 'python':
                    nome_arquivo_principal = 'codigo.py'
                else:
                    extensao = '.cpp' if linguagem == 'cpp' else '.c'
                    nome_arquivo_principal = 'codigo' + extensao

                caminho_arquivo_principal = os.path.join(temp_dir, nome_arquivo_principal)
                with open(caminho_arquivo_principal, 'w', encoding='utf-8') as f:
                    f.write(codigo_principal)

                dependencias = dados.get('dependencies', [])
                for dep in dependencias:
                    caminho_dep = os.path.join(temp_dir, dep['filename'])
                    with open(caminho_dep, 'w', encoding='utf-8') as f:
                        f.write(dep['content'])

            # --- LÓGICA COMUM (Construção do Comando) ---
            
            comando = ['esbmc', nome_arquivo_principal]
            
            # --- CORREÇÃO PYTHON (Inalterada desta vez) ---
            if linguagem == 'python':
                interpretador_python = dados.get('python_interpreter', '').strip()
                if not interpretador_python:
                    interpretador_python = 'python3' 
                comando.extend(['--python', interpretador_python])
            # --- FIM DA CORREÇÃO ---
            else:
                if not (git_url and main_file_path_in_repo):
                    for dep in dependencias:
                        if dep['filename'].endswith(('.c', '.cpp')):
                            comando.append(dep['filename'])

            # Processamento de Flags (Inalterado)
            i = 0
            while i < len(flags_recebidas):
                flag = flags_recebidas[i]
                if flag in FLAGS_PERMITIDAS_SIMPLES:
                    comando.append(flag)
                    i += 1
                elif flag in FLAGS_PERMITIDAS_COM_VALOR:
                    if (i + 1) < len(flags_recebidas):
                        valor = flags_recebidas[i+1]
                        comando.extend([flag, valor])
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1

            comando.append('--generate-json-report')

            # Configuração do Ambiente (Inalterado)
            env = os.environ.copy()
            existing_pythonpath = env.get('PYTHONPATH')
            if existing_pythonpath:
                env['PYTHONPATH'] = f"{temp_dir}{os.pathsep}{existing_pythonpath}"
            else:
                env['PYTHONPATH'] = temp_dir
            
            # Execução do Subprocesso (Inalterado)
            processo = subprocess.run(
                comando, 
                capture_output=True, 
                text=True, 
                timeout=600, 
                cwd=temp_dir,
                env=env
            )

            texto_para_exibicao = (processo.stdout + "\n" + processo.stderr).strip()

            # Lógica de processamento de resultados (Inalterada)
            dashboard_data = []
            lista_json = glob.glob(os.path.join(temp_dir, '*.json'))
            if lista_json:
                caminho_json = lista_json[0]
                with open(caminho_json, 'r', encoding='utf-8') as f:
                    try:
                        dashboard_data = json.load(f)
                    except json.JSONDecodeError:
                        pass
            
            html_report_content = None
            lista_html = glob.glob(os.path.join(temp_dir, '*.html'))
            if lista_html:
                caminho_html = lista_html[0]
                with open(caminho_html, 'r', encoding='utf-8') as f:
                    html_report_content = f.read()

            yaml_report_content = None
            lista_yaml = glob.glob(os.path.join(temp_dir, '*.yml')) + glob.glob(os.path.join(temp_dir, '*.yaml'))
            if lista_yaml:
                caminho_yaml = lista_yaml[0]
                with open(caminho_yaml, 'r', encoding='utf-8') as f:
                    yaml_report_content = f.read()

            graphml_report_content = None
            lista_graphml = glob.glob(os.path.join(temp_dir, '*.graphml'))
            if lista_graphml:
                caminho_graphml = lista_graphml[0]
                with open(caminho_graphml, 'r', encoding='utf-8') as f:
                    graphml_report_content = f.read()

            if not dashboard_data and "VERIFICATION FAILED" in texto_para_exibicao:
                dashboard_data = [{
                    "status": "violation",
                    "steps": [{
                        "type": "violation",
                        "file": "N/A", "function": "N/A", "line": "N/A",
                        "message": "Verification failed, but ESBMC did not generate a detailed report. Check the 'Text Output' for more details."
                    }]
                }]

            return jsonify({
                "resultado_texto": texto_para_exibicao,
                "dashboard_data": dashboard_data,
                "html_report_data": html_report_content, 
                "yaml_report_data": yaml_report_content,
                "graphml_report_data": graphml_report_content,
                "codigo_analisado": codigo_para_dashboard
            })

        except subprocess.TimeoutExpired:
            return jsonify({"raw_text_error": "ERROR: Analysis exceeded the server's security timeout (600s)."}), 500
        except Exception as e:
            return jsonify({"error": "Backend process failed.", "details": str(e)}), 500

# =========== ENDPOINT DE AJUDA (Inalterado) ===========
@app.route('/help', methods=['GET'])
def get_esbmc_help():
    try:
        processo = subprocess.run(
            ['esbmc', '--help'], 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        
        help_text = (processo.stdout + "\n" + processo.stderr).strip()
        
        if not help_text:
            help_text = "Could not retrieve help text from ESBMC. Is it installed and in PATH?"
        
        return jsonify({"help_text": help_text})

    except FileNotFoundError:
        return jsonify({"help_text": "ERROR: 'esbmc' command not found. Make sure it is installed and in your system's PATH."}), 500
    except Exception as e:
        return jsonify({"help_text": f"An error occurred: {str(e)}"}), 500
# ===============================================

if __name__ == '__main__':
    app.run(debug=True)
