document.addEventListener('DOMContentLoaded', () => {
    // --- Variáveis Globais e Constantes ---
    const analisarBtn = document.getElementById('analisarBtn');
    const esbmcFlags = document.querySelectorAll('.esbmc-flag');
    const esbmcParams = document.querySelectorAll('.esbmc-param');
    const languageRadios = document.querySelectorAll('input[name="language"]');
    const pythonOptions = document.getElementById('python-options');
    const cCppDependencies = document.getElementById('c-cpp-dependencies');
    const dependencyListContainer = document.getElementById('dependency-files-list-container');
    
    // --- ATUALIZADO: Variáveis do Git ---
    const gitRepoUrl = document.getElementById('gitRepoUrl');
    const gitMainFile = document.getElementById('gitMainFile');
    const fetchRepoBtn = document.getElementById('fetchRepoBtn');
    const gitFetchStatus = document.getElementById('git-fetch-status');
    const gitFileListDatalist = document.getElementById('git-file-list');
    
    const fileInputContainer = document.querySelector('.file-input-container');
    const dependencyContainer = document.getElementById('c-cpp-dependencies');
    const editorButtons = document.querySelector('.editor-botoes-container');


    // --- Variáveis dos Botões do Editor ---
    const btnLimparEditor = document.getElementById('btnLimparEditor');
    const btnSelecionarTudo = document.getElementById('btnSelecionarTudo');
    const btnCopiarCodigo = document.getElementById('btnCopiarCodigo');
    let dependencyFiles = []; // Array que armazena {filename, content}

    // --- Variáveis das Abas e Resultados (Inalteradas) ---
    const tabsContainer = document.getElementById('tabs-container');
    const tabDashboard = document.getElementById('tab-dashboard');
    const tabRawText = document.getElementById('tab-raw-text');
    const tabHtmlReport = document.getElementById('tab-html-report');
    const tabYamlReport = document.getElementById('tab-yaml-report');
    const tabGraphmlReport = document.getElementById('tab-graphml-report');
    const dashboard = document.getElementById('dashboard-detalhado');
    const resultadoTextoContainer = document.getElementById('resultado-texto-container');
    const htmlReportContainer = document.getElementById('html-report-container');
    const htmlReportIframe = document.getElementById('html-report-iframe');
    const yamlReportContainer = document.getElementById('yaml-report-container');
    const yamlReportPre = document.getElementById('yaml-report-pre');
    const graphmlReportContainer = document.getElementById('graphml-report-container');
    const graphmlReportPre = document.getElementById('graphml-report-pre');
    const resultadoTexto = document.getElementById('resultado-texto');

    // --- Variáveis do Modal de Ajuda (Inalteradas) ---
    const helpBtn = document.getElementById('helpBtn');
    const helpModal = document.getElementById('helpModal');
    const helpTextContent = document.getElementById('help-text-content');
    const modalCloseBtn = document.querySelector('.modal-close-btn');


    // --- Inicialização do Editor CodeMirror ---
    const editor = CodeMirror.fromTextArea(document.getElementById('codigoInput'), {
        lineNumbers: true,
        mode: 'text/x-c++src', // Modo padrão C++
        theme: 'dracula',
        indentUnit: 4,
    });
    const editorWrapper = editor.getWrapperElement();


    // --- Lógica das Abas de Opções (Inalterada) ---
    const optionsTabButtons = document.querySelectorAll('.opcoes-tab-btn');
    const optionsTabPanes = document.querySelectorAll('.opcoes-tab-pane');

    optionsTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabTarget = button.dataset.tab;
            optionsTabButtons.forEach(btn => btn.classList.remove('active'));
            optionsTabPanes.forEach(pane => pane.classList.remove('active'));
            button.classList.add('active');
            document.getElementById(`tab-pane-${tabTarget}`).classList.add('active');
        });
    });

    // --- Lógica Colapsável (Accordion) (Inalterada) ---
    const collapsibleLegends = document.querySelectorAll('.opcoes-analise.collapsible > legend');

    collapsibleLegends.forEach(legend => {
        legend.addEventListener('click', (event) => {
            const fieldset = event.target.parentElement;
            if (fieldset) {
                fieldset.classList.toggle('open');
            }
        });
    });


    // --- Funções de UI ---

    function toggleLanguageOptions() {
        const selectedLanguage = document.querySelector('input[name="language"]:checked').value;
        cCppDependencies.style.display = 'block';

        if (selectedLanguage === 'python') {
            pythonOptions.style.display = 'block';
            editor.setOption('mode', 'python');
        } else {
            pythonOptions.style.display = 'none';
            editor.setOption('mode', selectedLanguage === 'c' ? 'text/x-csrc' : 'text/x-c++src');
        }
    }

    // --- Lógica de Validação (Inalterada) ---
    function validateInputs() {
        const isCodePresent = editor.getValue().trim() !== '';
        const hasGitInput = gitRepoUrl.value.trim() !== '' && gitMainFile.value.trim() !== '';
        const hasCodeSource = isCodePresent || hasGitInput;

        let isOptionSelected = false;
        esbmcFlags.forEach(flag => { if (flag.checked) isOptionSelected = true; });
        
        if (!isOptionSelected) {
            esbmcParams.forEach(param => { if (param.value.trim() !== '') isOptionSelected = true; });
        }
        
        if (hasGitInput) {
            editor.setOption('readOnly', 'nocursor');
            editorWrapper.style.backgroundColor = '#f1f1f1';
            editorWrapper.style.opacity = '0.6';
            fileInputContainer.style.opacity = '0.5';
            dependencyContainer.style.opacity = '0.5';
            editorButtons.style.opacity = '0.5';
            document.getElementById('fileInput').disabled = true;
            document.getElementById('dependencyInput').disabled = true;
        } else {
            editor.setOption('readOnly', false);
            editorWrapper.style.backgroundColor = '';
            editorWrapper.style.opacity = '1';
            fileInputContainer.style.opacity = '1';
            dependencyContainer.style.opacity = '1';
            editorButtons.style.opacity = '1';
            document.getElementById('fileInput').disabled = false;
            document.getElementById('dependencyInput').disabled = false;
        }

        if (hasCodeSource && isOptionSelected) {
            analisarBtn.disabled = false;
            analisarBtn.textContent = 'Analyze';
        } else {
            analisarBtn.disabled = true;
            if (!hasCodeSource) {
                analisarBtn.textContent = 'Fill in code or Git info';
            } else {
                analisarBtn.textContent = 'Please select an analysis option';
            }
        }
    }
    
    // --- (Função renderDependencyList - Inalterada) ---
    function renderDependencyList() {
        dependencyListContainer.innerHTML = '';
        dependencyFiles.forEach(file => {
            const tag = document.createElement('div');
            tag.className = 'dependency-tag';
            tag.textContent = file.filename;
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-dependency-btn';
            removeBtn.innerHTML = '&times;';
            removeBtn.title = `Remove ${file.filename}`;
            removeBtn.dataset.filename = file.filename;
            tag.appendChild(removeBtn);
            dependencyListContainer.appendChild(tag);
        });
    }

    // --- ============ NOVAS FUNÇÕES ============ ---

    /**
     * Seleciona o radio button de linguagem com base na extensão do arquivo.
     */
    function autoSelectLanguage(filename) {
        if (filename.endsWith('.c') || filename.endsWith('.h')) {
            document.getElementById('lang-c').checked = true;
        } else if (filename.endsWith('.cpp') || filename.endsWith('.hpp')) {
            document.getElementById('lang-cpp').checked = true;
        } else if (filename.endsWith('.py')) {
            document.getElementById('lang-py').checked = true;
        } else {
            // Padrão C++ se não for reconhecido
            document.getElementById('lang-cpp').checked = true;
        }
        
        // Atualiza a UI (opções de Python e syntax highlighting do editor)
        toggleLanguageOptions();
    }

    /**
     * Busca o conteúdo de um arquivo do Git e carrega no editor.
     */
    async function fetchAndLoadFile(filePath) {
        const url = gitRepoUrl.value.trim();
        if (!url) return; // Segurança: não fazer nada se a URL foi apagada

        gitFetchStatus.textContent = 'Loading file content...';
        gitFetchStatus.className = '';

        try {
            const response = await fetch('http://127.0.0.1:5000/fetch-file-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    git_url: url, 
                    file_path: filePath 
                })
            });

            const data = await response.json();

            if (!response.ok || data.error) {
                throw new Error(data.error || 'Failed to fetch file content.');
            }

            // Sucesso!
            editor.setValue(data.content);
            autoSelectLanguage(filePath);
            gitFetchStatus.textContent = 'File loaded successfully.';
            
            // Re-valida para garantir que o botão Analyze acenda
            validateInputs(); 

        } catch (error) {
            console.error('Error fetching file content:', error);
            gitFetchStatus.textContent = `Error: ${error.message}`;
            gitFetchStatus.className = 'error';
            editor.setValue(''); // Limpa o editor em caso de falha
        }
    }
    // --- ============ FIM DAS NOVAS FUNÇÕES ============ ---


    // --- Event Listeners ---

    editor.on('change', validateInputs);
    document.querySelectorAll('.esbmc-flag, .esbmc-param').forEach(input => {
        const event = input.type === 'checkbox' || input.type === 'radio' ? 'change' : 'input';
        input.addEventListener(event, validateInputs);
    });

    // --- Listener do Git URL (Inalterado) ---
    gitRepoUrl.addEventListener('input', () => {
        validateInputs();
        gitFileListDatalist.innerHTML = '';
        gitFetchStatus.textContent = '';
        gitFetchStatus.className = '';
    });

    // --- ATUALIZADO: Listener do Git Main File ---
    // Este listener agora também carrega o arquivo
    gitMainFile.addEventListener('input', () => {
        // 1. Sempre re-valida o estado do botão "Analyze"
        validateInputs(); 
        
        const selectedFile = gitMainFile.value;
        const options = Array.from(gitFileListDatalist.options).map(opt => opt.value);

        // 2. Verifica se o valor no campo é uma seleção *completa* da lista
        if (options.includes(selectedFile)) {
            fetchAndLoadFile(selectedFile);
        }
    });
    // --- FIM DA ATUALIZAÇÃO ---


    // --- Listener 'Fetch Files' (Inalterado) ---
    fetchRepoBtn.addEventListener('click', async () => {
        const url = gitRepoUrl.value.trim();
        if (!url) {
            alert('Please enter a Git URL first.');
            return;
        }

        gitFileListDatalist.innerHTML = '';
        gitFetchStatus.textContent = 'Fetching repository... (this may take a moment)';
        gitFetchStatus.className = '';
        fetchRepoBtn.disabled = true;

        try {
            const response = await fetch('http://127.0.0.1:5000/fetch-repo-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ git_url: url })
            });

            const data = await response.json();

            if (!response.ok || data.error) {
                throw new Error(data.error || 'Failed to fetch files.');
            }

            if (data.files && data.files.length > 0) {
                data.files.forEach(filePath => {
                    const option = document.createElement('option');
                    option.value = filePath;
                    gitFileListDatalist.appendChild(option);
                });
                gitFetchStatus.textContent = `Found ${data.files.length} relevant files.`;
            } else {
                gitFetchStatus.textContent = 'No relevant files (.c, .py, etc.) found in this repo.';
            }

        } catch (error) {
            console.error('Error fetching repo files:', error);
            gitFetchStatus.textContent = `Error: ${error.message}`;
            gitFetchStatus.className = 'error';
        } finally {
            fetchRepoBtn.disabled = false;
        }
    });


    // --- Listeners (Botões Editor, Upload, Dependências) (Inalterados) ---
    
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

    // --- Listeners das Abas de Resultado (Inalterados) ---
    tabDashboard.addEventListener('click', () => {
        dashboard.style.display = 'block';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.add('active');
        tabRawText.classList.remove('active');
        tabHtmlReport.classList.remove('active');
        tabYamlReport.classList.remove('active');
        tabGraphmlReport.classList.remove('active');
    });

    tabRawText.addEventListener('click', () => {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'block';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active');
        tabRawText.classList.add('active');
        tabHtmlReport.classList.remove('active');
        tabYamlReport.classList.remove('active');
        tabGraphmlReport.classList.remove('active');
    });

    tabHtmlReport.addEventListener('click', () => {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'block';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active');
        tabRawText.classList.remove('active');
        tabHtmlReport.classList.add('active');
        tabYamlReport.classList.remove('active');
        tabGraphmlReport.classList.remove('active');
    });

    tabYamlReport.addEventListener('click', () => {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'block';
        graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active');
        tabRawText.classList.remove('active');
        tabHtmlReport.classList.remove('active');
        tabYamlReport.classList.add('active');
        tabGraphmlReport.classList.remove('active');
    });

    tabGraphmlReport.addEventListener('click', () => {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'block';
        tabDashboard.classList.remove('active');
        tabRawText.classList.remove('active');
        tabHtmlReport.classList.remove('active');
        tabYamlReport.classList.remove('active');
        tabGraphmlReport.classList.add('active');
    });


    // --- Listener Principal: Analisar (Inalterado) ---
    document.getElementById('analisarBtn').addEventListener('click', async () => {
        const codigo = editor.getValue();
        const loadingOverlay = document.getElementById('loading-overlay');
        
        const gitUrlValue = gitRepoUrl.value.trim();
        const gitMainFileValue = gitMainFile.value.trim();

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
        
        const hasGraphmlOutput = flags.includes('--witness-output');
        const hasYamlOutput = flags.includes('--witness-output-yaml');
        const hasHtmlReportFlag = flags.includes('--generate-html-report');

        if (linguagemSelecionada === 'c' || linguagemSelecionada === 'cpp' || linguagemSelecionada === 'python') {
            if (!hasHtmlReportFlag) {
                flags.push('--generate-html-report');
            }
            if (!hasGraphmlOutput) {
                flags.push('--witness-output');
                flags.push('auto-witness.graphml');
            }
            if (!hasYamlOutput) {
                flags.push('--witness-output-yaml');
                flags.push('auto-witness.yaml');
            }
        }

        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        tabsContainer.style.display = 'none'; 
        loadingOverlay.style.display = 'flex';
        analisarBtn.disabled = true;
        analisarBtn.textContent = 'Analyzing...';

        try {
            const requestBody = {
                flags,
                language: linguagemSelecionada,
            };

            if (gitUrlValue && gitMainFileValue) {
                requestBody.git_url = gitUrlValue;
                requestBody.main_file_path = gitMainFileValue;
            } else {
                requestBody.codigo = codigo;
                requestBody.dependencies = dependencyFiles;
            }

            if (linguagemSelecionada === 'python' && pythonInterpreter) {
                requestBody.python_interpreter = pythonInterpreter;
            }

            const response = await fetch('http://127.0.0.1:5000/analisar', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Cache-Control': 'no-cache'
                },
                body: JSON.stringify(requestBody),
                cache: 'no-store'
            });

            const data = await response.json();
            
            if (response.status >= 400 && data.error) {
                 alert('Error: ' + data.error);
                 throw new Error(data.error);
            }

            let showedSomething = false;
            
            dashboard.style.display = 'none';
            resultadoTextoContainer.style.display = 'none';
            htmlReportContainer.style.display = 'none';
            yamlReportContainer.style.display = 'none';
            graphmlReportContainer.style.display = 'none';

            tabDashboard.classList.remove('active');
            tabRawText.classList.remove('active');
            tabHtmlReport.classList.remove('active');
            tabYamlReport.classList.remove('active');
            tabGraphmlReport.classList.remove('active');
            
            tabHtmlReport.style.display = 'none'; 
            tabYamlReport.style.display = 'none';
            tabGraphmlReport.style.display = 'none';

            htmlReportIframe.srcdoc = '';
            yamlReportPre.textContent = '';
            graphmlReportPre.textContent = '';


            if (data.html_report_data) {
                htmlReportIframe.srcdoc = data.html_report_data;
                tabHtmlReport.style.display = 'inline-block';
                showedSomething = true;
            }

            if (data.yaml_report_data) {
                yamlReportPre.textContent = data.yaml_report_data;
                tabYamlReport.style.display = 'inline-block';
                showedSomething = true;
            }

            if (data.graphml_report_data) {
                graphmlReportPre.textContent = data.graphml_report_data;
                tabGraphmlReport.style.display = 'inline-block';
                showedSomething = true;
            }

            if (data.dashboard_data && data.dashboard_data.length > 0 && data.codigo_analisado) {
                renderDashboard(data.dashboard_data, data.codigo_analisado);
                showedSomething = true;
            }
            
            if (data.resultado_texto) {
                resultadoTexto.textContent = data.resultado_texto;
                showedSomething = true;
            }

            if (data.html_report_data) {
                htmlReportContainer.style.display = 'block';
                tabHtmlReport.classList.add('active');
            } else if (data.yaml_report_data) { 
                yamlReportContainer.style.display = 'block';
                tabYamlReport.classList.add('active');
            } else if (data.graphml_report_data) {
                graphmlReportContainer.style.display = 'block';
                tabGraphmlReport.classList.add('active');
            } else if (data.dashboard_data && data.dashboard_data.length > 0 && data.codigo_analisado) {
                dashboard.style.display = 'block';
                tabDashboard.classList.add('active');
            } else if (data.resultado_texto) {
                resultadoTextoContainer.style.display = 'block';
                tabRawText.classList.add('active');
            }

            if (showedSomething) {
                tabsContainer.style.display = 'flex';
            }
            
            if (!showedSomething && (data.error || data.raw_text_error)) {
                 alert('Analysis error: ' + (data.error || data.raw_text_error));
            }

        } catch (error) {
            if (!error.message.includes('Failed to clone') && !error.message.includes('Failed to fetch') && !error.message.includes('Invalid file path')) {
                 alert('Error connecting to the analysis server.');
            }
            console.error('Erro:', error);
        } finally {
            loadingOverlay.style.display = 'none';
            validateInputs();
        }
    });
    
    // --- (Função renderDashboard - Inalterada) ---
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


    // --- Listeners do Modal de Ajuda (Inalterados) ---
    helpBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        helpTextContent.textContent = 'Loading...';
        helpModal.style.display = 'block';
        try {
            const response = await fetch('http://127.0.0.1:5000/help', {
                 method: 'GET',
                 cache: 'no-store'
            });
            const data = await response.json();
            helpTextContent.textContent = data.help_text;
        } catch (error) {
            helpTextContent.textContent = 'Error connecting to the server to get help text.';
            console.error('Erro ao buscar ajuda:', error);
        }
    });

    modalCloseBtn.addEventListener('click', () => {
        helpModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target == helpModal) {
            helpModal.style.display = 'none';
        }
    });
});
