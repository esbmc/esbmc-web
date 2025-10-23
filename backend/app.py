from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import tempfile
import os
import glob
import json

FLAGS_PERMITIDAS_SIMPLES = {
     '--floatbv', '--k-induction', '--memory-leak-check',
    '--loop-invariant', '--overflow-check',
    '--data-races-check', '--deadlock-check',
    '--smt-during-symex', '--smt-thread-guard',
    '--smt-symex-guard', '--smt-symex-assert', '--smt-symex-assume',
    # NOVO: Adicionadas as flags de BMC Incremental
    '--incremental-bmc',
    '--falsification',
    '--termination'

     # NOVO: Adicionadas as flags dos solvers
    '--boolector',
    '--z3',
    '--cvc5',
    '--bitwuzla',
    '--mathsat',
    '--yices',

     '--no-standard-checks', '--no-assertions', '--no-bounds-check',
    '--no-div-by-zero-check', '--no-pointer-check', '--no-align-check', '--multi-property'
}
# ATUALIZADO: Adicionadas as novas flags que aceitam um valor
FLAGS_PERMITIDAS_COM_VALOR = {
    '--unwind', '--context-bound', '--witness-output', '--function', '--timeout'
}

app = Flask(__name__)
CORS(app)

@app.route('/analisar', methods=['POST'])
def analisar_codigo():
    dados = request.get_json()
    codigo_principal = dados.get('codigo', '')
    flags_recebidas = dados.get('flags', [])
    linguagem = dados.get('language', 'cpp')
    
    if not codigo_principal:
        return jsonify({'error': 'No main code was provided'}), 400 # TRADUZIDO

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            if linguagem == 'python':
                nome_arquivo_principal = 'codigo.py'
            else:
                extensao = '.cpp' if linguagem == 'cpp' else '.c'
                nome_arquivo_principal = 'codigo' + extensao

            caminho_arquivo_principal = os.path.join(temp_dir, nome_arquivo_principal)
            with open(caminho_arquivo_principal, 'w', encoding='utf-8') as f:
                f.write(codigo_principal)

            # Processa dependências para TODAS as linguagens (C, C++, Python)
            # Elas são salvas no temp_dir para que o ESBMC possa encontrá-las
            dependencias = dados.get('dependencies', [])
            for dep in dependencias:
                caminho_dep = os.path.join(temp_dir, dep['filename'])
                with open(caminho_dep, 'w', encoding='utf-8') as f:
                    f.write(dep['content'])

            comando = ['esbmc', nome_arquivo_principal]
            
            if linguagem == 'python':
                interpretador_python = dados.get('python_interpreter', '').strip()
                if interpretador_python:
                    comando.extend(['--python', interpretador_python])
            else:
                # Para C/C++, adicionamos os arquivos .c/.cpp ao comando
                for dep in dependencias:
                    if dep['filename'].endswith(('.c', '.cpp')):
                        comando.append(dep['filename'])

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

            # =========== MODIFICADO AQUI (Início) ===========
            # Crie uma cópia do ambiente atual
            env = os.environ.copy()
            
            # Adicione o temp_dir ao PYTHONPATH
            # Isso é crucial para o Python (e mypy) encontrar os módulos de dependência.
            existing_pythonpath = env.get('PYTHONPATH')
            if existing_pythonpath:
                # Usa os.pathsep para ser compatível com Windows (;) e Linux (:)
                env['PYTHONPATH'] = f"{temp_dir}{os.pathsep}{existing_pythonpath}"
            else:
                env['PYTHONPATH'] = temp_dir
            # =========== MODIFICADO AQUI (Fim) ===========
            
            # Aumentamos o timeout de segurança do servidor...
            processo = subprocess.run(
                comando, 
                capture_output=True, 
                text=True, 
                timeout=600, 
                cwd=temp_dir,
                env=env  # <-- MODIFICADO: Passa o novo ambiente para o subprocesso
            )

            texto_para_exibicao = (processo.stdout + "\n" + processo.stderr).strip()

            dashboard_data = []
            lista_json = glob.glob(os.path.join(temp_dir, '*.json'))
            if lista_json:
                caminho_json = lista_json[0]
                with open(caminho_json, 'r', encoding='utf-8') as f:
                    try:
                        dashboard_data = json.load(f)
                    except json.JSONDecodeError:
                        pass

            if not dashboard_data and "VERIFICATION FAILED" in texto_para_exibicao:
                dashboard_data = [{
                    "status": "violation",
                    "steps": [{
                        "type": "violation",
                        "file": "N/A", "function": "N/A", "line": "N/A",
                        "message": "Verification failed, but ESBMC did not generate a detailed report. Check the 'Text Output' for more details." # TRADUZIDO
                    }]
                }]

            return jsonify({
                "resultado_texto": texto_para_exibicao,
                "dashboard_data": dashboard_data,
                "codigo_analisado": codigo_principal
            })

        except subprocess.TimeoutExpired:
            return jsonify({"raw_text_error": "ERROR: Analysis exceeded the server's security timeout (600s)."}), 500 # TRADUZIDO
        except Exception as e:
            return jsonify({"error": "Backend process failed.", "details": str(e)}), 500 # TRADUZIDO

if __name__ == '__main__':
    app.run(debug=True)
