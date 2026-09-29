document.addEventListener('DOMContentLoaded', () => {
    // --- Variáveis Globais e Constantes ---
    const analisarBtn = document.getElementById('analisarBtn');
    const esbmcFlags = document.querySelectorAll('.esbmc-flag');
    const esbmcParams = document.querySelectorAll('.esbmc-param');
    const languageRadios = document.querySelectorAll('input[name="language"]');
    const pythonOptions = document.getElementById('python-options');
    const cCppDependencies = document.getElementById('c-cpp-dependencies');
    const dependencyListContainer = document.getElementById('dependency-files-list-container');
    
    // --- Variáveis do Git ---
    const gitRepoUrl = document.getElementById('gitRepoUrl');
    const gitMainFile = document.getElementById('gitMainFile');
    const fetchRepoBtn = document.getElementById('fetchRepoBtn');
    const gitFetchStatus = document.getElementById('git-fetch-status');
    const gitFileListDatalist = document.getElementById('git-file-list');
    const gitFileSelect = document.getElementById('gitFileSelect');
    const gitFolderScopeBadge = document.getElementById('git-folder-scope-badge');
    window.REPO_ALL_FILES = [];
    
    const fileInputContainer = document.querySelector('.file-input-container');
    const dependencyContainer = document.getElementById('c-cpp-dependencies');
    const editorButtons = document.querySelector('.editor-botoes-container');

    // --- Variáveis dos Botões do Editor ---
    const btnLimparEditor = document.getElementById('btnLimparEditor');
    const btnSelecionarTudo = document.getElementById('btnSelecionarTudo');
    const btnCopiarCodigo = document.getElementById('btnCopiarCodigo');
    let dependencyFiles = []; 

    // --- Variáveis das Abas e Resultados ---
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

    const helpBtn = document.getElementById('helpBtn');
    const helpModal = document.getElementById('helpModal');
    const helpTextContent = document.getElementById('help-text-content');
    const modalCloseBtn = document.querySelector('.modal-close-btn');

    // --- Inicialização do Editor CodeMirror ---
    const editor = CodeMirror.fromTextArea(document.getElementById('codigoInput'), {
        lineNumbers: true,
        mode: 'text/x-c++src', 
        theme: 'dracula',
        indentUnit: 4,
    });
    const editorWrapper = editor.getWrapperElement();

    // =========================================================================
    // ⏳ SISTEMA DE PROGRESSÃO E LOADING (NOVO)
    // =========================================================================
    
    function showLoadingOverlay(texto, percent = null) {
        const overlay = document.getElementById('loading-overlay');
        const textElement = overlay.querySelector('.loading-text');
        const progressBarValue = overlay.querySelector('.progress-bar-value');
        
        if (textElement && texto) textElement.textContent = texto;
        
        if (percent !== null) {
            // Trava a animação infinita CSS e usa o tamanho exato da %
            progressBarValue.style.animation = 'none';
            progressBarValue.style.width = `${percent}%`;
        } else {
            // Restaura a animação infinita para ações sem % (ex: carregar um ficheiro)
            progressBarValue.style.animation = 'indeterminate-progress 1.5s ease-in-out infinite';
            progressBarValue.style.width = '100%';
        }
        
        overlay.style.display = 'flex';
    }

    function hideLoadingOverlay() {
        document.getElementById('loading-overlay').style.display = 'none';
    }

    // =========================================================================
    // 🟢 1. MONITOR DE INICIALIZAÇÃO DO SERVIDOR ESBMC-WEB (.BAT -> HTML)
    // =========================================================================
    const startupOverlay = document.getElementById('server-startup-overlay');
    const startupIcon = document.getElementById('startup-icon');
    const startupTitle = document.getElementById('startup-title');
    const startupSubtitle = document.getElementById('startup-subtitle');
    const startupBarFill = document.getElementById('startup-bar-fill');
    const startupStepDetail = document.getElementById('startup-step-detail');
    const closeStartupBtn = document.getElementById('close-startup-overlay-btn');
    const serverStatusBadge = document.getElementById('server-status-badge');
    const serverStatusDot = document.getElementById('server-status-dot');
    const serverStatusText = document.getElementById('server-status-text');

    if (closeStartupBtn && startupOverlay) {
        closeStartupBtn.addEventListener('click', () => {
            startupOverlay.style.display = 'none';
        });
    }

    let serverStartupAttempts = 0;
    async function checkServerHealth() {
        serverStartupAttempts++;
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1500);
            const res = await fetch('http://127.0.0.1:5000/health', { signal: controller.signal, cache: 'no-store' });
            clearTimeout(timeoutId);
            if (res.ok) {
                const info = await res.json();
                if (serverStatusBadge && serverStatusDot && serverStatusText) {
                    serverStatusBadge.style.background = '#ecfdf5';
                    serverStatusBadge.style.color = '#065f46';
                    serverStatusBadge.style.borderColor = '#10b981';
                    serverStatusDot.style.background = '#10b981';
                    serverStatusText.textContent = `🟢 Servidor ESBMC Online`;
                    //serverStatusText.textContent = `🟢 Servidor ESBMC Online — Pronto para Uso (${info.engine || 'RepoSlice-BMC'})`;
                }
                if (startupOverlay && startupOverlay.style.display !== 'none') {
                    if (startupIcon) startupIcon.textContent = '✅';
                    if (startupTitle) {
                        startupTitle.textContent = 'Servidor ESBMC Conectado e Pronto para Uso!';
                        startupTitle.style.color = '#065f46';
                    }
                    if (startupSubtitle) {
                        startupSubtitle.innerHTML = `Motor <strong>${info.engine || 'RepoSlice-BMC v2026'}</strong> e Solver <strong>${info.solver || 'Z3'}</strong> ativos e prontos para verificação formal.`;
                    }
                    if (startupBarFill) {
                        startupBarFill.style.width = '100%';
                        startupBarFill.style.background = '#10b981';
                    }
                    if (startupStepDetail) {
                        startupStepDetail.textContent = '✅ Conexão estabelecida com sucesso em http://127.0.0.1:5000!';
                        startupStepDetail.style.color = '#059669';
                    }
                    if (closeStartupBtn) closeStartupBtn.style.display = 'inline-block';
                    setTimeout(() => {
                        if (startupOverlay) startupOverlay.style.display = 'none';
                    }, 1300);
                }
                return;
            }
        } catch (err) {
            if (startupStepDetail) {
                const pct = Math.min(90, 20 + serverStartupAttempts * 10);
                if (startupBarFill) startupBarFill.style.width = `${pct}%`;
                startupStepDetail.textContent = `⏳ Aguardando inicialização do servidor Flask/WSL2 (Tentativa ${serverStartupAttempts})...`;
            }
        }
        setTimeout(checkServerHealth, 900);
    }
    checkServerHealth();

    // =========================================================================
    // 📊 2. PAINEL DE PROGRESSO EM TEMPO REAL (1/12, 2/12...) + TABELA AO VIVO
    // =========================================================================
    const analysisProgressContainer = document.createElement('div');
    analysisProgressContainer.id = 'analysis-progress-container';
    analysisProgressContainer.style.display = 'none';
    analysisProgressContainer.style.width = '100%';
    analysisProgressContainer.style.marginTop = '16px';
    analysisProgressContainer.style.padding = '16px';
    analysisProgressContainer.style.background = '#f8fafc';
    analysisProgressContainer.style.border = '1px solid #cbd5e1';
    analysisProgressContainer.style.borderRadius = '10px';
    analysisProgressContainer.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
            <div id="live-progress-status-text" style="font-size: 13.5px; color: var(--primary); font-weight: 700; display: flex; align-items: center; gap: 8px;">
                <span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid var(--primary); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span>
                <span>Iniciando verificação formal...</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span id="live-progress-counter-badge" style="background: #4f46e5; color: #fff; padding: 4px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 800;">
                    Teste 1/1 (0%)
                </span>
                <span id="live-progress-scoreboard" style="background: #e2e8f0; color: #1e293b; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;">
                    ✅ SAFE: 0 | ❌ VIOLATION: 0 | 📐 VCCs: 0
                </span>
            </div>
        </div>
        <div style="width: 100%; height: 10px; background-color: #e2e8f0; border-radius: 999px; overflow: hidden; margin-bottom: 10px;">
            <div id="live-progress-bar-fill" style="width: 8%; height: 100%; background: linear-gradient(90deg, #4f46e5, #0ea5e9); border-radius: 999px; transition: width 0.35s ease;"></div>
        </div>
        <div id="live-streaming-preview-wrapper" style="display: none; margin-top: 10px; max-height: 210px; overflow-y: auto; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff;">
            <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                <thead style="background: #f1f5f9; position: sticky; top: 0;">
                    <tr>
                        <th style="padding: 6px 8px; text-align: left;">Teste #</th>
                        <th style="padding: 6px 8px; text-align: left;">Lang</th>
                        <th style="padding: 6px 8px; text-align: left;">Fase</th>
                        <th style="padding: 6px 8px; text-align: left;">Módulo / Arquivo</th>
                        <th style="padding: 6px 8px; text-align: left;">Modo / Contraexemplo Z3</th>
                        <th style="padding: 6px 8px; text-align: left;">VCCs / SSA</th>
                        <th style="padding: 6px 8px; text-align: left;">Tempo</th>
                        <th style="padding: 6px 8px; text-align: left;">Veredito</th>
                        <th style="padding: 6px 8px; text-align: left;">Status / Oráculo</th>
                    </tr>
                </thead>
                <tbody id="live-streaming-preview-tbody"></tbody>
            </table>
        </div>
        <style>@keyframes spin { to { transform: rotate(360deg); } }</style>
    `;
    const btnContainer = document.getElementById('cancelarBtn').parentElement;
    btnContainer.parentElement.insertBefore(analysisProgressContainer, btnContainer.nextSibling);

    // =========================================================================
    // 🎯 3. PERFIS CIENTÍFICOS DE VERIFICAÇÃO (1-CLICK PRESETS)
    // =========================================================================
    document.querySelectorAll('.preset-profile-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const preset = btn.dataset.preset;
            document.querySelectorAll('.esbmc-flag').forEach(cb => { cb.checked = false; });
            const unwindInput = document.querySelector('.esbmc-param[data-flag="--unwind"]');
            if (unwindInput) unwindInput.value = '';

            if (preset === 'fast-audit') {
                const falsif = document.querySelector('.esbmc-flag[value="--falsification"]');
                if (falsif) falsif.checked = true;
                if (unwindInput) unwindInput.value = '3';
            } else if (preset === 'bug-hunting') {
                const incBmc = document.querySelector('.esbmc-flag[value="--incremental-bmc"]');
                const overflow = document.querySelector('.esbmc-flag[value="--overflow-check"]');
                const memleak = document.querySelector('.esbmc-flag[value="--memory-leak-check"]');
                if (incBmc) incBmc.checked = true;
                if (overflow) overflow.checked = true;
                if (memleak) memleak.checked = true;
            } else if (preset === 'sound-proof') {
                const kind = document.querySelector('.esbmc-flag[value="--k-induction"]');
                const multiProp = document.querySelector('.esbmc-flag[value="--multi-property"]');
                const overflow = document.querySelector('.esbmc-flag[value="--overflow-check"]');
                if (kind) kind.checked = true;
                if (multiProp) multiProp.checked = true;
                if (overflow) overflow.checked = true;
            }
            validateInputs();
        });
    });

    function initLiveProgressPanel(initialMessage, isRepoMode = false) {
        analysisProgressContainer.style.display = 'block';
        const statusText = document.getElementById('live-progress-status-text');
        const counterBadge = document.getElementById('live-progress-counter-badge');
        const scoreboard = document.getElementById('live-progress-scoreboard');
        const barFill = document.getElementById('live-progress-bar-fill');
        const previewWrapper = document.getElementById('live-streaming-preview-wrapper');
        const previewTbody = document.getElementById('live-streaming-preview-tbody');

        if (statusText) {
            statusText.innerHTML = `<span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid var(--primary); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span> <span>${initialMessage}</span>`;
        }
        if (counterBadge) counterBadge.textContent = isRepoMode ? 'Clonando & Escaneando Git...' : 'Teste 1/1 (Em execução)';
        if (scoreboard) scoreboard.textContent = '✅ SAFE: 0 | ❌ VIOLATION: 0 | 📐 VCCs: 0 | 🔗 SSA: 0';
        if (barFill) barFill.style.width = '6%';
        if (previewWrapper) previewWrapper.style.display = 'none';
        if (previewTbody) previewTbody.innerHTML = '';
    }

    // --- Lógica das Abas de Opções ---
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

    const collapsibleLegends = document.querySelectorAll('.opcoes-analise.collapsible > legend');
    collapsibleLegends.forEach(legend => {
        legend.addEventListener('click', (event) => {
            const fieldset = event.target.parentElement;
            if (fieldset) fieldset.classList.toggle('open');
        });
    });

    function toggleLanguageOptions() {
        const selectedLanguage = document.querySelector('input[name="language"]:checked').value;
        cCppDependencies.style.display = 'block';

        if (selectedLanguage === 'python' || selectedLanguage === 'all') {
            pythonOptions.style.display = 'block';
            if (selectedLanguage === 'python') editor.setOption('mode', 'python');
        } else {
            pythonOptions.style.display = 'none';
            editor.setOption('mode', selectedLanguage === 'c' ? 'text/x-csrc' : 'text/x-c++src');
        }
    }

    function validateInputs() {
        const isCodePresent = editor.getValue().trim() !== '';
        const hasGitInput = gitRepoUrl.value.trim() !== '' && gitMainFile.value.trim() !== '';
        const hasCodeSource = isCodePresent || hasGitInput;

        let isOptionSelected = false;
        esbmcFlags.forEach(flag => { if (flag.checked) isOptionSelected = true; });
        
        if (!isOptionSelected) {
            esbmcParams.forEach(param => { if (param.value.trim() !== '') isOptionSelected = true; });
        }

        const solverSelect = document.getElementById('solver-select');
        if (!isOptionSelected && solverSelect && solverSelect.value) {
            isOptionSelected = true;
        }
        
        editor.setOption('readOnly', false);
        editorWrapper.style.backgroundColor = '';
        editorWrapper.style.opacity = '1';
        fileInputContainer.style.opacity = '1';
        dependencyContainer.style.opacity = '1';
        editorButtons.style.opacity = '1';
        document.getElementById('fileInput').disabled = false;
        document.getElementById('dependencyInput').disabled = false;

        if (hasCodeSource && isOptionSelected) {
            analisarBtn.disabled = false;
            analisarBtn.textContent = 'Analyze Source Code';
        } else {
            analisarBtn.disabled = true;
            if (!hasCodeSource) analisarBtn.textContent = 'Fill in code or Git info';
            else analisarBtn.textContent = 'Please select an analysis option';
        }
    }
    
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

    function autoSelectLanguage(filename) {
        if (filename.endsWith('.c') || filename.endsWith('.h')) document.getElementById('lang-c').checked = true;
        else if (filename.endsWith('.cpp') || filename.endsWith('.hpp')) document.getElementById('lang-cpp').checked = true;
        else if (filename.endsWith('.py')) document.getElementById('lang-py').checked = true;
        else document.getElementById('lang-cpp').checked = true;
        toggleLanguageOptions();
    }

    // --- PROGRESSÃO: Carregar arquivo do Git (COM %) ---
    async function fetchAndLoadFile(filePath) {
        const url = gitRepoUrl.value.trim();
        if (!url) return;

        gitFetchStatus.textContent = 'Loading file content...';
        gitFetchStatus.className = '';
        
        // Inicia a overlay travada em 0%
        showLoadingOverlay(`Downloading file: ${filePath}... 0%`, 0); 

        try {
            const response = await fetch('http://127.0.0.1:5000/fetch-file-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ git_url: url, file_path: filePath })
            });

            const data = await response.json();

            if (!response.ok || data.error) throw new Error(data.error || 'Failed to start fetch.');

            const taskId = data.task_id;
            
            // Pergunta ao servidor a cada meio segundo o estado do download
            const poll = setInterval(async () => {
                try {
                    const res = await fetch(`http://127.0.0.1:5000/fetch-repo-status/${taskId}`);
                    const statusData = await res.json();

                    if (statusData.status === 'running') {
                        // Atualiza a barra de carregamento no ecrã
                        showLoadingOverlay(`Downloading file: ${filePath}... ${statusData.progress}%`, statusData.progress);
                    } else if (statusData.status === 'completed') {
                        clearInterval(poll);
                        hideLoadingOverlay();
                        
                        // Ficheiro descarregado com sucesso, injeta no editor
                        editor.setValue(statusData.content || '');
                        autoSelectLanguage(filePath);
                        gitFetchStatus.textContent = 'File loaded successfully.';
                        validateInputs(); 
                    } else if (statusData.status === 'error') {
                        clearInterval(poll);
                        hideLoadingOverlay();
                        gitFetchStatus.textContent = `Error: ${statusData.error}`;
                        gitFetchStatus.className = 'error';
                        editor.setValue('');
                    }
                } catch (pollError) {
                    console.error("Polling error:", pollError);
                }
            }, 500);

        } catch (error) {
            console.error('Error fetching file content:', error);
            gitFetchStatus.textContent = `Error: ${error.message}`;
            gitFetchStatus.className = 'error';
            editor.setValue('');
            hideLoadingOverlay();
        }
    }

    editor.on('change', validateInputs);
    document.querySelectorAll('.esbmc-flag, .esbmc-param').forEach(input => {
        const event = input.type === 'checkbox' || input.type === 'radio' ? 'change' : 'input';
        input.addEventListener(event, validateInputs);
    });

    function normalizarGithubUrlFrontend() {
        const raw = gitRepoUrl.value.trim();
        if (!raw) return;
        const padrao = /^(https?:\/\/github\.com\/[^/]+\/[^/]+)\/(?:tree|blob)\/([^/]+)\/(.+)$/i;
        const m = raw.match(padrao);
        if (m) {
            const baseUrl = m[1];
            const ref = m[2];
            const subpath = m[3].replace(/\/+$/, '');
            const isBlob = raw.includes('/blob/');
            gitRepoUrl.value = baseUrl;
            const repoSubdirFilter = document.getElementById('repoSubdirFilter');
            if (isBlob) {
                if (gitMainFile && !gitMainFile.value) {
                    gitMainFile.value = subpath;
                }
                const dirPai = subpath.substring(0, subpath.lastIndexOf('/'));
                if (repoSubdirFilter && !repoSubdirFilter.value && dirPai) {
                    repoSubdirFilter.value = dirPai;
                }
                gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">⚡ URL de arquivo detectada! Repositório base: <code>${baseUrl}</code> | Arquivo: <code>${subpath}</code></span>`;
            } else {
                if (repoSubdirFilter) {
                    repoSubdirFilter.value = subpath;
                }
                gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">⚡ Subpasta detectada! Repositório base: <code>${baseUrl}</code> | Filtro de subdiretório: <code>${subpath}</code></span>`;
            }
        }
    }

    gitRepoUrl.addEventListener('input', () => {
        normalizarGithubUrlFrontend();
        validateInputs();
        gitFileListDatalist.innerHTML = '';
        if (!gitFetchStatus.innerHTML.includes('⚡')) {
            gitFetchStatus.textContent = '';
            gitFetchStatus.className = '';
        }
    });

    gitRepoUrl.addEventListener('paste', () => {
        setTimeout(() => {
            normalizarGithubUrlFrontend();
            validateInputs();
        }, 60);
    });

    function renderizarArquivosPasta(listaArquivos, subpasta) {
        gitFileListDatalist.innerHTML = '';
        if (gitFileSelect) {
            gitFileSelect.innerHTML = '<option value="">📂 Selecionar arquivo da pasta...</option>';
        }

        if (!listaArquivos || listaArquivos.length === 0) {
            if (gitFileSelect) gitFileSelect.style.display = 'none';
            if (gitFolderScopeBadge) gitFolderScopeBadge.style.display = 'none';
            gitFetchStatus.textContent = subpasta 
                ? `Nenhum arquivo verificável (.c, .cpp, .py) encontrado na pasta "${subpasta}".`
                : 'Nenhum arquivo verificável (.c, .cpp, .py) encontrado neste repositório.';
            return;
        }

        listaArquivos.forEach(filePath => {
            const opt = document.createElement('option');
            opt.value = filePath;
            gitFileListDatalist.appendChild(opt);

            if (gitFileSelect) {
                const selOpt = document.createElement('option');
                selOpt.value = filePath;
                const label = subpasta && filePath.startsWith(subpasta + '/')
                    ? filePath.substring(subpasta.length + 1)
                    : filePath;
                selOpt.textContent = `📄 ${label}`;
                gitFileSelect.appendChild(selOpt);
            }
        });

        if (gitFileSelect) {
            gitFileSelect.style.display = 'inline-block';
        }

        if (gitFolderScopeBadge) {
            gitFolderScopeBadge.style.display = 'inline-block';
            if (subpasta) {
                gitFolderScopeBadge.textContent = `📂 Pasta: ${subpasta} (${listaArquivos.length} arquivos)`;
                gitFolderScopeBadge.style.background = '#dbeafe';
                gitFolderScopeBadge.style.color = '#1e40af';
            } else {
                gitFolderScopeBadge.textContent = `🌐 Repositório completo (${listaArquivos.length} arquivos)`;
                gitFolderScopeBadge.style.background = '#e5e7eb';
                gitFolderScopeBadge.style.color = '#4b5563';
            }
        }

        if (subpasta) {
            gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">✅ Pasta aberta: <code>${subpasta}</code> — ${listaArquivos.length} arquivo(s) prontos para teste individual ou exploração.</span>`;
            if (gitMainFile && !gitMainFile.value) {
                gitMainFile.placeholder = `Escolha um arquivo de ${subpasta}...`;
            }
        } else {
            gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">✅ Encontrados ${listaArquivos.length} arquivos no repositório.</span>`;
        }
    }

    if (gitFileSelect) {
        gitFileSelect.addEventListener('change', () => {
            const arq = gitFileSelect.value;
            if (arq) {
                gitMainFile.value = arq;
                fetchAndLoadFile(arq);
                validateInputs();
            }
        });
    }

    const repoSubdirFilterInput = document.getElementById('repoSubdirFilter');
    if (repoSubdirFilterInput) {
        repoSubdirFilterInput.addEventListener('input', () => {
            const sub = repoSubdirFilterInput.value.trim().replace(/^\/+|\/+$/g, '');
            if (window.REPO_ALL_FILES && window.REPO_ALL_FILES.length > 0) {
                let filtrados = window.REPO_ALL_FILES;
                if (sub) {
                    filtrados = window.REPO_ALL_FILES.filter(f => f === sub || f.startsWith(sub + '/'));
                }
                renderizarArquivosPasta(filtrados, sub);
            }
        });
    }

    gitMainFile.addEventListener('input', () => {
        validateInputs(); 
        const selectedFile = gitMainFile.value.trim();
        const options = Array.from(gitFileListDatalist.options).map(opt => opt.value);
        if (options.includes(selectedFile)) {
            if (gitFileSelect) gitFileSelect.value = selectedFile;
            fetchAndLoadFile(selectedFile);
        }
    });

    // --- PROGRESSÃO: Clonar repositório do Git (COM %) ---
    fetchRepoBtn.addEventListener('click', async () => {
        normalizarGithubUrlFrontend();
        const url = gitRepoUrl.value.trim();
        if (!url) { alert('Please enter a Git URL first.'); return; }

        const subdirFilterVal = repoSubdirFilterInput ? repoSubdirFilterInput.value.trim() : '';

        gitFileListDatalist.innerHTML = '';
        if (gitFileSelect) {
            gitFileSelect.innerHTML = '<option value="">📂 Carregando arquivos...</option>';
            gitFileSelect.style.display = 'none';
        }
        gitFetchStatus.textContent = 'Preparing to clone repository...';
        gitFetchStatus.className = '';
        fetchRepoBtn.disabled = true;

        showLoadingOverlay('Cloning Repository Structure... 0%', 0); 

        try {
            const reqBody = { git_url: url };
            if (subdirFilterVal) {
                reqBody.subdir_filter = subdirFilterVal;
            }

            const response = await fetch('http://127.0.0.1:5000/fetch-repo-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(reqBody)
            });

            const data = await response.json();
            if (!response.ok || data.error) throw new Error(data.error || 'Failed to start fetch.');

            if (data.normalized_url && data.normalized_url !== gitRepoUrl.value) {
                gitRepoUrl.value = data.normalized_url;
            }
            if (data.auto_subdir && repoSubdirFilterInput && !repoSubdirFilterInput.value) {
                repoSubdirFilterInput.value = data.auto_subdir;
            }

            const taskId = data.task_id;
            
            // Polling: Pergunta ao servidor a cada 0.5 segundos quantos % já clonou
            const poll = setInterval(async () => {
                try {
                    const res = await fetch(`http://127.0.0.1:5000/fetch-repo-status/${taskId}`);
                    const statusData = await res.json();

                    if (statusData.normalized_url && statusData.normalized_url !== gitRepoUrl.value) {
                        gitRepoUrl.value = statusData.normalized_url;
                    }
                    if (statusData.auto_subdir && repoSubdirFilterInput && !repoSubdirFilterInput.value) {
                        repoSubdirFilterInput.value = statusData.auto_subdir;
                    }

                    if (statusData.status === 'running') {
                        showLoadingOverlay(`Cloning Repository Structure... ${statusData.progress}%`, statusData.progress);
                    } else if (statusData.status === 'completed') {
                        clearInterval(poll);
                        hideLoadingOverlay();
                        fetchRepoBtn.disabled = false;

                        window.REPO_ALL_FILES = statusData.all_files || statusData.files || [];
                        const subpastaAtiva = statusData.auto_subdir || (repoSubdirFilterInput ? repoSubdirFilterInput.value.trim() : '');

                        renderizarArquivosPasta(statusData.files, subpastaAtiva);

                        const targetAutoFile = statusData.auto_file || data.auto_file;
                        if (targetAutoFile) {
                            gitMainFile.value = targetAutoFile;
                            if (gitFileSelect) gitFileSelect.value = targetAutoFile;
                            fetchAndLoadFile(targetAutoFile);
                        }
                    } else if (statusData.status === 'error') {
                        clearInterval(poll);
                        hideLoadingOverlay();
                        fetchRepoBtn.disabled = false;
                        gitFetchStatus.textContent = `Error: ${statusData.error}`;
                        gitFetchStatus.className = 'error';
                    }
                } catch (pollError) {
                    console.error("Polling error:", pollError);
                }
            }, 500);

        } catch (error) {
            console.error('Error fetching repo files:', error);
            gitFetchStatus.textContent = `Error: ${error.message}`;
            gitFetchStatus.className = 'error';
            fetchRepoBtn.disabled = false;
            hideLoadingOverlay();
        }
    });
    
    btnLimparEditor.addEventListener('click', () => {
        editor.setValue('');
        gitRepoUrl.value = '';
        gitMainFile.value = '';
        if (gitFileSelect) {
            gitFileSelect.innerHTML = '<option value="">📂 Arquivos da pasta...</option>';
            gitFileSelect.style.display = 'none';
        }
        if (gitFolderScopeBadge) gitFolderScopeBadge.style.display = 'none';
        window.REPO_ALL_FILES = [];
        gitFileListDatalist.innerHTML = '';
        gitFetchStatus.textContent = '';
        validateInputs();
        editor.focus();
    });
    btnSelecionarTudo.addEventListener('click', () => { editor.execCommand('selectAll'); editor.focus(); });
    btnCopiarCodigo.addEventListener('click', async () => {
        const codigo = editor.getValue();
        if (codigo.trim() === '') return; 
        try {
            await navigator.clipboard.writeText(codigo);
            const originalText = btnCopiarCodigo.textContent;
            btnCopiarCodigo.textContent = 'Copied!';
            setTimeout(() => { btnCopiarCodigo.textContent = originalText; }, 2000); 
        } catch (err) { alert('Could not copy code.'); }
    });

    languageRadios.forEach(radio => radio.addEventListener('change', () => {
        toggleLanguageOptions();
        validateInputs();
    }));

    document.getElementById('fileInput').addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (!file) return;
        gitRepoUrl.value = '';
        gitMainFile.value = '';
        if (gitFileSelect) {
            gitFileSelect.innerHTML = '<option value="">📂 Arquivos da pasta...</option>';
            gitFileSelect.style.display = 'none';
        }
        if (gitFolderScopeBadge) gitFolderScopeBadge.style.display = 'none';
        window.REPO_ALL_FILES = [];
        gitFileListDatalist.innerHTML = '';
        gitFetchStatus.textContent = '';
        const fileName = file.name;
        const fileExtension = fileName.slice(fileName.lastIndexOf('.'));
        if (fileExtension === '.c') document.getElementById('lang-c').checked = true;
        else if (fileExtension === '.cpp') document.getElementById('lang-cpp').checked = true;
        else if (fileExtension === '.py') document.getElementById('lang-py').checked = true;
        else document.getElementById('lang-cpp').checked = true;
        toggleLanguageOptions();
        const reader = new FileReader();
        reader.onload = (e) => { editor.setValue(e.target.result); validateInputs(); };
        reader.readAsText(file);
    });
    
    document.getElementById('dependencyInput').addEventListener('change', async (event) => {
        const files = Array.from(event.target.files);
        event.target.value = ''; 
        if (files.length === 0) return;
        const readPromises = files.map(file => {
            if (dependencyFiles.some(dep => dep.filename === file.name)) return Promise.resolve(null); 
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

    tabDashboard.addEventListener('click', () => {
        dashboard.style.display = 'block'; resultadoTextoContainer.style.display = 'none'; htmlReportContainer.style.display = 'none'; yamlReportContainer.style.display = 'none'; graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.add('active'); tabRawText.classList.remove('active'); tabHtmlReport.classList.remove('active'); tabYamlReport.classList.remove('active'); tabGraphmlReport.classList.remove('active');
    });

    tabRawText.addEventListener('click', () => {
        dashboard.style.display = 'none'; resultadoTextoContainer.style.display = 'block'; htmlReportContainer.style.display = 'none'; yamlReportContainer.style.display = 'none'; graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active'); tabRawText.classList.add('active'); tabHtmlReport.classList.remove('active'); tabYamlReport.classList.remove('active'); tabGraphmlReport.classList.remove('active');
    });

    tabHtmlReport.addEventListener('click', () => {
        dashboard.style.display = 'none'; resultadoTextoContainer.style.display = 'none'; htmlReportContainer.style.display = 'block'; yamlReportContainer.style.display = 'none'; graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active'); tabRawText.classList.remove('active'); tabHtmlReport.classList.add('active'); tabYamlReport.classList.remove('active'); tabGraphmlReport.classList.remove('active');
    });

    tabYamlReport.addEventListener('click', () => {
        dashboard.style.display = 'none'; resultadoTextoContainer.style.display = 'none'; htmlReportContainer.style.display = 'none'; yamlReportContainer.style.display = 'block'; graphmlReportContainer.style.display = 'none';
        tabDashboard.classList.remove('active'); tabRawText.classList.remove('active'); tabHtmlReport.classList.remove('active'); tabYamlReport.classList.add('active'); tabGraphmlReport.classList.remove('active');
    });

    tabGraphmlReport.addEventListener('click', () => {
        dashboard.style.display = 'none'; resultadoTextoContainer.style.display = 'none'; htmlReportContainer.style.display = 'none'; yamlReportContainer.style.display = 'none'; graphmlReportContainer.style.display = 'block';
        tabDashboard.classList.remove('active'); tabRawText.classList.remove('active'); tabHtmlReport.classList.remove('active'); tabYamlReport.classList.remove('active'); tabGraphmlReport.classList.add('active');
    });

    let currentTaskId = null;
    let pollInterval = null;
    const cancelarBtn = document.getElementById('cancelarBtn');

    // --- PROGRESSÃO: Analisador ESBMC ---
    analisarBtn.addEventListener('click', async () => {
        const codigo = editor.getValue();
        const gitUrlValue = gitRepoUrl.value.trim();
        const gitMainFileValue = gitMainFile.value.trim();
        const linguagemSelecionada = document.querySelector('input[name="language"]:checked').value;
        const pythonInterpreter = document.getElementById('python-interpreter').value;

        const flags = [];
        document.querySelectorAll('.esbmc-flag:checked').forEach(cb => flags.push(cb.value));
        document.querySelectorAll('.esbmc-param').forEach(input => {
            if (input.value.trim()) { flags.push(input.dataset.flag); flags.push(input.value.trim()); }
        });

        const selectedSolver = document.getElementById('solver-select').value;
        if (selectedSolver) flags.push(selectedSolver);
        
        const hasGraphmlOutput = flags.includes('--witness-output');
        const hasYamlOutput = flags.includes('--witness-output-yaml');
        const hasHtmlReportFlag = flags.includes('--generate-html-report');

        if (linguagemSelecionada === 'c' || linguagemSelecionada === 'cpp' || linguagemSelecionada === 'python') {
            if (!hasHtmlReportFlag) flags.push('--generate-html-report');
            if (!hasGraphmlOutput) { flags.push('--witness-output'); flags.push('auto-witness.graphml'); }
            if (!hasYamlOutput) { flags.push('--witness-output-yaml'); flags.push('auto-witness.yaml'); }
        }

        dashboard.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        
        // ... (dentro do analisarBtn.addEventListener, sensivelmente na linha 250) ...
        
        // ...
        tabsContainer.style.display = 'flex';
        tabRawText.click(); 
        
        const verificationModeSelect = document.getElementById('verificationModeSelect');
        const selectedEngineMode = verificationModeSelect ? verificationModeSelect.value : 'assisted';

        if (selectedEngineMode === 'raw_esbmc') {
            resultadoTexto.textContent = "Connecting to server...\n[SYSTEM] [Strict Pure ESBMC Baseline] Running 100% Unmodified ESBMC (No Slicing / No Homogenizer v2.0)...\n";
        } else if (linguagemSelecionada === 'python') {
            resultadoTexto.textContent = "Connecting to server...\n[SYSTEM] Running ESBMC Homogenizer v2.0 (AST & Dependency Sanitizer)...\n";
        } else {
            resultadoTexto.textContent = "Connecting to the analysis server...\n";
        }
        
        analisarBtn.style.display = 'none';
        cancelarBtn.style.display = 'block';
        cancelarBtn.textContent = 'Stop Analysis & Consolidate Results';

        // ATIVA O PAINEL DE PROGRESSO EM TEMPO REAL
        initLiveProgressPanel(
            selectedEngineMode === 'raw_esbmc'
                ? 'Running 100% Strict Pure ESBMC (Baseline SV-COMP without Homogenizer)...'
                : (linguagemSelecionada === 'python'
                    ? 'Sanitizing dependencies with ESBMC Homogenizer v2.0 & running ESBMC...'
                    : 'Running formal symbolic verification with ESBMC...'),
            false
        );

        try {
            const requestBody = {
                flags,
                language: linguagemSelecionada,
                verification_engine_mode: selectedEngineMode,
                codigo: codigo,
                dependencies: dependencyFiles
            };
            if (gitUrlValue && gitMainFileValue) {
                requestBody.git_url = gitUrlValue;
                requestBody.main_file_path = gitMainFileValue;
            }
            if (linguagemSelecionada === 'python' && pythonInterpreter) {
                requestBody.python_interpreter = pythonInterpreter;
            }

            const response = await fetch('http://127.0.0.1:5000/analisar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();
            
            if (response.status >= 400 && data.error) {
                 alert('Error: ' + data.error);
                 resetAnalysisButtons();
                 return;
            }

            currentTaskId = data.task_id;
            pollInterval = setInterval(checkStatus, 1000);

        } catch (error) {
            alert('Error connecting to the analysis server.');
            console.error('Erro:', error);
            resetAnalysisButtons();
        }
    });

    const exploreRepoBtn = document.getElementById('exploreRepoBtn');
    const repoSubdirFilter = document.getElementById('repoSubdirFilter');
    const maxRepoFilesSelect = document.getElementById('maxRepoFilesSelect');
    const repoLangFilterSelect = document.getElementById('repoLangFilterSelect');
    let latestLatexTable = '';
    let latestCsvReport = '';

    const copyLatexBtn = document.getElementById('copyLatexBtn');
    if (copyLatexBtn) {
        copyLatexBtn.addEventListener('click', () => {
            if (!latestLatexTable) {
                alert('No LaTeX table available yet. Run a Repository Exploration first.');
                return;
            }
            navigator.clipboard.writeText(latestLatexTable).then(() => {
                const orig = copyLatexBtn.innerHTML;
                copyLatexBtn.innerHTML = '✅ Copied LaTeX to Clipboard!';
                setTimeout(() => { copyLatexBtn.innerHTML = orig; }, 2500);
            });
        });
    }

    const downloadCsvBtn = document.getElementById('downloadCsvBtn');
    if (downloadCsvBtn) {
        downloadCsvBtn.addEventListener('click', () => {
            if (!latestCsvReport) {
                alert('No CSV metrics available yet. Run a Repository Exploration first.');
                return;
            }
            const blob = new Blob([latestCsvReport], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'reposlice_bmc_metrics.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });
    }

    if (exploreRepoBtn) {
        exploreRepoBtn.addEventListener('click', async () => {
            const gitUrlValue = gitRepoUrl.value.trim();
            if (!gitUrlValue) {
                alert('Please enter a Git Repository URL first to run Multi-Directory Repository Exploration.');
                return;
            }
            const linguagemSelecionada = document.querySelector('input[name="language"]:checked').value;
            const pythonInterpreter = document.getElementById('python-interpreter').value.trim();
            const flags = [];
            document.querySelectorAll('.esbmc-flag:checked').forEach(cb => flags.push(cb.value));
            const solverSelect = document.getElementById('solver-select');
            if (solverSelect && solverSelect.value) flags.push(solverSelect.value);
            document.querySelectorAll('.esbmc-param').forEach(input => {
                const value = input.value.trim();
                const flag = input.dataset.flag;
                if (value !== '') {
                    if ((flag === '--witness-output' || flag === '--witness-output-yaml') && value.toLowerCase() === 'auto') {
                        flags.push(flag);
                        flags.push(flag === '--witness-output' ? 'auto-witness.graphml' : 'auto-witness.yaml');
                    } else {
                        flags.push(flag);
                        flags.push(value);
                    }
                }
            });

            dashboard.style.display = 'none';
            htmlReportContainer.style.display = 'none';
            yamlReportContainer.style.display = 'none';
            graphmlReportContainer.style.display = 'none';
            tabsContainer.style.display = 'flex';
            tabRawText.click();

            resultadoTexto.textContent = (
                "Connecting to server...\n" +
                "[SYSTEM] [RepoSlice-BMC] Starting Multi-Directory Repository Exploration & Slicing Algorithm...\n"
            );
            analisarBtn.style.display = 'none';
            cancelarBtn.style.display = 'block';
            cancelarBtn.textContent = 'Stop Analysis & Consolidate Results';

            initLiveProgressPanel(
                'Clonando repositório Git e iniciando varredura estratificada RepoSlice-BMC...',
                true
            );

            try {
                const parsedMaxFiles = maxRepoFilesSelect ? parseInt(maxRepoFilesSelect.value, 10) : 0;
                const selectedRepoLang = repoLangFilterSelect ? repoLangFilterSelect.value : 'auto';
                const verificationModeSelect = document.getElementById('verificationModeSelect');
                const selectedEngineMode = verificationModeSelect ? verificationModeSelect.value : 'assisted';
                const testSuiteModeCheck = document.getElementById('testSuiteModeCheck');
                const testSuiteMode = testSuiteModeCheck ? testSuiteModeCheck.checked : false;
                const verificationPhasesSelect = document.getElementById('verificationPhasesSelect');
                const selectedPhases = verificationPhasesSelect ? verificationPhasesSelect.value : 'both';

                const requestBody = {
                    flags,
                    language: selectedRepoLang === 'auto' ? 'all' : selectedRepoLang,
                    repo_lang_filter: selectedRepoLang,
                    verification_engine_mode: selectedEngineMode,
                    test_suite_mode: testSuiteMode,
                    verification_phases: selectedPhases,
                    git_url: gitUrlValue,
                    explore_repo: true,
                    repo_subdir_filter: repoSubdirFilter ? repoSubdirFilter.value.trim() : '',
                    max_repo_files: !Number.isNaN(parsedMaxFiles) ? parsedMaxFiles : 0,
                    codigo: '',
                    dependencies: dependencyFiles
                };
                if ((linguagemSelecionada === 'python' || selectedRepoLang === 'python') && pythonInterpreter) {
                    requestBody.python_interpreter = pythonInterpreter;
                }
                const response = await fetch('http://127.0.0.1:5000/analisar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                const data = await response.json();
                if (response.status >= 400 && data.error) {
                    alert('Error: ' + data.error);
                    resetAnalysisButtons();
                    return;
                }
                currentTaskId = data.task_id;
                pollInterval = setInterval(checkStatus, 1000);
            } catch (error) {
                alert('Error connecting to the analysis server.');
                console.error('Erro:', error);
                resetAnalysisButtons();
            }
        });
    }

    async function checkStatus() {
        if (!currentTaskId) return;

        try {
            const res = await fetch(`http://127.0.0.1:5000/status/${currentTaskId}`);
            const data = await res.json();

            resultadoTexto.textContent = data.logs;
            resultadoTextoContainer.scrollTop = resultadoTextoContainer.scrollHeight;

            if (data.progresso && data.progresso.total > 0) {
                const prog = data.progresso;
                const cur = Math.min(prog.current || 1, prog.total);
                const tot = prog.total;
                const pct = Math.max(5, Math.min(100, Math.round((cur / tot) * 100)));

                const statusText = document.getElementById('live-progress-status-text');
                const counterBadge = document.getElementById('live-progress-counter-badge');
                const scoreboard = document.getElementById('live-progress-scoreboard');
                const barFill = document.getElementById('live-progress-bar-fill');
                const previewWrapper = document.getElementById('live-streaming-preview-wrapper');
                const previewTbody = document.getElementById('live-streaming-preview-tbody');

                if (counterBadge) {
                    counterBadge.textContent = `Teste ${cur}/${tot} (${pct}%)`;
                }
                if (statusText) {
                    const langTag = prog.current_lang ? `[${prog.current_lang}] ` : '';
                    const fileTag = prog.current_file || 'Aguardando...';
                    statusText.innerHTML = `<span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid var(--primary); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span> <span>Verificando <strong>${cur}/${tot}</strong>: <code>${langTag}${fileTag}</code></span>`;
                }
                if (scoreboard) {
                    const passBug = prog.pass_bug_count || 0;
                    const passSafe = prog.pass_safe_count || 0;
                    const regrCount = prog.regression_count || 0;
                    if (prog.test_suite_mode || passBug > 0 || regrCount > 0) {
                        scoreboard.innerHTML = `🟢 PASS (Bugs): <strong>${passBug}</strong> | 🛡️ PASS (Safe): <strong>${passSafe}</strong> | 🔴 REGRESSÕES: <strong style="color:#dc2626;">${regrCount}</strong> | 📐 VCCs: <strong>${prog.total_vccs || 0}</strong>`;
                    } else {
                        scoreboard.innerHTML = `✅ SAFE: <strong>${prog.safe_count || 0}</strong> | ❌ VIOLATION: <strong style="color:#dc2626;">${prog.violation_count || 0}</strong> | 📐 VCCs: <strong>${prog.total_vccs || 0}</strong> | 🔗 SSA: <strong>${prog.total_ssa || 0}</strong>`;
                    }
                }
                if (barFill) {
                    barFill.style.width = `${pct}%`;
                }
                if (previewWrapper && previewTbody && Array.isArray(prog.partial_summary) && prog.partial_summary.length > 0) {
                    previewWrapper.style.display = 'block';
                    previewTbody.innerHTML = '';
                    prog.partial_summary.forEach(item => {
                        const tr = previewTbody.insertRow();
                        const isViol = String(item.status).startsWith('VIOLATION');
                        const badgeColor = isViol ? '#dc2626' : '#059669';
                        const witnessOrMode = item.z3_witness
                            ? `<span style="color:#dc2626; font-weight:600;">❌ ${item.z3_witness}</span>`
                            : `<span style="color:#4f46e5; font-weight:600;">${item.mode || 'Symbolic BMC'}</span>`;

                        const phaseBadge = item.phase
                            ? `<span style="background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:3px; font-size:10px; font-weight:600; white-space:nowrap;">${item.phase.split(':')[0]}</span>`
                            : `<span style="color:#94a3b8;">-</span>`;

                        let testStatusHtml = '<span style="color:#94a3b8;">-</span>';
                        if (item.test_status) {
                            let tsColor = '#059669';
                            if (item.test_status.includes('REGRESSÃO') || item.test_status.includes('VIOLAÇÃO')) tsColor = '#dc2626';
                            else if (item.test_status.includes('PASS')) tsColor = '#059669';
                            testStatusHtml = `<span style="background:${tsColor}; color:#fff; padding:1px 6px; border-radius:3px; font-size:10.5px; font-weight:700; white-space:nowrap;">${item.test_status}</span>`;
                        }

                        tr.innerHTML = `
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><strong>${item.index}/${tot}</strong></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><span style="background:#e0e7ff; color:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700; font-size:10.5px;">${item.lang || 'C/C++'}</span></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${phaseBadge}</td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><code>${item.directory}/${item.file}</code></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${witnessOrMode}</td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><strong>${item.vccs || 0}</strong> <small style="color:#64748b;">(${item.ssa_assigns || 0} SSA)</small></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><code>${item.wall_time || '-'}</code></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><span style="background:${badgeColor}; color:#fff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:700;">${item.status}</span></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${testStatusHtml}</td>
                        `;
                    });
                    previewWrapper.scrollTop = previewWrapper.scrollHeight;
                }
            }

            if (data.status === 'consolidating') {
                const statusText = document.getElementById('live-progress-status-text');
                if (statusText) {
                    statusText.innerHTML = `<span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid #059669; border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span> <span style="color:#059669;">⏳ Consolidando Dashboard, Tabela LaTeX e CSV dos módulos já verificados...</span>`;
                }
                return;
            }

            if (data.status === 'completed' || data.status === 'error' || data.status === 'cancelled') {
                clearInterval(pollInterval);
                resetAnalysisButtons();

                if (data.resultado) {
                    processCompletedAnalysis(data.resultado);
                } else if (data.progresso && Array.isArray(data.progresso.partial_summary) && data.progresso.partial_summary.length > 0) {
                    processCompletedAnalysis({
                        verificacao_sucesso: (data.progresso.violation_count || 0) === 0,
                        dashboard_data: [],
                        repo_exploration_summary: data.progresso.partial_summary,
                        codigo_analisado: data.logs || '// Consolidated Partial Repository Run'
                    });
                }
            }
        } catch (error) {
            console.error("Erro ao verificar status:", error);
        }
    }

    function processCompletedAnalysis(resultado) {
        tabHtmlReport.style.display = 'none'; 
        tabYamlReport.style.display = 'none';
        tabGraphmlReport.style.display = 'none';
        latestLatexTable = resultado.latex_table || '';
        latestCsvReport = resultado.csv_report || '';

        if (resultado.html_report_data) {
            htmlReportIframe.srcdoc = resultado.html_report_data;
            tabHtmlReport.style.display = 'inline-block';
        }

        if (resultado.yaml_report_data) {
            yamlReportPre.textContent = resultado.yaml_report_data;
            tabYamlReport.style.display = 'inline-block';
        }

        if (resultado.graphml_report_data) {
            graphmlReportPre.textContent = resultado.graphml_report_data;
            tabGraphmlReport.style.display = 'inline-block';
        }

        const hasRepoSummary = Array.isArray(resultado.repo_exploration_summary) && resultado.repo_exploration_summary.length > 0;
        const hasDashboardItems = Array.isArray(resultado.dashboard_data) && resultado.dashboard_data.length > 0;
        if (hasRepoSummary || hasDashboardItems || resultado.verificacao_sucesso || resultado.codigo_analisado) {
            renderDashboard(
                resultado.dashboard_data || [],
                resultado.codigo_analisado || '// Consolidated Formal Verification Report',
                resultado.repo_exploration_summary || null
            );
            tabDashboard.click(); 
        }
    }

    cancelarBtn.addEventListener('click', async () => {
        if (!currentTaskId) return;
        cancelarBtn.textContent = 'Consolidating partial results & stopping...';
        cancelarBtn.disabled = true;
        await fetch(`http://127.0.0.1:5000/cancelar/${currentTaskId}`, { method: 'POST' });
    });

    function resetAnalysisButtons() {
        analisarBtn.style.display = 'block';
        cancelarBtn.style.display = 'none';
        cancelarBtn.disabled = false;
        analysisProgressContainer.style.display = 'none'; // DESATIVA A BARRA INLINE
        validateInputs(); 
    }     

    function renderDashboard(resultsArray, codigoFonte, repoExplorationSummary = null) {
        const statusBanner = document.getElementById('status-banner');
        const cardModulosAuditados = document.getElementById('card-modulos-auditados');
        const cardModulosSafe = document.getElementById('card-modulos-safe');
        const cardTotalVccs = document.getElementById('card-total-vccs');
        const cardTotalSsa = document.getElementById('card-total-ssa');
        const cardPassos = document.getElementById('card-total-passos');
        const cardViolacoes = document.getElementById('card-violacoes');
        const violacoesTabela = document.getElementById('violacoes-tabela');
        const valoresIniciais = document.getElementById('valores-iniciais');
        const codigoContainer = document.getElementById('codigo-fonte-container');
        const traceExecucao = document.getElementById('traço-execucao');
        const sucessoSection = document.getElementById('sucesso-section');
        const repoExplorerSection = document.getElementById('repo-explorer-section');
        const repoExplorerTabela = document.getElementById('repo-explorer-tabela');

        if (sucessoSection) sucessoSection.style.display = 'none';
        if (repoExplorerSection) repoExplorerSection.style.display = 'none';
        if (repoExplorerTabela) repoExplorerTabela.innerHTML = '';
        document.getElementById('violacoes-section').style.display = 'none';
        document.getElementById('contraexemplo-section').style.display = 'none';
        document.getElementById('trace-section').style.display = 'none';
        violacoesTabela.innerHTML = '';
        valoresIniciais.textContent = '';
        traceExecucao.textContent = '';

        let totalVccsSum = 0;
        let totalSsaSum = 0;
        let safeModulesSum = 0;
        let auditedModulesSum = 1;
        currentRepoExplorationSummary = repoExplorationSummary || [];

        let currentRepoFilter = 'all';

        function renderRepoExplorerRows(summaryList) {
            if (!repoExplorerTabela) return;
            repoExplorerTabela.innerHTML = '';

            const filtered = summaryList.filter(item => {
                if (currentRepoFilter === 'all') return true;
                const code = item.test_status_code || '';
                const desc = item.test_status || '';
                if (currentRepoFilter === 'pass_bug') {
                    return code === 'PASS_BUG_FOUND' || desc.includes('Bug Encontrado');
                }
                if (currentRepoFilter === 'pass_safe') {
                    return code === 'PASS_SOUND' || desc.includes('Provado Seguro') || (!code && String(item.status).includes('SAFE'));
                }
                if (currentRepoFilter === 'regression') {
                    return code === 'REGRESSION_FAILED' || desc.includes('REGRESSÃO') || (!code && String(item.status).includes('VIOLATION'));
                }
                return true;
            });

            if (filtered.length === 0) {
                const tr = repoExplorerTabela.insertRow();
                tr.innerHTML = `<td colspan="12" style="text-align:center; padding:20px; color:#64748b;">Nenhum módulo corresponde ao filtro selecionado.</td>`;
                return;
            }

            filtered.forEach(item => {
                const statusStr = String(item.status || '');
                const tr = repoExplorerTabela.insertRow();
                let statusColor = '#059669'; // Emerald for VERIFIED SOUND
                if (statusStr.startsWith('VIOLATION [NATIVE BUG]')) statusColor = '#dc2626';
                else if (statusStr.startsWith('VIOLATION')) statusColor = '#ea580c';
                else if (statusStr.startsWith('RAW ERROR')) statusColor = '#b45309';
                else if (statusStr.startsWith('BOUNDED SAFE')) statusColor = '#2563eb';
                else if (statusStr.startsWith('SLICED SAFE')) statusColor = '#4f46e5';
                else if (statusStr.startsWith('STATIC SAFE')) statusColor = '#0d9488';
                const statusBadge = `<span class="severity-badge" style="background-color: ${statusColor};">${item.status}</span>`;
                const langBadge = `<span style="background:#e0e7ff; color:#3730a3; padding:2px 7px; border-radius:4px; font-weight:700; font-size:11px;">${item.lang || 'C/C++'}</span>`;
                const phaseBadge = item.phase
                    ? `<span style="background:#fef3c7; color:#92400e; padding:2px 6px; border-radius:4px; font-weight:700; font-size:10.5px; white-space:nowrap;">${item.phase.split(':')[0]}</span>`
                    : `<span style="color:#94a3b8;">-</span>`;

                let testStatusBadge = '<span style="color:#94a3b8;">-</span>';
                if (item.test_status) {
                    let tsColor = '#059669';
                    let tsBg = '#ecfdf5';
                    let tsBorder = '#10b981';
                    if (item.test_status.includes('REGRESSÃO') || item.test_status.includes('VIOLAÇÃO')) {
                        tsColor = '#dc2626';
                        tsBg = '#fef2f2';
                        tsBorder = '#ef4444';
                    } else if (item.test_status.includes('PASS')) {
                        tsColor = '#059669';
                        tsBg = '#ecfdf5';
                        tsBorder = '#10b981';
                    }
                    const oracleSubtext = item.expected_verdict
                        ? `<div style="font-size:10px; color:#64748b; margin-top:2px;">Esp: <code>${item.expected_verdict}</code></div>`
                        : '';
                    testStatusBadge = `<div style="display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; background:${tsBg}; color:${tsColor}; border:1px solid ${tsBorder}; white-space:nowrap;">${item.test_status}</div>${oracleSubtext}`;
                }

                const ssaVccStr = (item.vccs !== undefined) ? `<strong>${item.vccs} VCCs</strong> <small style="color:#64748b;">(${item.ssa_assigns || 0} SSA)</small>` : `Score ${item.score}`;
                const cliSubtext = item.esbmc_cli
                    ? `<div style="margin-top:4px; font-family:monospace; font-size:10.5px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:4px; padding:2px 6px; word-break:break-all;" title="Exact Reproducible ESBMC CLI Command">💻 ${item.esbmc_cli}</div>`
                    : '';
                const witnessHtml = item.z3_witness
                    ? `<div style="color:#dc2626; font-weight:600; font-size:12px;">❌ ${item.z3_witness}</div>${cliSubtext}`
                    : `<div><span style="font-weight:600; color:#4f46e5;">${item.mode || 'Symbolic BMC'}</span> <small style="color:#64748b;">(Score ${item.score})</small></div>${cliSubtext}`;

                tr.innerHTML = `
                    <td><strong>${item.index}</strong></td>
                    <td>${langBadge}</td>
                    <td>${phaseBadge}</td>
                    <td><code>${item.directory}</code></td>
                    <td><strong>${item.file}</strong></td>
                    <td>${witnessHtml}</td>
                    <td><code>${item.fused_names}</code> <small>(${item.fused_deps})</small></td>
                    <td>${ssaVccStr}</td>
                    <td><code>${item.wall_time || '-'}</code></td>
                    <td>${statusBadge}</td>
                    <td>${testStatusBadge}</td>
                    <td style="text-align:center;">
                        <button class="btn-ver-homogeneizado btn-editor" data-index="${item.index}" style="padding: 4px 10px; font-size: 11px; background: #0284c7; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; white-space: nowrap;">
                            👁️ Ver Código
                        </button>
                    </td>
                `;
            });
        }

        if (repoExplorationSummary && Array.isArray(repoExplorationSummary) && repoExplorationSummary.length > 0 && repoExplorerSection && repoExplorerTabela) {
            repoExplorerSection.style.display = 'block';
            auditedModulesSum = repoExplorationSummary.length;
            repoExplorationSummary.forEach(item => {
                totalVccsSum += Number(item.vccs || 0);
                totalSsaSum += Number(item.ssa_assigns || 0);
                const statusStr = String(item.status || '');
                if (!statusStr.startsWith('VIOLATION') && !statusStr.startsWith('RAW ERROR')) safeModulesSum++;
            });
            renderRepoExplorerRows(repoExplorationSummary);

            if (!window._filterListenersAttached) {
                window._filterListenersAttached = true;
                document.querySelectorAll('.btn-filter-status').forEach(btn => {
                    btn.addEventListener('click', () => {
                        document.querySelectorAll('.btn-filter-status').forEach(b => {
                            b.classList.remove('active');
                            b.style.background = '#fff';
                            if (b.dataset.filter === 'all') b.style.color = '#334155';
                            else if (b.dataset.filter === 'pass_bug') b.style.color = '#16a34a';
                            else if (b.dataset.filter === 'pass_safe') b.style.color = '#0284c7';
                            else if (b.dataset.filter === 'regression') b.style.color = '#dc2626';
                        });
                        btn.classList.add('active');
                        if (btn.dataset.filter === 'all') {
                            btn.style.background = '#334155';
                            btn.style.color = '#f8fafc';
                        } else if (btn.dataset.filter === 'pass_bug') {
                            btn.style.background = '#16a34a';
                            btn.style.color = '#fff';
                        } else if (btn.dataset.filter === 'pass_safe') {
                            btn.style.background = '#0284c7';
                            btn.style.color = '#fff';
                        } else if (btn.dataset.filter === 'regression') {
                            btn.style.background = '#dc2626';
                            btn.style.color = '#fff';
                        }
                        currentRepoFilter = btn.dataset.filter;
                        if (currentRepoExplorationSummary && currentRepoExplorationSummary.length > 0) {
                            renderRepoExplorerRows(currentRepoExplorationSummary);
                        }
                    });
                });
            }

            if (repoExplorerTabela && !repoExplorerTabela.dataset.hasHomogenizedListener) {
                repoExplorerTabela.dataset.hasHomogenizedListener = "true";
                repoExplorerTabela.addEventListener('click', (e) => {
                    const btn = e.target.closest('.btn-ver-homogeneizado');
                    if (!btn) return;
                    const idx = parseInt(btn.dataset.index, 10);
                    const item = (currentRepoExplorationSummary || []).find(r => r.index === idx);
                    if (item) {
                        abrirModalHomogeneizado(item);
                    }
                });
            }
        }

        const violationDetails = [];
        resultsArray.forEach(result => {
            if (result.status === 'violation' && result.steps) {
                result.steps.forEach(step => {
                    if (step.type === 'violation') {
                        const loc = step.location || {};
                        violationDetails.push({
                            file: loc.file || step.file || 'N/A',
                            function: loc.function || step.function || 'N/A',
                            line: loc.line || step.line || 'N/A',
                            message: step.message || 'Description not available',
                            cwe: step.cwe || 'N/A', 
                            severity: step.severity || 'N/A' 
                        });
                    }
                });
            }
        });

        cardViolacoes.textContent = violationDetails.length;
        const hasViolations = violationDetails.length > 0;

        if (!repoExplorationSummary || !Array.isArray(repoExplorationSummary) || repoExplorationSummary.length === 0) {
            auditedModulesSum = 1;
            safeModulesSum = hasViolations ? 0 : 1;
            totalSsaSum = resultsArray[0]?.steps?.length || 0;
            totalVccsSum = hasViolations ? violationDetails.length : 1;
        }
        if (cardModulosAuditados) cardModulosAuditados.textContent = auditedModulesSum;
        if (cardModulosSafe) cardModulosSafe.textContent = safeModulesSum;
        if (cardTotalVccs) cardTotalVccs.textContent = totalVccsSum;
        if (cardTotalSsa) cardTotalSsa.textContent = totalSsaSum;

        if (hasViolations) {
            const firstResultWithViolation = resultsArray.find(res => res.status === 'violation');
            statusBanner.className = 'status-banner failed';
            statusBanner.textContent = `❌ VERIFICATION FAILED (${violationDetails.length} VIOLATION(S))`;
            cardViolacoes.className = 'value red';
            cardViolacoes.style.color = '';
            document.getElementById('violacoes-section').style.display = 'block';
            document.getElementById('contraexemplo-section').style.display = 'block';
            document.getElementById('trace-section').style.display = 'block';
            cardPassos.textContent = firstResultWithViolation.steps ? firstResultWithViolation.steps.length : 0;
            violationDetails.forEach(v => {
                const row = violacoesTabela.insertRow();
                let cweHtml = v.cwe;
                if (v.cwe !== 'N/A') {
                    const cweNumber = v.cwe.replace('CWE-', ''); 
                    cweHtml = `<a href="https://cwe.mitre.org/data/definitions/${cweNumber}.html" target="_blank" style="color: #007bff; text-decoration: none; font-weight: bold;" title="View MITRE Specification">${v.cwe}</a>`;
                }

                let badgeClass = 'severity-na';
                if (v.severity === 'Critical') badgeClass = 'severity-critical';
                else if (v.severity === 'High') badgeClass = 'severity-high';
                else if (v.severity === 'Medium') badgeClass = 'severity-medium';
                else if (v.severity === 'Low') badgeClass = 'severity-low';

                let severityHtml = `<span class="severity-badge ${badgeClass}">${v.severity}</span>`;
                row.innerHTML = `<td>${v.file}</td><td>${v.function}</td><td>${v.line}</td><td>${v.message}</td><td>${cweHtml}</td><td>${severityHtml}</td>`;
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
            statusBanner.textContent = '✅ VERIFICATION SUCCESSFUL — STATUS: OK (NENHUMA VULNERABILIDADE ENCONTRADA)';
            cardViolacoes.className = 'value';
            cardViolacoes.style.color = 'var(--success)';
            if (sucessoSection) sucessoSection.style.display = 'block';
            cardPassos.textContent = resultsArray[0]?.steps?.length || 0;
        }

        // Se for exploração de suíte de testes profissional com oráculos esperados:
        if (repoExplorationSummary && Array.isArray(repoExplorationSummary) && repoExplorationSummary.length > 0) {
            const hasOracles = repoExplorationSummary.some(it => it.expected_verdict);
            const regressions = repoExplorationSummary.filter(it => it.test_status_code === 'REGRESSION_FAILED' || (it.test_status && it.test_status.includes('REGRESSÃO')));
            const passBugs = repoExplorationSummary.filter(it => it.test_status_code === 'PASS_BUG_FOUND' || (it.test_status && it.test_status.includes('Bug Encontrado')));
            const passSafe = repoExplorationSummary.filter(it => it.test_status_code === 'PASS_SOUND' || (it.test_status && it.test_status.includes('Provado Seguro')));

            if (hasOracles) {
                if (regressions.length > 0) {
                    statusBanner.className = 'status-banner failed';
                    statusBanner.textContent = `🔴 SUÍTE DE TESTES: ${regressions.length} REGRESSÃO(ÕES) DETECTADA(S) (DIVERGÊNCIA DE ORÁCULO)`;
                } else {
                    statusBanner.className = 'status-banner success';
                    statusBanner.textContent = `🟢 SUÍTE DE TESTES APROVADA: ${passBugs.length} BUG(S) CONFIRMADO(S) + ${passSafe.length} PROVADO(S) SEGURO(S) [100% ORÁCULOS ATENDIDOS]`;
                }
            }
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

    toggleLanguageOptions();
    validateInputs();

    helpBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        helpTextContent.textContent = 'Loading...';
        helpModal.style.display = 'block';
        try {
            const response = await fetch('http://127.0.0.1:5000/help', { method: 'GET', cache: 'no-store' });
            const data = await response.json();
            helpTextContent.textContent = data.help_text;
        } catch (error) {
            helpTextContent.textContent = 'Error connecting to the server to get help text.';
        }
    });

    modalCloseBtn.addEventListener('click', () => { helpModal.style.display = 'none'; });
    window.addEventListener('click', (event) => { if (event.target == helpModal) helpModal.style.display = 'none'; });

    // --- Modal do Código Homogeneizado & Fatiado (Input ESBMC/Z3) ---
    function abrirModalHomogeneizado(item) {
        const modal = document.getElementById('homogenizedModal');
        const modalCode = document.getElementById('homogenizedModalCode');
        const modalMeta = document.getElementById('homogenizedModalMeta');
        const modalTitle = document.getElementById('homogenizedModalTitle');
        if (!modal || !modalCode) return;

        if (modalTitle) {
            modalTitle.textContent = `📄 Código Homogeneizado & Fatiado: ${item.file}`;
        }
        if (modalMeta) {
            modalMeta.innerHTML = `
                <div><strong>Módulo:</strong> <code>${item.directory}/${item.file}</code> &nbsp;|&nbsp; <strong>Linguagem:</strong> <span style="background:#e0e7ff; color:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700;">${item.lang}</span> &nbsp;|&nbsp; <strong>Modo:</strong> <em>${item.mode}</em></div>
                <div style="margin-top:4px;"><strong>Veredito Formal:</strong> <strong>${item.status}</strong> &nbsp;|&nbsp; <strong>VCCs:</strong> ${item.vccs || 0} &nbsp;|&nbsp; <strong>Atribuições SSA:</strong> ${item.ssa_assigns || 0} &nbsp;|&nbsp; <strong>Tempo:</strong> ${item.wall_time || '-'}</div>
                ${item.esbmc_cli ? `<div style="margin-top:4px; font-size:11px; color:#475569;"><strong>CLI Reproduzível:</strong> <code>${item.esbmc_cli}</code></div>` : ''}
            `;
        }

        const codigo = item.homogenized_code || '// Nenhum código intermediário disponível para este módulo.';
        modalCode.textContent = codigo;
        modal.style.display = 'flex';
    }

    const copyHomogenizedCodeBtn = document.getElementById('copyHomogenizedCodeBtn');
    if (copyHomogenizedCodeBtn) {
        copyHomogenizedCodeBtn.addEventListener('click', async () => {
            const modalCode = document.getElementById('homogenizedModalCode');
            if (!modalCode || !modalCode.textContent) return;
            try {
                await navigator.clipboard.writeText(modalCode.textContent);
                const originalText = copyHomogenizedCodeBtn.textContent;
                copyHomogenizedCodeBtn.textContent = '✅ Copiado!';
                setTimeout(() => { copyHomogenizedCodeBtn.textContent = originalText; }, 2000);
            } catch (err) {
                alert('Não foi possível copiar o código.');
            }
        });
    }

    const homogenizedModalClose = document.getElementById('homogenizedModalClose');
    if (homogenizedModalClose) {
        homogenizedModalClose.addEventListener('click', () => {
            const modal = document.getElementById('homogenizedModal');
            if (modal) modal.style.display = 'none';
        });
    }

    window.addEventListener('click', (event) => {
        const modal = document.getElementById('homogenizedModal');
        if (modal && event.target === modal) {
            modal.style.display = 'none';
        }
    });

});