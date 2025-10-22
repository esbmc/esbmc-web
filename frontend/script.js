document.addEventListener('DOMContentLoaded', () => {
    // --- Variáveis Globais e Constantes ---
    const analisarBtn = document.getElementById('analisarBtn');
    const esbmcFlags = document.querySelectorAll('.esbmc-flag');
    const esbmcParams = document.querySelectorAll('.esbmc-param');
    const languageRadios = document.querySelectorAll('input[name="language"]');
    const pythonOptions = document.getElementById('python-options');
    const cCppDependencies = document.getElementById('c-cpp-dependencies');
    const dependencyListContainer = document.getElementById('dependency-files-list-container');
    
    // --- Variáveis dos Botões do Editor ---
    const btnLimparEditor = document.getElementById('btnLimparEditor');
    const btnSelecionarTudo = document.getElementById('btnSelecionarTudo');
    const btnCopiarCodigo = document.getElementById('btnCopiarCodigo');
    let dependencyFiles = []; // Array que armazena {filename, content}

    // --- NOVO: Variáveis das Abas e Resultados ---
    const tabsContainer = document.getElementById('tabs-container');
    const tabDashboard = document.getElementById('tab-dashboard');
    const tabRawText = document.getElementById('tab-raw-text');
    const dashboard = document.getElementById('dashboard-detalhado');
    const resultadoTextoContainer = document.getElementById('resultado-texto-container');
    const resultadoTexto = document.getElementById('resultado-texto');


    // --- Inicialização do Editor CodeMirror ---
    const editor = CodeMirror.fromTextArea(document.getElementById('codigoInput'), {
        lineNumbers: true,
        mode: 'text/x-c++src', // Modo padrão C++
        theme: 'dracula',
        indentUnit: 4,
    });

    // --- Funções de UI ---

    function toggleLanguageOptions() {
        const selectedLanguage = document.querySelector('input[name="language"]:checked').value;
        if (selectedLanguage === 'python') {
            pythonOptions.style.display = 'block';
            cCppDependencies.style.display = 'none';
            editor.setOption('mode', 'python');
        } else {
            pythonOptions.style.display = 'none';
            cCppDependencies.style.display = 'block';
            editor.setOption('mode', selectedLanguage === 'c' ? 'text/x-csrc' : 'text/x-c++src');
        }
    }

    function validateInputs() {
        const isCodePresent = editor.getValue().trim() !== '';
        let isOptionSelected = false;
        esbmcFlags.forEach(flag => { if (flag.checked) isOptionSelected = true; });
        esbmcParams.forEach(param => { if (param.value.trim() !== '') isOptionSelected = true; });
        
        const lang = document.querySelector('input[name="language"]:checked').value;
        if (lang === 'python') isOptionSelected = true;

        if (isCodePresent && (isOptionSelected || lang === 'python')) {
            analisarBtn.disabled = false;
            analisarBtn.textContent = 'Analyze';
        } else {
            analisarBtn.disabled = true;
            analisarBtn.textContent = 'Fill in the code and choose an option';
        }
    }
    
    function renderDependencyList() {
        dependencyListContainer.innerHTML = ''; // Limpa a lista atual
        dependencyFiles.forEach(file => {
            const tag = document.createElement('div');
            tag.className = 'dependency-tag';
            tag.textContent = file.filename;

            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-dependency-btn';
            removeBtn.innerHTML = '&times;'; // Símbolo 'x'
            removeBtn.title = `Remove ${file.filename}`;
            removeBtn.dataset.filename = file.filename;
            
            tag.appendChild(removeBtn);
            dependencyListContainer.appendChild(tag);
        });
    }

    // --- Event Listeners ---

    editor.on('change', validateInputs);
    document.querySelectorAll('.esbmc-flag, .esbmc-param').forEach(input => {
        const event = input.type === 'checkbox' || input.type === 'radio' ? 'change' : 'input';
        input.addEventListener(event, validateInputs);
    });


    // --- Listeners dos Botões do Editor ---
    
    btnLimparEditor.addEventListener('click', () => {
        editor.setValue(''); 
        editor.focus(); 
    });

    btnSelecionarTudo.addEventListener('click', () => {
        editor.execCommand('selectAll'); 
        editor.focus(); 
    });

    btnCopiarCodigo.addEventListener('click', async () => {
        const codigo = editor.getValue();
        if (codigo.trim() === '') return; 

        try {
            await navigator.clipboard.writeText(codigo);
            const originalText = btnCopiarCodigo.textContent;
            btnCopiarCodigo.textContent = 'Copied!';
            setTimeout(() => {
                btnCopiarCodigo.textContent = originalText;
            }, 2000); 

        } catch (err) {
            console.error('Failed to copy code: ', err);
            alert('Could not copy code.');
        }
    });

    languageRadios.forEach(radio => radio.addEventListener('change', () => {
        toggleLanguageOptions();
        validateInputs();
    }));

    document.getElementById('fileInput').addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) return;

        const fileName = file.name;
        const fileExtension = fileName.slice(fileName.lastIndexOf('.'));

        if (fileExtension === '.c') document.getElementById('lang-c').checked = true;
        else if (fileExtension === '.cpp') document.getElementById('lang-cpp').checked = true;
        else if (fileExtension === '.py') document.getElementById('lang-py').checked = true;
        else document.getElementById('lang-cpp').checked = true;
        
        toggleLanguageOptions();

        const reader = new FileReader();
        reader.onload = (e) => { 
            editor.setValue(e.target.result); 
            validateInputs(); 
        };
        reader.readAsText(file);
    });
    
    document.getElementById('dependencyInput').addEventListener('change', async (event) => {
        const files = Array.from(event.target.files);
        event.target.value = ''; 
        if (files.length === 0) return;
    
        const readPromises = files.map(file => {
            if (dependencyFiles.some(dep => dep.filename === file.name)) {
                return Promise.resolve(null); 
            }
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = (e) => resolve({ filename: file.name, content: e.target.result });
                reader.onerror = reject;
                reader.readAsText(file);
            });
        });
    
        const newFiles = (await Promise.all(readPromises)).filter(Boolean); 
        dependencyFiles.push(...newFiles);
        renderDependencyList();
    });

    dependencyListContainer.addEventListener('click', (event) => {
        if (event.target && event.target.classList.contains('remove-dependency-btn')) {
            const filenameToRemove = event.target.dataset.filename;
            dependencyFiles = dependencyFiles.filter(file => file.filename !== filenameToRemove);
            renderDependencyList();
        }
    });

    // --- NOVO: Listeners das Abas ---
    tabDashboard.addEventListener('click', () => {
        dashboard.style.display = 'block';
        resultadoTextoContainer.style.display = 'none';
        tabDashboard.classList.add('active');
        tabRawText.classList.remove('active');
    });

    tabRawText.addEventListener('click', () => {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'block';
        tabDashboard.classList.remove('active');
        tabRawText.classList.add('active');
    });


    // --- Listener Principal: Analisar ---
    document.getElementById('analisarBtn').addEventListener('click', async () => {
        const codigo = editor.getValue();
        const loadingOverlay = document.getElementById('loading-overlay');
        
        // (Variáveis das abas e resultados já estão definidas no escopo global)
        
        const linguagemSelecionada = document.querySelector('input[name="language"]:checked').value;
        const pythonInterpreter = document.getElementById('python-interpreter').value;

        const flags = [];
        document.querySelectorAll('.esbmc-flag:checked').forEach(cb => flags.push(cb.value));
        document.querySelectorAll('.esbmc-param').forEach(input => {
            if (input.value.trim()) {
                flags.push(input.dataset.flag);
                flags.push(input.value.trim());
            }
        });

        const selectedSolver = document.getElementById('solver-select').value;
        if (selectedSolver) {
            flags.push(selectedSolver);
        }

        // --- MODIFICADO: Esconde todos os resultados e abas antes de analisar ---
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        tabsContainer.style.display = 'none'; // Esconde as abas
        loadingOverlay.style.display = 'flex';
        analisarBtn.disabled = true;
        analisarBtn.textContent = 'Analyzing...';

        try {
            const requestBody = {
                codigo,
                flags,
                language: linguagemSelecionada,
                dependencies: dependencyFiles
            };

            if (linguagemSelecionada === 'python' && pythonInterpreter) {
                requestBody.python_interpreter = pythonInterpreter;
            }

            const response = await fetch('http://127.0.0.1:5000/analisar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            });
            const data = await response.json();

            // --- LÓGICA DE EXIBIÇÃO DAS ABAS ---
            let showedSomething = false;

            if (data.dashboard_data) {
                renderDashboard(data.dashboard_data, data.codigo_analisado);
                dashboard.style.display = 'block'; // Mostra o dashboard
                resultadoTextoContainer.style.display = 'none'; // Esconde o texto
                tabDashboard.classList.add('active'); // Ativa a aba do dashboard
                tabRawText.classList.remove('active');
                showedSomething = true;
            }
            
            if (data.resultado_texto) {
                resultadoTexto.textContent = data.resultado_texto;
                
                // Só exibe a aba de texto por padrão se o dashboard NÃO existir
                if (!data.dashboard_data) {
                    dashboard.style.display = 'none';
                    resultadoTextoContainer.style.display = 'block';
                    tabDashboard.classList.remove('active');
                    tabRawText.classList.add('active');
                }
                showedSomething = true;
            }

            // Se qualquer resultado foi mostrado, exibe o container das abas
            if (showedSomething) {
                tabsContainer.style.display = 'flex';
            }
            
            // Lida com erros (exibe alerta)
            if (!data.dashboard_data && (data.error || data.raw_text_error)) {
                 alert('Analysis error: ' + (data.error || data.raw_text_error));
            }

        } catch (error) {
            alert('Error connecting to the analysis server.');
            console.error('Erro:', error);
        } finally {
            loadingOverlay.style.display = 'none';
            validateInputs();
        }
    });
    
    function renderDashboard(resultsArray, codigoFonte) {
        const statusBanner = document.getElementById('status-banner');
        const cardPassos = document.getElementById('card-total-passos');
        const cardViolacoes = document.getElementById('card-violacoes');
        const violacoesTabela = document.getElementById('violacoes-tabela');
        const valoresIniciais = document.getElementById('valores-iniciais');
        const codigoContainer = document.getElementById('codigo-fonte-container');
        const traceExecucao = document.getElementById('traço-execucao');

        document.getElementById('violacoes-section').style.display = 'none';
        document.getElementById('contraexemplo-section').style.display = 'none';
        document.getElementById('trace-section').style.display = 'none';
        violacoesTabela.innerHTML = '';
        valoresIniciais.textContent = '';
        traceExecucao.textContent = '';

        const violationDetails = [];
        resultsArray.forEach(result => {
            if (result.status === 'violation' && result.steps) {
                result.steps.forEach(step => {
                    if (step.type === 'violation') {
                        violationDetails.push({
                            file: step.file || 'N/A', function: step.function || 'N/A',
                            line: step.line || 'N/A', message: step.message || 'Description not available'
                        });
                    }
                });
            }
        });

        cardViolacoes.textContent = violationDetails.length;
        const hasViolations = violationDetails.length > 0;

        if (hasViolations) {
            const firstResultWithViolation = resultsArray.find(res => res.status === 'violation');
            statusBanner.className = 'status-banner failed';
            statusBanner.textContent = `VERIFICATION FAILED (${violationDetails.length} VIOLATION(S))`;
            document.getElementById('violacoes-section').style.display = 'block';
            document.getElementById('contraexemplo-section').style.display = 'block';
            document.getElementById('trace-section').style.display = 'block';
            cardPassos.textContent = firstResultWithViolation.steps ? firstResultWithViolation.steps.length : 0;
            violationDetails.forEach(v => {
                const row = violacoesTabela.insertRow();
                row.innerHTML = `<td>${v.file}</td><td>${v.function}</td><td>${v.line}</td><td>${v.message}</td>`;
            });
            if (firstResultWithViolation.initial_values) {
                for (const key in firstResultWithViolation.initial_values) {
                    const valueObj = firstResultWithViolation.initial_values[key];
                    const value = valueObj?.value?.value || 'N/A';
                    valoresIniciais.textContent += `${key} = ${value}\n`;
                }
            }
            if (firstResultWithViolation.steps) {
                firstResultWithViolation.steps.forEach((step, index) => {
                    const stepDetails = step.message || step.full_expr || (step.assignment ? `${step.assignment.lhs} = ${step.assignment.rhs?.value || '...'}` : '');
                    const location = step.file ? `${step.file}:${step.line}` : 'N/A';
                    traceExecucao.textContent += `[Step ${index}] ${step.type} @ ${location} -> ${stepDetails}\n`;
                });
            }
        } else {
            statusBanner.className = 'status-banner success';
            statusBanner.textContent = 'VERIFICATION SUCCESSFUL';
            cardPassos.textContent = resultsArray[0]?.steps?.length || 0;
        }

        const lineNumbersOfViolations = violationDetails.map(v => v.line);
        const codeLines = codigoFonte.split('\n');
        codigoContainer.innerHTML = '';
        codeLines.forEach((line, index) => {
            const lineNumber = index + 1;
            const lineElement = document.createElement('div');
            if (lineNumbersOfViolations.includes(lineNumber.toString())) {
                lineElement.className = 'highlight-red';
            }
            const lineNumSpan = document.createElement('span');
            lineNumSpan.style.color = '#555';
            lineNumSpan.style.marginRight = '10px';
            lineNumSpan.style.userSelect = 'none';
            lineNumSpan.textContent = lineNumber.toString().padStart(3, ' ') + ' ';
            lineElement.appendChild(lineNumSpan);
            lineElement.append(line);
            codigoContainer.appendChild(lineElement);
        });
    }

    // --- Inicialização ---
    toggleLanguageOptions();
    validateInputs();
});