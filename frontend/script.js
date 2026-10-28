document.addEventListener('DOMContentLoaded', () => {
    // Values from ESBMC, the analysed code or a cloned repository are untrusted: escape them in innerHTML (#32)
    const escapeHtml = (value) => (value === undefined || value === null ? '' : String(value))
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    // --- Global Variables and Constants ---
    const analisarBtn = document.getElementById('analisarBtn');
    const esbmcFlags = document.querySelectorAll('.esbmc-flag');
    const esbmcParams = document.querySelectorAll('.esbmc-param');
    const languageRadios = document.querySelectorAll('input[name="language"]');
    const pythonOptions = document.getElementById('python-options');
    const cCppDependencies = document.getElementById('c-cpp-dependencies');
    const dependencyListContainer = document.getElementById('dependency-files-list-container');
    
    // --- Git Variables ---
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

    // --- Editor Button Variables ---
    const btnLimparEditor = document.getElementById('btnLimparEditor');
    const btnSelecionarTudo = document.getElementById('btnSelecionarTudo');
    const btnCopiarCodigo = document.getElementById('btnCopiarCodigo');
    let dependencyFiles = []; 

    // --- Tab and Result Variables ---
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

    // --- Bug Report & Execution Trace Elements (ESBMC GitHub Format) ---
    const tabBugReport = document.getElementById('tab-bug-report');
    const bugReportContainer = document.getElementById('bug-report-container');
    const bugReportPre = document.getElementById('bug-report-pre');
    const bugReportActionBar = document.getElementById('bug-report-action-bar');
    const btnVerRelatorioTab = document.getElementById('btnVerRelatorioTab');
    const btnCopiarRelatorioRapido = document.getElementById('btnCopiarRelatorioRapido');
    const btnGerarPdfRapido = document.getElementById('btnGerarPdfRapido');
    const btnAbrirGithubIssueRapido = document.getElementById('btnAbrirGithubIssueRapido');
    const btnCopiarRelatorio = document.getElementById('btnCopiarRelatorio');
    const btnBaixarRelatorioMd = document.getElementById('btnBaixarRelatorioMd');
    const btnGerarPdf = document.getElementById('btnGerarPdf');
    const btnAbrirGithubIssue = document.getElementById('btnAbrirGithubIssue');

    let latestBugReportMarkdown = '';
    let latestBugReportTitle = '';
    let latestBugReportData = null;
    let latestExecutionFlags = [];
    let latestSelectedLanguage = 'cpp';
    let latestSelectedEngineMode = 'assisted';
    let latestMainFileAnalyzed = 'main.c';

    // --- Metrics and History Module Variables (Codacy Style) ---
    const tabMetricsHistory = document.getElementById('tab-metrics-history');
    const metricsHistoryContainer = document.getElementById('metrics-history-container');
    const btnOpenMetricsHeader = document.getElementById('btnOpenMetricsHeader');
    const btnCarregarDemoCodacy = document.getElementById('btnCarregarDemoCodacy');
    const btnExportarCsvCodacy = document.getElementById('btnExportarCsvCodacy');
    const btnExportarJsonCodacy = document.getElementById('btnExportarJsonCodacy');
    const btnLimparHistoricoCodacy = document.getElementById('btnLimparHistoricoCodacy');
    const filterHistorySearch = document.getElementById('filterHistorySearch');
    const filterHistoryVerdict = document.getElementById('filterHistoryVerdict');
    const tabelaHistoricoBody = document.getElementById('tabela-historico-codacy-body');
    const evolutionChartCanvas = document.getElementById('evolutionChartCanvas');
    const cweChartCanvas = document.getElementById('cweChartCanvas');
    const evolutionChartFallback = document.getElementById('evolutionChartFallback');
    const cweChartFallback = document.getElementById('cweChartFallback');

    const STORAGE_KEY_CODACY_HISTORY = 'esbmc_quality_history_v1';
    let evolutionChartInstance = null;
    let cweChartInstance = null;

    const helpBtn = document.getElementById('helpBtn');
    const helpModal = document.getElementById('helpModal');
    const helpTextContent = document.getElementById('help-text-content');
    const modalCloseBtn = document.querySelector('.modal-close-btn');

    // --- CodeMirror Editor Initialization ---
    const editor = CodeMirror.fromTextArea(document.getElementById('codigoInput'), {
        lineNumbers: true,
        mode: 'text/x-c++src', 
        theme: 'dracula',
        indentUnit: 4,
    });
    const editorWrapper = editor.getWrapperElement();

    // =========================================================================
    // ⏳ PROGRESS AND LOADING SYSTEM (NEW)
    // =========================================================================
    
    function showLoadingOverlay(texto, percent = null) {
        const overlay = document.getElementById('loading-overlay');
        const textElement = overlay.querySelector('.loading-text');
        const progressBarValue = overlay.querySelector('.progress-bar-value');
        
        if (textElement && texto) textElement.textContent = texto;
        
        if (percent !== null) {
            // Stop the infinite CSS animation and use the exact percentage width
            progressBarValue.style.animation = 'none';
            progressBarValue.style.width = `${percent}%`;
        } else {
            // Restore the infinite animation for actions without a percentage (e.g. loading a file)
            progressBarValue.style.animation = 'indeterminate-progress 1.5s ease-in-out infinite';
            progressBarValue.style.width = '100%';
        }
        
        overlay.style.display = 'flex';
    }

    function hideLoadingOverlay() {
        document.getElementById('loading-overlay').style.display = 'none';
    }

    // =========================================================================
    // 🟢 1. SERVER STATUS MONITOR (Silent and Non-Blocking)
    // =========================================================================
    const serverStatusBadge = document.getElementById('server-status-badge');
    const serverStatusDot = document.getElementById('server-status-dot');
    const serverStatusText = document.getElementById('server-status-text');

    async function checkServerHealth() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2500);
            let res = null;
            try {
                res = await fetch('http://127.0.0.1:5000/health', { signal: controller.signal, cache: 'no-store' });
            } catch (e1) {
                try {
                    const ctrl2 = new AbortController();
                    const tId2 = setTimeout(() => ctrl2.abort(), 2000);
                    res = await fetch('http://localhost:5000/health', { signal: ctrl2.signal, cache: 'no-store' });
                    clearTimeout(tId2);
                } catch (e2) {
                    res = null;
                }
            }
            clearTimeout(timeoutId);

            if (res && res.ok) {
                const info = await res.json();
                if (info && info.esbmc_version) {
                    window.esbmcServerVersion = info.esbmc_version;
                }
                if (serverStatusBadge && serverStatusDot && serverStatusText) {
                    serverStatusBadge.style.background = '#ecfdf5';
                    serverStatusBadge.style.color = '#065f46';
                    serverStatusBadge.style.borderColor = '#10b981';
                    serverStatusDot.style.background = '#10b981';
                    serverStatusText.textContent = `🟢 ESBMC Server Online (${info.engine ? 'Active' : 'Ready'})`;
                }
                return;
            }
            if (res && res.status === 503 && serverStatusBadge && serverStatusDot && serverStatusText) {
                serverStatusBadge.style.background = '#fef2f2';
                serverStatusBadge.style.color = '#991b1b';
                serverStatusBadge.style.borderColor = '#ef4444';
                serverStatusDot.style.background = '#ef4444';
                serverStatusText.textContent = '🔴 Server online, but ESBMC is unavailable';
                setTimeout(checkServerHealth, 5000);
                return;
            }
        } catch (err) {
            // Silent: keep an indicative state without blocking the user
        }
        if (serverStatusBadge && serverStatusDot && serverStatusText) {
            serverStatusBadge.style.background = '#fef3c7';
            serverStatusBadge.style.color = '#92400e';
            serverStatusBadge.style.borderColor = '#f59e0b';
            serverStatusDot.style.background = '#f59e0b';
            serverStatusText.textContent = `⏳ Connecting to Server...`;
        }
        setTimeout(checkServerHealth, 2000);
    }
    checkServerHealth();

    // =========================================================================
    // 📊 2. REAL-TIME PROGRESS PANEL (1/12, 2/12...) + LIVE TABLE
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
                <span>Starting formal verification...</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <span id="live-progress-counter-badge" style="background: #4f46e5; color: #fff; padding: 4px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 800;">
                    Test 1/1 (0%)
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
                        <th style="padding: 6px 8px; text-align: left;">Test #</th>
                        <th style="padding: 6px 8px; text-align: left;">Lang</th>
                        <th style="padding: 6px 8px; text-align: left;">Phase</th>
                        <th style="padding: 6px 8px; text-align: left;">Module / File</th>
                        <th style="padding: 6px 8px; text-align: left;">Mode / Z3 Counterexample</th>
                        <th style="padding: 6px 8px; text-align: left;">VCCs / SSA</th>
                        <th style="padding: 6px 8px; text-align: left;">Time</th>
                        <th style="padding: 6px 8px; text-align: left;">Verdict</th>
                        <th style="padding: 6px 8px; text-align: left;">Status / Oracle</th>
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
    // 🎯 3. SCIENTIFIC VERIFICATION PROFILES (1-CLICK PRESETS)
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
        if (counterBadge) counterBadge.textContent = isRepoMode ? 'Cloning & Scanning Git...' : 'Test 1/1 (Running)';
        if (scoreboard) scoreboard.textContent = '✅ SAFE: 0 | ❌ VIOLATION: 0 | 📐 VCCs: 0 | 🔗 SSA: 0';
        if (barFill) barFill.style.width = '6%';
        if (previewWrapper) previewWrapper.style.display = 'none';
        if (previewTbody) previewTbody.innerHTML = '';
    }

    // --- Options Tab Logic ---
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

        const contractsFieldset = document.getElementById('fieldset-contracts');
        const contractsHint = document.getElementById('contracts-info-hint');
        const enforceInput = document.querySelector('.esbmc-param[data-flag="--enforce-contract"]');
        const replaceInput = document.querySelector('.esbmc-param[data-flag="--replace-call-with-contract"]');

        if (selectedLanguage === 'python') {
            pythonOptions.style.display = 'block';
            editor.setOption('mode', 'python');
            if (contractsFieldset) contractsFieldset.style.display = 'none';
            if (enforceInput) { enforceInput.disabled = true; enforceInput.value = ''; }
            if (replaceInput) { replaceInput.disabled = true; replaceInput.value = ''; }
            if (contractsHint) {
                contractsHint.innerHTML = 'Function contracts (--enforce-contract) are supported for C/C++. For Python, use <code>--function &lt;name&gt;</code>.';
            }
        } else if (selectedLanguage === 'all') {
            pythonOptions.style.display = 'block';
            if (contractsFieldset) contractsFieldset.style.display = 'block';
            if (enforceInput) enforceInput.disabled = false;
            if (replaceInput) replaceInput.disabled = false;
            if (contractsHint) {
                contractsHint.innerHTML = 'Native for C/C++ (<code>__ESBMC_requires</code>, <code>__ESBMC_ensures</code>, <code>__ESBMC_assigns</code>).';
            }
        } else {
            pythonOptions.style.display = 'none';
            editor.setOption('mode', selectedLanguage === 'c' ? 'text/x-csrc' : 'text/x-c++src');
            if (contractsFieldset) contractsFieldset.style.display = 'block';
            if (enforceInput) { enforceInput.disabled = false; enforceInput.placeholder = 'function_name'; }
            if (replaceInput) { replaceInput.disabled = false; replaceInput.placeholder = 'callee_name'; }
            if (contractsHint) {
                contractsHint.innerHTML = 'Native for C/C++ (<code>__ESBMC_requires</code>, <code>__ESBMC_ensures</code>, <code>__ESBMC_assigns</code>).';
            }
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

    // --- PROGRESS: Load a file from Git (WITH %) ---
    async function fetchAndLoadFile(filePath) {
        const url = gitRepoUrl.value.trim();
        if (!url) return;

        gitFetchStatus.textContent = 'Loading file content...';
        gitFetchStatus.className = '';
        
        // Start the overlay pinned at 0%
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
            
            // Ask the server for the download state every half second
            const poll = setInterval(async () => {
                try {
                    const res = await fetch(`http://127.0.0.1:5000/fetch-repo-status/${taskId}`);
                    const statusData = await res.json();

                    if (statusData.status === 'running') {
                        // Update the on-screen loading bar
                        showLoadingOverlay(`Downloading file: ${filePath}... ${statusData.progress}%`, statusData.progress);
                    } else if (statusData.status === 'completed') {
                        clearInterval(poll);
                        hideLoadingOverlay();
                        
                        // File downloaded successfully; load it into the editor
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
                gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">⚡ File URL detected! Base repository: <code>${escapeHtml(baseUrl)}</code> | File: <code>${escapeHtml(subpath)}</code></span>`;
            } else {
                if (repoSubdirFilter) {
                    repoSubdirFilter.value = subpath;
                }
                gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">⚡ Subfolder detected! Base repository: <code>${escapeHtml(baseUrl)}</code> | Subdirectory filter: <code>${escapeHtml(subpath)}</code></span>`;
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
            gitFileSelect.innerHTML = '<option value="">📂 Select a file from the folder...</option>';
        }

        if (!listaArquivos || listaArquivos.length === 0) {
            if (gitFileSelect) gitFileSelect.style.display = 'none';
            if (gitFolderScopeBadge) gitFolderScopeBadge.style.display = 'none';
            gitFetchStatus.textContent = subpasta 
                ? `No verifiable file (.c, .cpp, .py) found in folder "${subpasta}".`
                : 'No verifiable file (.c, .cpp, .py) found in this repository.';
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
                gitFolderScopeBadge.textContent = `📂 Folder: ${subpasta} (${listaArquivos.length} files)`;
                gitFolderScopeBadge.style.background = '#dbeafe';
                gitFolderScopeBadge.style.color = '#1e40af';
            } else {
                gitFolderScopeBadge.textContent = `🌐 Whole repository (${listaArquivos.length} files)`;
                gitFolderScopeBadge.style.background = '#e5e7eb';
                gitFolderScopeBadge.style.color = '#4b5563';
            }
        }

        if (subpasta) {
            gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">✅ Folder opened: <code>${escapeHtml(subpasta)}</code> — ${listaArquivos.length} file(s) ready for an individual test or exploration.</span>`;
            if (gitMainFile && !gitMainFile.value) {
                gitMainFile.placeholder = `Choose a file from ${subpasta}...`;
            }
        } else {
            gitFetchStatus.innerHTML = `<span style="color:#059669; font-weight:600;">✅ Found ${listaArquivos.length} files in the repository.</span>`;
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

    // --- PROGRESS: Clone a Git repository (WITH %) ---
    fetchRepoBtn.addEventListener('click', async () => {
        normalizarGithubUrlFrontend();
        const url = gitRepoUrl.value.trim();
        if (!url) { alert('Please enter a Git URL first.'); return; }

        const subdirFilterVal = repoSubdirFilterInput ? repoSubdirFilterInput.value.trim() : '';

        gitFileListDatalist.innerHTML = '';
        if (gitFileSelect) {
            gitFileSelect.innerHTML = '<option value="">📂 Loading files...</option>';
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
            
            // Polling: ask the server every 0.5 seconds what percentage has been cloned
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
            gitFileSelect.innerHTML = '<option value="">📂 Files in folder...</option>';
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
            gitFileSelect.innerHTML = '<option value="">📂 Files in folder...</option>';
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

    function hideAllTabPanels() {
        dashboard.style.display = 'none';
        resultadoTextoContainer.style.display = 'none';
        htmlReportContainer.style.display = 'none';
        yamlReportContainer.style.display = 'none';
        graphmlReportContainer.style.display = 'none';
        if (bugReportContainer) bugReportContainer.style.display = 'none';
        if (metricsHistoryContainer) metricsHistoryContainer.style.display = 'none';

        tabDashboard.classList.remove('active');
        tabRawText.classList.remove('active');
        if (tabBugReport) tabBugReport.classList.remove('active');
        tabHtmlReport.classList.remove('active');
        tabYamlReport.classList.remove('active');
        tabGraphmlReport.classList.remove('active');
        if (tabMetricsHistory) tabMetricsHistory.classList.remove('active');
    }

    tabDashboard.addEventListener('click', () => {
        hideAllTabPanels();
        dashboard.style.display = 'block';
        tabDashboard.classList.add('active');
    });

    tabRawText.addEventListener('click', () => {
        hideAllTabPanels();
        resultadoTextoContainer.style.display = 'block';
        tabRawText.classList.add('active');
    });

    tabHtmlReport.addEventListener('click', () => {
        hideAllTabPanels();
        htmlReportContainer.style.display = 'block';
        tabHtmlReport.classList.add('active');
    });

    tabYamlReport.addEventListener('click', () => {
        hideAllTabPanels();
        yamlReportContainer.style.display = 'block';
        tabYamlReport.classList.add('active');
    });

    tabGraphmlReport.addEventListener('click', () => {
        hideAllTabPanels();
        graphmlReportContainer.style.display = 'block';
        tabGraphmlReport.classList.add('active');
    });

    if (tabBugReport) {
        tabBugReport.addEventListener('click', () => {
            hideAllTabPanels();
            if (bugReportContainer) bugReportContainer.style.display = 'block';
            tabBugReport.classList.add('active');
        });
    }

    if (tabMetricsHistory) {
        tabMetricsHistory.addEventListener('click', () => {
            hideAllTabPanels();
            if (metricsHistoryContainer) metricsHistoryContainer.style.display = 'block';
            tabMetricsHistory.classList.add('active');
            renderCodacyMetricsView();
        });
    }

    if (btnOpenMetricsHeader) {
        btnOpenMetricsHeader.addEventListener('click', () => {
            if (tabsContainer) tabsContainer.style.display = 'flex';
            if (tabMetricsHistory) {
                tabMetricsHistory.click();
            }
        });
    }

    let currentTaskId = null;
    let pollInterval = null;
    const cancelarBtn = document.getElementById('cancelarBtn');

    // --- PROGRESS: ESBMC Analyser ---
    analisarBtn.addEventListener('click', async () => {
        const codigo = editor.getValue();
        const gitUrlValue = gitRepoUrl.value.trim();
        const gitMainFileValue = gitMainFile.value.trim();
        const linguagemSelecionada = document.querySelector('input[name="language"]:checked').value;
        const pythonInterpreter = document.getElementById('python-interpreter').value;

        const flags = [];
        document.querySelectorAll('.esbmc-flag:checked').forEach(cb => flags.push(cb.value));
        document.querySelectorAll('.esbmc-param').forEach(input => {
            if (input.disabled) return;
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
        if (metricsHistoryContainer) metricsHistoryContainer.style.display = 'none';
        
        // ... (inside analisarBtn.addEventListener, around line 250) ...
        
        // ...
        tabsContainer.style.display = 'flex';
        tabRawText.click(); 
        
        const verificationModeSelect = document.getElementById('verificationModeSelect');
        const selectedEngineMode = verificationModeSelect ? verificationModeSelect.value : 'assisted';

        latestExecutionFlags = [...flags];
        latestSelectedLanguage = linguagemSelecionada;
        latestSelectedEngineMode = selectedEngineMode;
        latestMainFileAnalyzed = gitMainFileValue || (linguagemSelecionada === 'python' ? 'main.py' : (linguagemSelecionada === 'c' ? 'main.c' : 'main.cpp'));

        if (tabBugReport) tabBugReport.style.display = 'none';
        if (bugReportActionBar) bugReportActionBar.style.display = 'none';
        if (bugReportContainer) bugReportContainer.style.display = 'none';

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

        // ENABLE THE REAL-TIME PROGRESS PANEL
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
                if (input.disabled) return;
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
                'Cloning the Git repository and starting the RepoSlice-BMC stratified scan...',
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

                latestExecutionFlags = [...flags];
                latestSelectedLanguage = selectedRepoLang === 'auto' ? 'all' : selectedRepoLang;
                latestSelectedEngineMode = selectedEngineMode;
                latestMainFileAnalyzed = 'Git Repository Exploration';

                if (tabBugReport) tabBugReport.style.display = 'none';
                if (bugReportActionBar) bugReportActionBar.style.display = 'none';
                if (bugReportContainer) bugReportContainer.style.display = 'none';

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
                    counterBadge.textContent = `Test ${cur}/${tot} (${pct}%)`;
                }
                if (statusText) {
                    const langTag = prog.current_lang ? `[${prog.current_lang}] ` : '';
                    const fileTag = prog.current_file || 'Waiting...';
                    statusText.innerHTML = `<span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid var(--primary); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span> <span>Verifying <strong>${escapeHtml(cur)}/${escapeHtml(tot)}</strong>: <code>${escapeHtml(langTag)}${escapeHtml(fileTag)}</code></span>`;
                }
                if (scoreboard) {
                    const passBug = prog.pass_bug_count || 0;
                    const passSafe = prog.pass_safe_count || 0;
                    const regrCount = prog.regression_count || 0;
                    if (prog.test_suite_mode || passBug > 0 || regrCount > 0) {
                        scoreboard.innerHTML = `🟢 PASS (Bugs): <strong>${passBug}</strong> | 🛡️ PASS (Safe): <strong>${passSafe}</strong> | 🔴 REGRESSIONS: <strong style="color:#dc2626;">${regrCount}</strong> | 📐 VCCs: <strong>${escapeHtml(prog.total_vccs || 0)}</strong>`;
                    } else {
                        scoreboard.innerHTML = `✅ SAFE: <strong>${escapeHtml(prog.safe_count || 0)}</strong> | ❌ VIOLATION: <strong style="color:#dc2626;">${escapeHtml(prog.violation_count || 0)}</strong> | 📐 VCCs: <strong>${escapeHtml(prog.total_vccs || 0)}</strong> | 🔗 SSA: <strong>${escapeHtml(prog.total_ssa || 0)}</strong>`;
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
                            ? `<span style="color:#dc2626; font-weight:600;">❌ ${escapeHtml(item.z3_witness)}</span>`
                            : `<span style="color:#4f46e5; font-weight:600;">${escapeHtml(item.mode || 'Symbolic BMC')}</span>`;

                        const phaseBadge = item.phase
                            ? `<span style="background:#fef3c7; color:#92400e; padding:1px 5px; border-radius:3px; font-size:10px; font-weight:600; white-space:nowrap;">${escapeHtml(item.phase.split(':')[0])}</span>`
                            : `<span style="color:#94a3b8;">-</span>`;

                        let testStatusHtml = '<span style="color:#94a3b8;">-</span>';
                        if (item.test_status) {
                            let tsColor = '#059669';
                            if (item.test_status_code === 'REGRESSION_FAILED') tsColor = '#dc2626';
                            else if (item.test_status.includes('PASS')) tsColor = '#059669';
                            testStatusHtml = `<span style="background:${tsColor}; color:#fff; padding:1px 6px; border-radius:3px; font-size:10.5px; font-weight:700; white-space:nowrap;">${escapeHtml(item.test_status)}</span>`;
                        }

                        tr.innerHTML = `
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><strong>${escapeHtml(item.index)}/${tot}</strong></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><span style="background:#e0e7ff; color:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700; font-size:10.5px;">${escapeHtml(item.lang || 'C/C++')}</span></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${phaseBadge}</td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><code>${escapeHtml(item.directory)}/${escapeHtml(item.file)}</code></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${witnessOrMode}</td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><strong>${escapeHtml(item.vccs || 0)}</strong> <small style="color:#64748b;">(${escapeHtml(item.ssa_assigns || 0)} SSA)</small></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><code>${escapeHtml(item.wall_time || '-')}</code></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;"><span style="background:${badgeColor}; color:#fff; padding:2px 7px; border-radius:4px; font-size:10.5px; font-weight:700;">${escapeHtml(item.status)}</span></td>
                            <td style="padding: 5px 8px; border-bottom: 1px solid #f1f5f9;">${testStatusHtml}</td>
                        `;
                    });
                    previewWrapper.scrollTop = previewWrapper.scrollHeight;
                }
            }

            if (data.status === 'consolidating') {
                const statusText = document.getElementById('live-progress-status-text');
                if (statusText) {
                    statusText.innerHTML = `<span style="display:inline-block; width: 14px; height: 14px; border: 2.5px solid #059669; border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></span> <span style="color:#059669;">⏳ Consolidating the Dashboard, LaTeX table and CSV for the modules verified so far...</span>`;
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
                        verificacao_sucesso: false,
                        verdict: (data.progresso.violation_count || 0) > 0 ? 'FAILED' : 'ERROR',
                        dashboard_data: [],
                        repo_exploration_summary: data.progresso.partial_summary,
                        codigo_analisado: data.logs || '// Consolidated Partial Repository Run'
                    });
                }
            }
        } catch (error) {
            console.error("Error checking status:", error);
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
                resultado.repo_exploration_summary || null,
                resultado.verdict || (resultado.verificacao_sucesso ? 'SUCCESSFUL' : 'UNKNOWN')
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
        analysisProgressContainer.style.display = 'none'; // DISABLE THE INLINE BAR
        validateInputs(); 
    }     

    // =========================================================================
    // 🐞 EXECUTION TRACE & BUG REPORT GENERATOR (ESBMC GITHUB)
    // =========================================================================
    function buildESBMCBugReportMarkdown(resultsArray, codigoFonte, repoExplorationSummary = null, violationDetails = []) {
        const esbmcVer = window.esbmcServerVersion || 'unknown (the server did not report an ESBMC version)';
        const lang = (latestSelectedLanguage || 'cpp').toLowerCase();
        const codeLang = lang === 'python' ? 'python' : (lang === 'c' ? 'c' : 'cpp');

        let failingModule = null;
        if (repoExplorationSummary && Array.isArray(repoExplorationSummary)) {
            failingModule = repoExplorationSummary.find(item => {
                const s = String(item.status || '');
                return s.startsWith('VIOLATION') || s.startsWith('RAW ERROR') || (item.test_status_code === 'REGRESSION_FAILED');
            });
        }

        const firstResultWithViolation = Array.isArray(resultsArray)
            ? resultsArray.find(res => res.status === 'violation')
            : null;

        // Determine the main file and minimal code
        let targetFile = latestMainFileAnalyzed || (lang === 'python' ? 'main.py' : (lang === 'c' ? 'main.c' : 'main.cpp'));
        let codeSnippet = codigoFonte || '';
        let cmdLine = '';

        if (failingModule) {
            targetFile = failingModule.file || targetFile;
            if (failingModule.homogenized_code) {
                codeSnippet = failingModule.homogenized_code;
            }
            if (failingModule.esbmc_cli) {
                cmdLine = failingModule.esbmc_cli;
            }
        }

        if (!cmdLine) {
            const flagStr = (latestExecutionFlags || []).join(' ');
            cmdLine = `esbmc ${targetFile} ${flagStr}`.trim();
        }

        // Title and violated property
        let primaryViolation = null;
        if (violationDetails && violationDetails.length > 0) {
            primaryViolation = violationDetails[0];
        }

        let title = '';
        if (primaryViolation) {
            const cwePrefix = primaryViolation.cwe && primaryViolation.cwe !== 'N/A' ? `[${primaryViolation.cwe}] ` : '';
            const funcPart = primaryViolation.function && primaryViolation.function !== 'N/A' ? ` in ${primaryViolation.function}()` : '';
            title = `[ESBMC Reproducer] ${cwePrefix}${primaryViolation.message}${funcPart} [${primaryViolation.file || targetFile}]`;
        } else if (failingModule) {
            title = `[ESBMC Reproducer] Verification Failure in ${failingModule.file} (${failingModule.status})`;
        } else {
            title = `[ESBMC Reproducer] Property Violation Detected by ESBMC [${targetFile}]`;
        }

        // Counterexample Initial States
        let initialValuesStr = '';
        if (firstResultWithViolation && firstResultWithViolation.initial_values) {
            for (const key in firstResultWithViolation.initial_values) {
                const valueObj = firstResultWithViolation.initial_values[key];
                const val = valueObj?.value?.value !== undefined ? valueObj.value.value : (valueObj?.value !== undefined ? valueObj.value : 'N/A');
                initialValuesStr += `${key} = ${val}\n`;
            }
        }

        // Step by step trace
        let traceStr = '';
        if (firstResultWithViolation && firstResultWithViolation.steps) {
            firstResultWithViolation.steps.forEach((step, index) => {
                const stepDetails = step.message || step.full_expr || (step.assignment ? `${step.assignment.lhs} = ${step.assignment.rhs?.value || '...'}` : '');
                const location = step.file ? `${step.file}:${step.line}` : (step.location?.file ? `${step.location.file}:${step.location.line}` : 'N/A');
                traceStr += `[Step ${index}] ${step.type} @ ${location} -> ${stepDetails}\n`;
            });
        }

        // Build the Markdown in the exact format of esbmc/esbmc issues
        const md = [];
        md.push(`### What went wrong`);
        md.push(`False alarm or verification failure (VERIFICATION FAILED: Property violation / counterexample found).`);
        md.push(``);
        md.push(`### ESBMC version`);
        md.push(`\`\`\``);
        md.push(esbmcVer);
        md.push(`\`\`\``);
        md.push(``);
        md.push(`### Program`);
        md.push(`Reduce it first: the smallest program that still shows the problem.`);
        md.push(`\`\`\`${codeLang}`);
        md.push(codeSnippet.trim() || '// No source code provided');
        md.push(`\`\`\``);
        md.push(``);
        md.push(`### Command`);
        md.push(`\`\`\`bash`);
        md.push(cmdLine);
        md.push(`\`\`\``);
        md.push(``);
        md.push(`### Execution Flow & Counterexample`);
        if (violationDetails && violationDetails.length > 0) {
            md.push(`#### Violated Properties:`);
            violationDetails.forEach(v => {
                const cweText = v.cwe && v.cwe !== 'N/A' ? ` (${v.cwe} - ${v.severity})` : '';
                md.push(`- **Location:** \`${v.file}:${v.line}\` in \`${v.function}()\``);
                md.push(`  - **Violation:** ${v.message}${cweText}`);
            });
            md.push(``);
        }
        if (initialValuesStr.trim()) {
            md.push(`#### Initial Symbolic State (Counterexample Inputs):`);
            md.push(`\`\`\``);
            md.push(initialValuesStr.trim());
            md.push(`\`\`\``);
            md.push(``);
        }
        if (traceStr.trim()) {
            md.push(`#### Step-by-Step Execution Trace:`);
            md.push(`\`\`\``);
            md.push(traceStr.trim());
            md.push(`\`\`\``);
            md.push(``);
        }
        if (failingModule && failingModule.z3_witness) {
            md.push(`#### SMT Solver Witness:`);
            md.push(`\`\`\``);
            md.push(failingModule.z3_witness);
            md.push(`\`\`\``);
            md.push(``);
        }

        return {
            title,
            markdown: md.join('\n'),
            esbmcVer,
            targetFile,
            codeSnippet,
            cmdLine,
            violationDetails,
            initialValuesStr,
            traceStr,
            failingModule,
            codeLang
        };
    }

    function copyBugReportMarkdown(buttonElement) {
        if (!latestBugReportMarkdown) {
            alert('No bug report is available yet.');
            return;
        }
        navigator.clipboard.writeText(latestBugReportMarkdown).then(() => {
            if (buttonElement) {
                const originalText = buttonElement.innerHTML;
                buttonElement.innerHTML = '✅ Copied!';
                setTimeout(() => { buttonElement.innerHTML = originalText; }, 2500);
            }
        }).catch(() => {
            alert('Could not copy to the clipboard automatically.');
        });
    }

    function downloadBugReportMd() {
        if (!latestBugReportMarkdown) {
            alert('No bug report is available to download.');
            return;
        }
        const blob = new Blob([latestBugReportMarkdown], { type: 'text/markdown;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        a.download = `esbmc_reproducer_${timestamp}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // 📄 FORMAL PDF REPORT GENERATOR (ESBMC GITHUB FORMAT / WRONG RESULT)
    // =========================================================================
    function generateBugReportPdf() {
        if (!latestBugReportData || !latestBugReportMarkdown) {
            alert('No bug report is available to generate a PDF.');
            return;
        }

        const data = latestBugReportData;
        const now = new Date();
        const dataFormatada = now.toLocaleDateString('en-GB') + ' ' + now.toLocaleTimeString('en-GB');


        // Extract the line numbers with violations
        const violationLines = (data.violationDetails || []).map(v => parseInt(v.line, 10)).filter(n => !isNaN(n));
        const codeLines = (data.codeSnippet || '').split('\n');
        let codeHtml = '<table class="code-table" style="width:100%; border-collapse:collapse; font-family:\'Fira Code\', Consolas, monospace; font-size:10.5px;">';
        codeLines.forEach((line, idx) => {
            const lineNum = idx + 1;
            const isViolated = violationLines.includes(lineNum);
            const lineBg = isViolated ? '#fee2e2' : (idx % 2 === 0 ? '#ffffff' : '#f8fafc');
            const numColor = isViolated ? '#dc2626' : '#94a3b8';
            const marker = isViolated ? ' ❌' : '';
            codeHtml += `
                <tr style="background-color: ${lineBg}; line-height: 1.45;">
                    <td style="width: 45px; text-align: right; padding: 2px 8px 2px 0; color: ${numColor}; border-right: 2px solid ${isViolated ? '#ef4444' : '#e2e8f0'}; user-select: none; font-weight: ${isViolated ? 'bold' : 'normal'};">${lineNum}${marker}</td>
                    <td style="padding: 2px 10px; white-space: pre-wrap; word-break: break-all; color: ${isViolated ? '#991b1b' : '#1e293b'}; font-weight: ${isViolated ? '600' : 'normal'};">${escapeHtml(line)}</td>
                </tr>
            `;
        });
        codeHtml += '</table>';

        let violationsTableHtml = '';
        if (data.violationDetails && data.violationDetails.length > 0) {
            violationsTableHtml = `
                <table class="report-table" style="width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 11px;">
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #334155; text-align: left; border-bottom: 2px solid #cbd5e1;">
                            <th style="padding: 6px 8px;">File</th>
                            <th style="padding: 6px 8px;">Function</th>
                            <th style="padding: 6px 8px;">Line</th>
                            <th style="padding: 6px 8px;">Violated Property</th>
                            <th style="padding: 6px 8px;">CWE (MITRE)</th>
                            <th style="padding: 6px 8px;">Severity</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            data.violationDetails.forEach((v, i) => {
                const bg = i % 2 === 0 ? '#ffffff' : '#f8fafc';
                let sevBg = '#fee2e2';
                let sevCol = '#991b1b';
                if (v.severity === 'Critical') { sevBg = '#fecaca'; sevCol = '#7f1d1d'; }
                else if (v.severity === 'Medium') { sevBg = '#ffedd5'; sevCol = '#9a3412'; }
                else if (v.severity === 'Low') { sevBg = '#fef9c3'; sevCol = '#854d0e'; }
                violationsTableHtml += `
                    <tr style="background: ${bg}; border-bottom: 1px solid #e2e8f0;">
                        <td style="padding: 6px 8px; font-family: monospace;">${escapeHtml(v.file)}</td>
                        <td style="padding: 6px 8px; font-family: monospace; font-weight: 600;">${escapeHtml(v.function)}()</td>
                        <td style="padding: 6px 8px; text-align: center; font-weight: bold; color: #dc2626;">${escapeHtml(v.line)}</td>
                        <td style="padding: 6px 8px; color: #b91c1c; font-weight: 600;">${escapeHtml(v.message)}</td>
                        <td style="padding: 6px 8px; font-family: monospace;">${escapeHtml(v.cwe)}</td>
                        <td style="padding: 6px 8px;"><span style="background: ${sevBg}; color: ${sevCol}; padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 10px;">${escapeHtml(v.severity)}</span></td>
                    </tr>
                `;
            });
            violationsTableHtml += '</tbody></table>';
        }

        const p = [];
        p.push('<!DOCTYPE html>');
        p.push('<html lang="en">');
        p.push('<head>');
        p.push('    <meta charset="UTF-8">');
        p.push('    <title>' + escapeHtml(data.title) + '</title>');
        p.push('    <style>');
        p.push('        @page { size: A4 portrait; margin: 12mm 12mm 12mm 12mm; }');
        p.push('        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; color: #0f172a; background: #ffffff; margin: 0; padding: 0; font-size: 11px; line-height: 1.45; }');
        p.push('        .header { border-bottom: 2.5px solid #0f172a; padding-bottom: 10px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: flex-start; }');
        p.push('        .header-title { font-size: 17px; font-weight: 800; color: #0f172a; letter-spacing: -0.3px; margin: 0; }');
        p.push('        .header-subtitle { font-size: 11px; color: #475569; margin-top: 3px; font-weight: 500; }');
        p.push('        .header-badge { background: #fff1f2; color: #be123c; border: 1.5px solid #fda4af; padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 11px; text-align: right; }');
        p.push('        .meta-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 9px 12px; margin-bottom: 14px; font-size: 10.5px; }');
        p.push('        .meta-item strong { display: block; color: #64748b; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }');
        p.push('        .meta-item span { color: #1e293b; font-weight: 600; }');
        p.push('        .section { margin-bottom: 14px; page-break-inside: avoid; }');
        p.push('        .section-title { font-size: 12px; font-weight: 800; color: #0f172a; border-bottom: 1.5px solid #e2e8f0; padding-bottom: 3px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }');
        p.push('        .section-desc { font-size: 10px; color: #64748b; margin-bottom: 5px; font-style: italic; }');
        p.push('        .code-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; margin-top: 4px; }');
        p.push('        .cmd-box { background: #0f172a; color: #f8fafc; padding: 8px 12px; border-radius: 6px; font-family: "Fira Code", Consolas, monospace; font-size: 10.5px; word-break: break-all; white-space: pre-wrap; }');
        p.push('        .trace-box { background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 6px; font-family: "Fira Code", Consolas, monospace; font-size: 10px; line-height: 1.4; white-space: pre-wrap; word-break: break-all; }');
        p.push('        .initial-values-box { background: #eff6ff; border-left: 4px solid #2563eb; padding: 7px 10px; border-radius: 4px; font-family: "Fira Code", Consolas, monospace; font-size: 10.5px; color: #1e293b; white-space: pre-wrap; }');
        p.push('        .footer { margin-top: 20px; border-top: 1px solid #e2e8f0; padding-top: 8px; display: flex; justify-content: space-between; color: #94a3b8; font-size: 9px; }');
        p.push('        @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } .section { page-break-inside: avoid; } }');
        p.push('    </style>');
        p.push('</head>');
        p.push('<body>');
        p.push('    <div class="header">');
        p.push('        <div>');
        p.push('            <h1 class="header-title">🐞 ESBMC Reproducer & Execution Flow Report</h1>');
        p.push('            <div class="header-subtitle">Formal bug reproduction report following the official <strong>esbmc/esbmc</strong> template (Wrong result or crash)</div>');
        p.push('        </div>');
        p.push('        <div class="header-badge">');
        p.push('            ❌ VERIFICATION FAILED<br>');
        p.push('            <span style="font-size: 9px; font-weight: normal; color: #9f1239;">Counterexample Discovered</span>');
        p.push('        </div>');
        p.push('    </div>');
        p.push('    <div class="meta-grid">');
        p.push('        <div class="meta-item"><strong>Issue Title</strong><span>' + escapeHtml(data.title) + '</span></div>');
        p.push('        <div class="meta-item"><strong>Analysed Module</strong><span>' + escapeHtml(data.targetFile) + '</span></div>');
        p.push('        <div class="meta-item"><strong>Extraction Date / Time</strong><span>' + dataFormatada + '</span></div>');
        p.push('        <div class="meta-item"><strong>ESBMC & Solver Version</strong><span>' + escapeHtml(data.esbmcVer) + '</span></div>');
        p.push('        <div class="meta-item"><strong>Language / Mode</strong><span>' + escapeHtml((data.codeLang || 'c').toUpperCase()) + ' (' + escapeHtml(latestSelectedEngineMode || 'assisted') + ')</span></div>');
        p.push('        <div class="meta-item"><strong>Project / Context</strong><span>UFAM MSc • Formal Software Verification</span></div>');
        p.push('    </div>');
        p.push('    <div class="section">');
        p.push('        <div class="section-title">1. What went wrong</div>');
        p.push('        <div style="background: #fff1f2; border: 1px solid #fecdd3; border-radius: 6px; padding: 8px 12px; color: #9f1239; font-size: 11px;">');
        p.push('            <strong>False alarm or verification failure:</strong> The ESBMC bounded model found a formal property violation or a failed assertion during symbolic checking with the SMT solver.');
        p.push('        </div>');
        p.push('    </div>');
        p.push('    <div class="section">');
        p.push('        <div class="section-title">2. ESBMC version</div>');
        p.push('        <div class="section-desc">Output of <code>esbmc --version</code>, or the commit you built:</div>');
        p.push('        <div class="cmd-box" style="background:#1e293b;">' + escapeHtml(data.esbmcVer) + '</div>');
        p.push('    </div>');
        p.push('    <div class="section">');
        p.push('        <div class="section-title">3. Program</div>');
        p.push('        <div class="section-desc">Reduce it first: the smallest program that still shows the problem (the violating line is highlighted):</div>');
        p.push('        <div class="code-box">' + codeHtml + '</div>');
        p.push('    </div>');
        p.push('    <div class="section">');
        p.push('        <div class="section-title">4. Command</div>');
        p.push('        <div class="section-desc">Exact command line to reproduce the counterexample deterministically:</div>');
        p.push('        <div class="cmd-box">' + escapeHtml(data.cmdLine) + '</div>');
        p.push('    </div>');
        p.push('    <div class="section">');
        p.push('        <div class="section-title">5. Execution Flow & Counterexample</div>');
        if (violationsTableHtml) {
            p.push('        <div style="font-weight: 700; color: #334155; margin-top: 4px; margin-bottom: 4px;">Properties Violated in the Code:</div>');
            p.push('        ' + violationsTableHtml);
        }
        if (data.initialValuesStr && data.initialValuesStr.trim()) {
            p.push('        <div style="font-weight: 700; color: #334155; margin-top: 10px; margin-bottom: 4px;">Initial Symbolic State (Counterexample Input Values):</div>');
            p.push('        <div class="initial-values-box">' + escapeHtml(data.initialValuesStr.trim()) + '</div>');
        }
        if (data.traceStr && data.traceStr.trim()) {
            p.push('        <div style="font-weight: 700; color: #334155; margin-top: 10px; margin-bottom: 4px;">Step-by-Step Execution Trace:</div>');
            p.push('        <div class="trace-box">' + escapeHtml(data.traceStr.trim()) + '</div>');
        }
        p.push('    </div>');
        p.push('    <div class="footer">');
        p.push('        <div>ESBMC-Web • Integrated Bounded Model Checking Formal Verification Platform</div>');
        p.push('        <div>Federal University of Amazonas (UFAM) • IComp • MSc in Informatics</div>');
        p.push('    </div>');
        p.push('</body>');
        p.push('</html>');
        const printHtml = p.join('\n');

        const iframe = document.createElement('iframe');
        iframe.style.position = 'fixed';
        iframe.style.right = '0';
        iframe.style.bottom = '0';
        iframe.style.width = '0';
        iframe.style.height = '0';
        iframe.style.border = '0';
        document.body.appendChild(iframe);

        const doc = iframe.contentWindow.document;
        doc.open();
        doc.write(printHtml);
        doc.close();

        iframe.contentWindow.focus();
        setTimeout(() => {
            iframe.contentWindow.print();
            setTimeout(() => {
                document.body.removeChild(iframe);
            }, 3000);
        }, 500);
    }

    function openGithubIssue() {
        if (!latestBugReportMarkdown) {
            window.open('https://github.com/esbmc/esbmc/issues/new/choose', '_blank');
            return;
        }

        // Always copy the complete Markdown to the user's clipboard
        navigator.clipboard.writeText(latestBugReportMarkdown).catch(() => {});

        const title = latestBugReportTitle || '[ESBMC Reproducer] Verification Failure';
        let body = latestBugReportMarkdown;

        if (body.length > 2000) {
            const shortMd = [
                '### What went wrong',
                'False alarm or verification failure (VERIFICATION FAILED: Property violation / counterexample found).',
                '',
                '### ESBMC version',
                '```',
                window.esbmcServerVersion || 'unknown (the server did not report an ESBMC version)',
                '```',
                '',
                '### Command',
                '```bash',
                `esbmc ${latestMainFileAnalyzed || 'main.c'} ${(latestExecutionFlags || []).join(' ')}`.trim(),
                '```',
                '',
                '> 📋 **Notice:** The full execution flow, minimal reproducer program, initial symbolic states, and step-by-step trace were automatically copied to your clipboard. Paste (Ctrl+V) here!'
            ].join('\n');
            body = shortMd;
        }

        const issueUrl = `https://github.com/esbmc/esbmc/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
        window.open(issueUrl, '_blank');
    }

    const INCONCLUSIVE_BANNERS = {
        CANCELLED: '⏹ ANALYSIS CANCELLED — NO VERDICT',
        TIMEOUT: '⏱ TIMED OUT — NO VERDICT',
        ERROR: '⚠ ESBMC ERROR — NO VERDICT (see Terminal Output)',
        UNKNOWN: '⚠ INCONCLUSIVE — ESBMC REPORTED NO VERDICT',
        BOUND_REACHED: '⚠ LOOP BOUND REACHED — NO VERDICT (increase --unwind or use --k-induction)',
        UNSUPPORTED: '⚠ ESBMC DOES NOT MODEL A LIBRARY CALL THAT WAS REACHED — NO VERDICT',
        PARTIAL: '⚠ PARTIAL — NO BUG FOUND, BUT SOME FUNCTIONS WERE NOT EXERCISED (see Terminal Output)',
    };

    function renderDashboard(resultsArray, codigoFonte, repoExplorationSummary = null, verdict = 'UNKNOWN', skipHistoryRecord = false) {
        if (typeof verdict === 'boolean') {
            skipHistoryRecord = verdict;
            verdict = 'UNKNOWN';
        }
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
                if (currentRepoFilter === 'pass_bug') {
                    return code === 'PASS_BUG_FOUND';
                }
                if (currentRepoFilter === 'pass_safe') {
                    return code === 'PASS_SOUND' || (!code && String(item.status).includes('SAFE'));
                }
                if (currentRepoFilter === 'regression') {
                    return code === 'REGRESSION_FAILED' || (!code && String(item.status).includes('VIOLATION'));
                }
                return true;
            });

            if (filtered.length === 0) {
                const tr = repoExplorerTabela.insertRow();
                tr.innerHTML = `<td colspan="12" style="text-align:center; padding:20px; color:#64748b;">No module matches the selected filter.</td>`;
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
                const statusBadge = `<span class="severity-badge" style="background-color: ${statusColor};">${escapeHtml(item.status)}</span>`;
                const langBadge = `<span style="background:#e0e7ff; color:#3730a3; padding:2px 7px; border-radius:4px; font-weight:700; font-size:11px;">${escapeHtml(item.lang || 'C/C++')}</span>`;
                const phaseBadge = item.phase
                    ? `<span style="background:#fef3c7; color:#92400e; padding:2px 6px; border-radius:4px; font-weight:700; font-size:10.5px; white-space:nowrap;">${escapeHtml(item.phase.split(':')[0])}</span>`
                    : `<span style="color:#94a3b8;">-</span>`;

                let testStatusBadge = '<span style="color:#94a3b8;">-</span>';
                if (item.test_status) {
                    let tsColor = '#059669';
                    let tsBg = '#ecfdf5';
                    let tsBorder = '#10b981';
                    if (item.test_status_code === 'REGRESSION_FAILED') {
                        tsColor = '#dc2626';
                        tsBg = '#fef2f2';
                        tsBorder = '#ef4444';
                    } else if (item.test_status.includes('PASS')) {
                        tsColor = '#059669';
                        tsBg = '#ecfdf5';
                        tsBorder = '#10b981';
                    }
                    const oracleSubtext = item.expected_verdict
                        ? `<div style="font-size:10px; color:#64748b; margin-top:2px;">Expected: <code>${escapeHtml(item.expected_verdict)}</code></div>`
                        : '';
                    testStatusBadge = `<div style="display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700; background:${tsBg}; color:${tsColor}; border:1px solid ${tsBorder}; white-space:nowrap;">${escapeHtml(item.test_status)}</div>${oracleSubtext}`;
                }

                const ssaVccStr = (item.vccs !== undefined) ? `<strong>${escapeHtml(item.vccs)} VCCs</strong> <small style="color:#64748b;">(${escapeHtml(item.ssa_assigns || 0)} SSA)</small>` : `Score ${escapeHtml(item.score)}`;
                const cliSubtext = item.esbmc_cli
                    ? `<div style="margin-top:4px; font-family:monospace; font-size:10.5px; color:#475569; background:#f8fafc; border:1px solid #e2e8f0; border-radius:4px; padding:2px 6px; word-break:break-all;" title="Exact Reproducible ESBMC CLI Command">💻 ${escapeHtml(item.esbmc_cli)}</div>`
                    : '';
                const witnessHtml = item.z3_witness
                    ? `<div style="color:#dc2626; font-weight:600; font-size:12px;">❌ ${escapeHtml(item.z3_witness)}</div>${cliSubtext}`
                    : `<div><span style="font-weight:600; color:#4f46e5;">${escapeHtml(item.mode || 'Symbolic BMC')}</span> <small style="color:#64748b;">(Score ${escapeHtml(item.score)})</small></div>${cliSubtext}`;

                tr.innerHTML = `
                    <td><strong>${escapeHtml(item.index)}</strong></td>
                    <td>${langBadge}</td>
                    <td>${phaseBadge}</td>
                    <td><code>${escapeHtml(item.directory)}</code></td>
                    <td><strong>${escapeHtml(item.file)}</strong></td>
                    <td>${witnessHtml}</td>
                    <td><code>${escapeHtml(item.fused_names)}</code> <small>(${escapeHtml(item.fused_deps)})</small></td>
                    <td>${ssaVccStr}</td>
                    <td><code>${escapeHtml(item.wall_time || '-')}</code></td>
                    <td>${statusBadge}</td>
                    <td>${testStatusBadge}</td>
                    <td style="text-align:center;">
                        <button class="btn-ver-homogeneizado btn-editor" data-index="${escapeHtml(item.index)}" style="padding: 4px 10px; font-size: 11px; background: #0284c7; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; white-space: nowrap;">
                            👁️ View Code
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
            if (verdict === 'FAILED') {
                statusBanner.className = 'status-banner failed';
                statusBanner.textContent = `❌ VERIFICATION FAILED (${violationDetails.length} VIOLATION(S))`;
            } else {
                statusBanner.className = 'status-banner inconclusive';
                statusBanner.textContent = INCONCLUSIVE_BANNERS[verdict] || INCONCLUSIVE_BANNERS.UNKNOWN;
            }
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
                    const cweNumber = String(v.cwe).replace(/\D/g, ''); 
                    cweHtml = `<a href="https://cwe.mitre.org/data/definitions/${cweNumber}.html" target="_blank" style="color: #007bff; text-decoration: none; font-weight: bold;" title="View MITRE Specification">${escapeHtml(v.cwe)}</a>`;
                }

                let badgeClass = 'severity-na';
                if (v.severity === 'Critical') badgeClass = 'severity-critical';
                else if (v.severity === 'High') badgeClass = 'severity-high';
                else if (v.severity === 'Medium') badgeClass = 'severity-medium';
                else if (v.severity === 'Low') badgeClass = 'severity-low';

                let severityHtml = `<span class="severity-badge ${badgeClass}">${escapeHtml(v.severity)}</span>`;
                row.innerHTML = `<td>${escapeHtml(v.file)}</td><td>${escapeHtml(v.function)}</td><td>${escapeHtml(v.line)}</td><td>${escapeHtml(v.message)}</td><td>${cweHtml}</td><td>${severityHtml}</td>`;
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
        } else if (verdict === 'FAILED') {
            statusBanner.className = 'status-banner failed';
            statusBanner.textContent = '❌ VERIFICATION FAILED — SEE MODULE TABLE';
            cardPassos.textContent = 0;
        } else if (verdict !== 'SUCCESSFUL') {
            statusBanner.className = 'status-banner inconclusive';
            statusBanner.textContent = INCONCLUSIVE_BANNERS[verdict] || INCONCLUSIVE_BANNERS.UNKNOWN;
            cardPassos.textContent = 0;
        } else {
            statusBanner.className = 'status-banner success';
            statusBanner.textContent = '✅ VERIFICATION SUCCESSFUL — STATUS: OK (NO VULNERABILITIES FOUND)';
            cardViolacoes.className = 'value';
            cardViolacoes.style.color = 'var(--success)';
            if (sucessoSection) sucessoSection.style.display = 'block';
            cardPassos.textContent = resultsArray[0]?.steps?.length || 0;
        }

        // Test-suite exploration with expected oracles:
        if (repoExplorationSummary && Array.isArray(repoExplorationSummary) && repoExplorationSummary.length > 0) {
            const hasOracles = repoExplorationSummary.some(it => it.expected_verdict && it.expected_verdict !== '-');
            const regressions = repoExplorationSummary.filter(it => it.test_status_code === 'REGRESSION_FAILED');
            const passBugs = repoExplorationSummary.filter(it => it.test_status_code === 'PASS_BUG_FOUND');
            const passSafe = repoExplorationSummary.filter(it => it.test_status_code === 'PASS_SOUND');
            const inconclusiveOracles = repoExplorationSummary.filter(it => it.test_status_code === 'INCONCLUSIVE');

            if (hasOracles) {
                if (regressions.length > 0) {
                    statusBanner.className = 'status-banner failed';
                    statusBanner.textContent = `🔴 TEST SUITE: ${regressions.length} REGRESSION(S) DETECTED (ORACLE MISMATCH)`;
                } else if (inconclusiveOracles.length > 0) {
                    statusBanner.className = 'status-banner inconclusive';
                    statusBanner.textContent = `⚠ TEST SUITE INCONCLUSIVE: ${inconclusiveOracles.length} ORACLE(S) WITHOUT A VERDICT`;
                } else if (verdict === 'SUCCESSFUL' || verdict === 'FAILED') {
                    statusBanner.className = 'status-banner success';
                    statusBanner.textContent = `🟢 TEST SUITE PASSED: ${passBugs.length} BUG(S) CONFIRMED + ${passSafe.length} PROVED SAFE [100% OF ORACLES MET]`;
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

        // --- Enable the Bug Reproduction Report (ESBMC GitHub) ---
        const failingRepoModules = (repoExplorationSummary || []).filter(item => {
            const s = String(item.status || '');
            return s.startsWith('VIOLATION') || s.startsWith('RAW ERROR') || (item.test_status_code === 'REGRESSION_FAILED');
        });
        const hasAnyFailure = hasViolations || failingRepoModules.length > 0;

        if (hasAnyFailure) {
            const reportData = buildESBMCBugReportMarkdown(resultsArray, codigoFonte, repoExplorationSummary, violationDetails);
            latestBugReportTitle = reportData.title;
            latestBugReportMarkdown = reportData.markdown;
            latestBugReportData = reportData;
            if (bugReportPre) bugReportPre.textContent = latestBugReportMarkdown;
            if (tabBugReport) tabBugReport.style.display = 'inline-block';
            if (bugReportActionBar) bugReportActionBar.style.display = 'flex';
        } else {
            latestBugReportTitle = '';
            latestBugReportMarkdown = '';
            latestBugReportData = null;
            if (tabBugReport) tabBugReport.style.display = 'none';
            if (bugReportActionBar) bugReportActionBar.style.display = 'none';
        }

        // --- Automatic Entry in the Quality History (Codacy Style) ---
        if (!skipHistoryRecord) {
            let runVerdict = 'SAFE';
            if (repoExplorationSummary && Array.isArray(repoExplorationSummary) && repoExplorationSummary.length > 0) {
                const hasRegressions = repoExplorationSummary.some(it => it.test_status_code === 'REGRESSION_FAILED');
                if (hasRegressions) runVerdict = 'REGRESSION';
                else if (hasAnyFailure) runVerdict = 'VIOLATION';
                else runVerdict = 'SAFE';
            } else {
                runVerdict = hasViolations ? 'VIOLATION' : 'SAFE';
            }

            recordVerificationRun({
                target: latestMainFileAnalyzed || 'main.c',
                lang: (latestSelectedLanguage || 'c').toUpperCase(),
                mode: latestSelectedEngineMode || 'assisted',
                verdict: runVerdict,
                vccs: totalVccsSum,
                ssa: totalSsaSum,
                cwes: violationDetails,
                resultsArray: resultsArray,
                codigoFonte: codigoFonte,
                repoSummary: repoExplorationSummary
            });
        }
    }

    if (btnVerRelatorioTab) {
        btnVerRelatorioTab.addEventListener('click', () => {
            if (tabBugReport) tabBugReport.click();
        });
    }

    if (btnGerarPdfRapido) {
        btnGerarPdfRapido.addEventListener('click', () => generateBugReportPdf());
    }

    if (btnCopiarRelatorioRapido) {
        btnCopiarRelatorioRapido.addEventListener('click', () => copyBugReportMarkdown(btnCopiarRelatorioRapido));
    }

    if (btnAbrirGithubIssueRapido) {
        btnAbrirGithubIssueRapido.addEventListener('click', () => openGithubIssue());
    }

    if (btnGerarPdf) {
        btnGerarPdf.addEventListener('click', () => generateBugReportPdf());
    }

    if (btnCopiarRelatorio) {
        btnCopiarRelatorio.addEventListener('click', () => copyBugReportMarkdown(btnCopiarRelatorio));
    }

    if (btnBaixarRelatorioMd) {
        btnBaixarRelatorioMd.addEventListener('click', () => downloadBugReportMd());
    }

    if (btnAbrirGithubIssue) {
        btnAbrirGithubIssue.addEventListener('click', () => openGithubIssue());
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

    // --- Homogenized & Sliced Code Modal (ESBMC/Z3 Input) ---
    function abrirModalHomogeneizado(item) {
        const modal = document.getElementById('homogenizedModal');
        const modalCode = document.getElementById('homogenizedModalCode');
        const modalMeta = document.getElementById('homogenizedModalMeta');
        const modalTitle = document.getElementById('homogenizedModalTitle');
        if (!modal || !modalCode) return;

        if (modalTitle) {
            modalTitle.textContent = `📄 Homogenised & Sliced Code: ${item.file}`;
        }
        if (modalMeta) {
            modalMeta.innerHTML = `
                <div><strong>Module:</strong> <code>${escapeHtml(item.directory)}/${escapeHtml(item.file)}</code> &nbsp;|&nbsp; <strong>Language:</strong> <span style="background:#e0e7ff; color:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700;">${escapeHtml(item.lang)}</span> &nbsp;|&nbsp; <strong>Mode:</strong> <em>${escapeHtml(item.mode)}</em></div>
                <div style="margin-top:4px;"><strong>Formal Verdict:</strong> <strong>${escapeHtml(item.status)}</strong> &nbsp;|&nbsp; <strong>VCCs:</strong> ${escapeHtml(item.vccs || 0)} &nbsp;|&nbsp; <strong>SSA Assignments:</strong> ${escapeHtml(item.ssa_assigns || 0)} &nbsp;|&nbsp; <strong>Time:</strong> ${escapeHtml(item.wall_time || '-')}</div>
                ${item.esbmc_cli ? `<div style="margin-top:4px; font-size:11px; color:#475569;"><strong>Reproducible CLI:</strong> <code>${escapeHtml(item.esbmc_cli)}</code></div>` : ''}
            `;
        }

        const codigo = item.homogenized_code || '// No intermediate code is available for this module.';
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
                copyHomogenizedCodeBtn.textContent = '✅ Copied!';
                setTimeout(() => { copyHomogenizedCodeBtn.textContent = originalText; }, 2000);
            } catch (err) {
                alert('Could not copy the code.');
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

    // =========================================================================
    // 📊 METRICS, HISTORY AND CHARTS MODULE (CODACY STYLE)
    // =========================================================================

    function getVerificationHistory() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY_CODACY_HISTORY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.warn('Error loading Codacy history from localStorage:', e);
            return [];
        }
    }

    function saveVerificationHistory(list) {
        try {
            localStorage.setItem(STORAGE_KEY_CODACY_HISTORY, JSON.stringify(list));
        } catch (e) {
            console.warn('Error saving Codacy history to localStorage:', e);
        }
    }

    function calculateCodacyGrade(score) {
        if (score >= 90) return { grade: 'A', color: '#10b981', label: 'Excellent Reliability', bg: '#d1fae5', textCol: '#065f46' };
        if (score >= 75) return { grade: 'B', color: '#3b82f6', label: 'Good Formal Integrity', bg: '#dbeafe', textCol: '#1e40af' };
        if (score >= 60) return { grade: 'C', color: '#f59e0b', label: 'Needs Attention', bg: '#fef3c7', textCol: '#92400e' };
        if (score >= 35) return { grade: 'D', color: '#f97316', label: 'Degraded / High Risk', bg: '#ffedd5', textCol: '#9a3412' };
        return { grade: 'F', color: '#ef4444', label: 'Critical / Multiple Failures', bg: '#fee2e2', textCol: '#991b1b' };
    }

    function computeRunScore(verdict, cwes = []) {
        if (verdict === 'SAFE') return 100;
        let score = 100;
        if (verdict === 'REGRESSION') score -= 25;
        if (!cwes || cwes.length === 0) {
            score -= 40;
        } else {
            cwes.forEach(c => {
                const sev = String(c.severity || '').toLowerCase();
                if (sev === 'critical') score -= 25;
                else if (sev === 'high') score -= 18;
                else if (sev === 'medium') score -= 12;
                else if (sev === 'low') score -= 6;
                else score -= 15;
            });
        }
        return Math.max(0, Math.min(100, score));
    }

    function recordVerificationRun(runData) {
        const history = getVerificationHistory();
        const runId = history.length > 0 ? (history[0].id || history.length) + 1 : 1;
        const now = new Date();
        const dataFormatada = now.toLocaleDateString('en-GB') + ' ' + now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        const score = computeRunScore(runData.verdict, runData.cwes);
        const gradeObj = calculateCodacyGrade(score);

        const newEntry = {
            id: runId,
            timestamp: dataFormatada,
            isoDate: now.toISOString(),
            target: runData.target || latestMainFileAnalyzed || 'main.c',
            lang: runData.lang || (latestSelectedLanguage || 'c').toUpperCase(),
            mode: runData.mode || latestSelectedEngineMode || 'assisted',
            verdict: runData.verdict,
            vccs: runData.vccs || 0,
            ssa: runData.ssa || 0,
            cwes: runData.cwes || [],
            score: score,
            grade: gradeObj.grade,
            resultsArray: runData.resultsArray || [],
            codigoFonte: runData.codigoFonte || '',
            repoSummary: runData.repoSummary || null
        };

        history.unshift(newEntry);
        if (history.length > 100) history.length = 100;
        saveVerificationHistory(history);
        renderCodacyMetricsView();
    }

    function renderCodacyMetricsView() {
        const history = getVerificationHistory();
        
        const badgeElem = document.getElementById('codacy-grade-badge');
        const scoreElem = document.getElementById('codacy-health-score');
        const labelElem = document.getElementById('codacy-grade-label');
        const trendElem = document.getElementById('codacy-trend-indicator');
        const trendSubElem = document.getElementById('codacy-trend-subtext');
        const safeRateElem = document.getElementById('codacy-safe-rate');
        const safeRateSubElem = document.getElementById('codacy-safe-rate-subtext');
        const totalVccsElem = document.getElementById('codacy-total-vccs');
        const totalRunsElem = document.getElementById('codacy-total-runs-count');

        if (history.length === 0) {
            if (badgeElem) { badgeElem.textContent = 'A'; badgeElem.style.background = '#10b981'; badgeElem.style.boxShadow = '0 4px 10px rgba(16, 185, 129, 0.3)'; }
            if (scoreElem) scoreElem.textContent = '100 / 100';
            if (labelElem) { labelElem.textContent = 'Excellent Reliability (Waiting for Verifications)'; labelElem.style.color = '#10b981'; }
            if (trendElem) trendElem.innerHTML = '<span>🟡 Stable</span>';
            if (trendSubElem) trendSubElem.textContent = 'No runs recorded';
            if (safeRateElem) safeRateElem.textContent = '100%';
            if (safeRateSubElem) safeRateSubElem.textContent = '0 failures recorded';
            if (totalVccsElem) totalVccsElem.textContent = '0';
            if (totalRunsElem) totalRunsElem.textContent = '0 audit(s) recorded';
        } else {
            const avgScore = history.reduce((acc, r) => acc + (r.score !== undefined ? r.score : 100), 0) / history.length;
            const roundScore = Math.round(avgScore);
            const overallGrade = calculateCodacyGrade(roundScore);

            if (badgeElem) {
                badgeElem.textContent = overallGrade.grade;
                badgeElem.style.background = overallGrade.color;
                badgeElem.style.boxShadow = `0 4px 10px ${overallGrade.color}55`;
            }
            if (scoreElem) scoreElem.textContent = `${roundScore} / 100`;
            if (labelElem) {
                labelElem.textContent = overallGrade.label;
                labelElem.style.color = overallGrade.color;
            }

            if (history.length > 1) {
                const diff = (history[0].score || 0) - (history[1].score || 0);
                if (diff > 0) {
                    if (trendElem) trendElem.innerHTML = `<span style="color:#059669;">🟢 Improving (+${diff} pts)</span>`;
                    if (trendSubElem) trendSubElem.textContent = 'Integrity rising as bugs are fixed';
                } else if (diff < 0) {
                    if (trendElem) trendElem.innerHTML = `<span style="color:#dc2626;">🔴 Regression (${diff} pts)</span>`;
                    if (trendSubElem) trendSubElem.textContent = 'New vulnerabilities detected';
                } else {
                    if (trendElem) trendElem.innerHTML = `<span>🟡 Stable</span>`;
                    if (trendSubElem) trendSubElem.textContent = 'Same integrity level as the previous run';
                }
            } else {
                if (trendElem) trendElem.innerHTML = `<span>🟢 Baseline</span>`;
                if (trendSubElem) trendSubElem.textContent = 'First verification recorded';
            }

            const safeCount = history.filter(r => r.verdict === 'SAFE').length;
            const safePercent = Math.round((safeCount / history.length) * 100);
            if (safeRateElem) {
                safeRateElem.textContent = `${safePercent}%`;
                safeRateElem.style.color = safePercent >= 80 ? '#059669' : (safePercent >= 50 ? '#d97706' : '#dc2626');
            }
            if (safeRateSubElem) safeRateSubElem.textContent = `${safeCount} of ${history.length} proved safe (SAFE)`;

            const totalVccs = history.reduce((acc, r) => acc + (r.vccs || 0), 0);
            if (totalVccsElem) totalVccsElem.textContent = totalVccs;
            if (totalRunsElem) totalRunsElem.textContent = `${history.length} audit(s) recorded`;
        }

        renderCodacyCharts(history);
        renderCodacyHistoryTable(history);
    }

    function renderCodacyCharts(history) {
        const chronHistory = history.slice(0, 15).reverse();
        const evolutionLabels = chronHistory.length > 0 
            ? chronHistory.map(r => `#${r.id} ${r.target.split('/').pop().substring(0, 14)}`)
            : ['No data'];
        const safeData = chronHistory.length > 0 ? chronHistory.map(r => r.verdict === 'SAFE' ? 1 : 0) : [0];
        const violationData = chronHistory.length > 0 ? chronHistory.map(r => r.verdict !== 'SAFE' ? (r.cwes && r.cwes.length ? r.cwes.length : 1) : 0) : [0];
        const vccData = chronHistory.length > 0 ? chronHistory.map(r => r.vccs || 0) : [0];

        const cweCounts = {};
        history.forEach(r => {
            (r.cwes || []).forEach(c => {
                const name = c.cwe && c.cwe !== 'N/A' ? c.cwe : 'General Vulnerability';
                cweCounts[name] = (cweCounts[name] || 0) + 1;
            });
        });

        let cweLabels = Object.keys(cweCounts);
        let cweValues = Object.values(cweCounts);
        let cweColors = ['#ef4444', '#f97316', '#eab308', '#8b5cf6', '#ec4899', '#06b6d4', '#64748b'];

        if (cweLabels.length === 0) {
            cweLabels = ['100% Free of Vulnerabilities (SAFE)'];
            cweValues = [1];
            cweColors = ['#10b981'];
        }

        const canvasEvol = document.getElementById('evolutionChartCanvas');
        const fallbackEvol = document.getElementById('evolutionChartFallback');
        const canvasCwe = document.getElementById('cweChartCanvas');
        const fallbackCwe = document.getElementById('cweChartFallback');

        if (typeof Chart !== 'undefined') {
            if (canvasEvol) canvasEvol.style.display = 'block';
            if (fallbackEvol) fallbackEvol.style.display = 'none';
            if (canvasCwe) canvasCwe.style.display = 'block';
            if (fallbackCwe) fallbackCwe.style.display = 'none';

            if (evolutionChartInstance) {
                evolutionChartInstance.destroy();
                evolutionChartInstance = null;
            }
            if (cweChartInstance) {
                cweChartInstance.destroy();
                cweChartInstance = null;
            }

            if (canvasEvol) {
                const ctxEvol = canvasEvol.getContext('2d');
                evolutionChartInstance = new Chart(ctxEvol, {
                    type: 'bar',
                    data: {
                        labels: evolutionLabels,
                        datasets: [
                            {
                                label: 'Proved Safe (SAFE)',
                                data: safeData,
                                backgroundColor: 'rgba(16, 185, 129, 0.85)',
                                borderColor: '#10b981',
                                borderWidth: 1,
                                borderRadius: 4,
                                stack: 'status'
                            },
                            {
                                label: 'Violations / Bugs',
                                data: violationData,
                                backgroundColor: 'rgba(239, 68, 68, 0.85)',
                                borderColor: '#ef4444',
                                borderWidth: 1,
                                borderRadius: 4,
                                stack: 'status'
                            },
                            {
                                label: 'Formal VCCs',
                                data: vccData,
                                type: 'line',
                                borderColor: '#3b82f6',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                tension: 0.3,
                                fill: false,
                                yAxisID: 'y1'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        scales: {
                            x: { grid: { display: false } },
                            y: {
                                beginAtZero: true,
                                title: { display: true, text: 'Status / Failures', font: { size: 10 } },
                                ticks: { precision: 0 }
                            },
                            y1: {
                                position: 'right',
                                beginAtZero: true,
                                grid: { display: false },
                                title: { display: true, text: 'VCC Count', font: { size: 10 } },
                                ticks: { precision: 0 }
                            }
                        },
                        plugins: {
                            legend: { position: 'top', labels: { boxWidth: 12, font: { size: 11 } } },
                            tooltip: { padding: 10, cornerRadius: 6 }
                        }
                    }
                });
            }

            if (canvasCwe) {
                const ctxCwe = canvasCwe.getContext('2d');
                cweChartInstance = new Chart(ctxCwe, {
                    type: 'doughnut',
                    data: {
                        labels: cweLabels,
                        datasets: [{
                            data: cweValues,
                            backgroundColor: cweColors,
                            borderWidth: 2,
                            borderColor: '#ffffff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '62%',
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: { boxWidth: 12, font: { size: 11 }, padding: 12 }
                            },
                            tooltip: { padding: 10, cornerRadius: 6 }
                        }
                    }
                });
            }
        } else {
            renderOfflineChartFallback(fallbackEvol, canvasEvol, evolutionLabels, safeData, violationData);
            renderOfflineCweFallback(fallbackCwe, canvasCwe, cweLabels, cweValues, cweColors);
        }
    }

    function renderOfflineChartFallback(container, canvas, labels, safe, violations) {
        if (!container) return;
        if (canvas) canvas.style.display = 'none';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.justifyContent = 'center';

        let html = '<div style="display:flex; align-items:flex-end; gap:8px; height:180px; padding:10px 0; border-bottom:1px solid #cbd5e1;">';
        labels.forEach((lbl, i) => {
            const isSafe = safe[i] > 0;
            const barBg = isSafe ? '#10b981' : '#ef4444';
            const barHeight = isSafe ? '70%' : '100%';
            const labelText = isSafe ? 'SAFE' : `${violations[i]} BUG`;
            html += `
                <div style="flex:1; display:flex; flex-direction:column; align-items:center; height:100%; justify-content:flex-end;">
                    <span style="font-size:10px; font-weight:700; color:${barBg}; margin-bottom:4px;">${labelText}</span>
                    <div style="width:100%; max-width:28px; height:${barHeight}; background:${barBg}; border-radius:4px 4px 0 0;"></div>
                    <span style="font-size:9.5px; color:#64748b; margin-top:6px; transform:rotate(-25deg); white-space:nowrap;">${lbl}</span>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;
    }

    function renderOfflineCweFallback(container, canvas, labels, values, colors) {
        if (!container) return;
        if (canvas) canvas.style.display = 'none';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.justifyContent = 'center';

        const total = values.reduce((a, b) => a + b, 0) || 1;
        let html = '<div style="display:flex; flex-direction:column; gap:10px; padding:10px;">';
        labels.forEach((lbl, i) => {
            const val = values[i];
            const pct = Math.round((val / total) * 100);
            const col = colors[i % colors.length];
            html += `
                <div>
                    <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600; margin-bottom:3px;">
                        <span>${lbl}</span>
                        <span style="color:${col};">${val} (${pct}%)</span>
                    </div>
                    <div style="background:#f1f5f9; height:10px; border-radius:5px; overflow:hidden;">
                        <div style="background:${col}; width:${pct}%; height:100%; border-radius:5px;"></div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;
    }

    function renderCodacyHistoryTable(history) {
        const tbody = document.getElementById('tabela-historico-codacy-body');
        const searchInput = document.getElementById('filterHistorySearch');
        const verdictSelect = document.getElementById('filterHistoryVerdict');
        if (!tbody) return;

        const searchTerm = (searchInput?.value || '').toLowerCase().trim();
        const verdictFilter = verdictSelect?.value || 'all';

        const filtered = history.filter(run => {
            if (verdictFilter !== 'all') {
                if (verdictFilter === 'SAFE' && run.verdict !== 'SAFE') return false;
                if (verdictFilter === 'VIOLATION' && run.verdict === 'SAFE') return false;
            }
            if (searchTerm) {
                const targetMatch = (run.target || '').toLowerCase().includes(searchTerm);
                const cweMatch = (run.cwes || []).some(c => (c.cwe || '').toLowerCase().includes(searchTerm) || (c.message || '').toLowerCase().includes(searchTerm));
                if (!targetMatch && !cweMatch) return false;
            }
            return true;
        });

        tbody.innerHTML = '';
        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="9" style="text-align: center; padding: 30px; color: #64748b; font-size: 13px;">
                        ${history.length === 0 ? 'No audits recorded yet. Run an analysis from the editor or click "🎲 Load Demo Data".' : 'No runs match the selected filters.'}
                    </td>
                </tr>
            `;
            return;
        }

        filtered.forEach(run => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid #f1f5f9';

            const gradeObj = calculateCodacyGrade(run.score !== undefined ? run.score : (run.verdict === 'SAFE' ? 100 : 50));
            
            let verdictBadge = '';
            if (run.verdict === 'SAFE') {
                verdictBadge = `<span style="background:#10b981; color:#fff; padding:3px 8px; border-radius:4px; font-weight:700; font-size:11px; white-space:nowrap;">✅ SAFE</span>`;
            } else if (run.verdict === 'REGRESSION') {
                verdictBadge = `<span style="background:#b91c1c; color:#fff; padding:3px 8px; border-radius:4px; font-weight:700; font-size:11px; white-space:nowrap;">🔴 REGRESSION</span>`;
            } else {
                verdictBadge = `<span style="background:#ef4444; color:#fff; padding:3px 8px; border-radius:4px; font-weight:700; font-size:11px; white-space:nowrap;">❌ VIOLATION</span>`;
            }

            let cwesHtml = '<span style="color:#94a3b8;">-</span>';
            if (run.cwes && run.cwes.length > 0) {
                cwesHtml = run.cwes.map(c => {
                    const cweNum = String(c.cwe || '').replace(/\D/g, '');
                    const link = cweNum ? `https://cwe.mitre.org/data/definitions/${cweNum}.html` : '#';
                    return `<a href="${link}" target="_blank" style="display:inline-block; background:#fee2e2; color:#991b1b; padding:1px 6px; border-radius:4px; font-size:10.5px; font-weight:700; text-decoration:none; margin:1px 2px;" title="${escapeHtml(c.message || '')}">${escapeHtml(c.cwe || 'CWE')}</a>`;
                }).join(' ');
            }

            const targetName = run.target.split('/').pop();
            const hasViolations = run.verdict !== 'SAFE';

            tr.innerHTML = `
                <td style="padding: 8px 10px; font-weight: 700;">#${escapeHtml(run.id)}</td>
                <td style="padding: 8px 10px; color: #64748b; font-size: 11.5px; white-space: nowrap;">${escapeHtml(run.timestamp)}</td>
                <td style="padding: 8px 10px;"><code style="font-weight: 600; color: #1e293b;" title="${escapeHtml(run.target)}">${escapeHtml(targetName)}</code></td>
                <td style="padding: 8px 10px;"><span style="background:#e0e7ff; color:#3730a3; padding:1px 6px; border-radius:4px; font-weight:700; font-size:10.5px;">${escapeHtml(run.lang || 'C')}</span></td>
                <td style="padding: 8px 10px;">${verdictBadge}</td>
                <td style="padding: 8px 10px;">${cwesHtml}</td>
                <td style="padding: 8px 10px;"><strong>${escapeHtml(run.vccs || 0)}</strong></td>
                <td style="padding: 8px 10px; text-align: center;">
                    <span style="background:${gradeObj.bg}; color:${gradeObj.textCol}; border:1px solid ${gradeObj.color}; padding:2px 8px; border-radius:12px; font-weight:800; font-size:12px;">${gradeObj.grade}</span>
                </td>
                <td style="padding: 8px 10px; text-align: center; white-space: nowrap;">
                    <button class="btn-load-run" data-run-id="${escapeHtml(run.id)}" style="background:#2563eb; color:#fff; padding:3px 8px; font-size:11px; border-radius:4px; font-weight:600; margin-right:4px;">
                        🔍 View
                    </button>
                    ${hasViolations ? `
                        <button class="btn-pdf-run" data-run-id="${escapeHtml(run.id)}" style="background:#b91c1c; color:#fff; padding:3px 8px; font-size:11px; border-radius:4px; font-weight:600; margin-right:4px;" title="Download PDF Bug Report">
                            📄 PDF
                        </button>
                    ` : ''}
                    <button class="btn-delete-run" data-run-id="${escapeHtml(run.id)}" style="background:#f1f5f9; color:#dc2626; border:1px solid #e2e8f0; padding:3px 7px; font-size:11px; border-radius:4px; font-weight:600;" title="Delete run">
                        🗑️
                    </button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    }

    function loadHistoricalRunIntoDashboard(runId) {
        const history = getVerificationHistory();
        const run = history.find(r => r.id === runId);
        if (!run) return;

        latestMainFileAnalyzed = run.target;
        latestSelectedLanguage = (run.lang || 'c').toLowerCase();
        latestSelectedEngineMode = run.mode || 'assisted';

        if (run.codigoFonte && editor) {
            editor.setValue(run.codigoFonte);
        }

        const runVerdict = run.verdict === 'SAFE' ? 'SUCCESSFUL' : (run.verdict === 'VIOLATION' ? 'FAILED' : (run.verdict || 'UNKNOWN'));
        renderDashboard(run.resultsArray || [], run.codigoFonte || '', run.repoSummary || null, runVerdict, true);
        tabDashboard.click();
    }

    function downloadHistoricalRunPdf(runId) {
        const history = getVerificationHistory();
        const run = history.find(r => r.id === runId);
        if (!run) return;

        const reportData = buildESBMCBugReportMarkdown(
            run.resultsArray || [],
            run.codigoFonte || '',
            run.repoSummary || null,
            run.cwes || []
        );
        latestBugReportTitle = reportData.title;
        latestBugReportMarkdown = reportData.markdown;
        latestBugReportData = reportData;
        generateBugReportPdf();
    }

    function deleteHistoricalRun(runId) {
        let history = getVerificationHistory();
        history = history.filter(r => r.id !== runId);
        saveVerificationHistory(history);
        renderCodacyMetricsView();
    }

    function loadDemoCodacyDataset() {
        const demoRuns = [
            {
                id: 5,
                timestamp: '13/10/2026 10:14:00',
                isoDate: new Date(Date.now() - 60000).toISOString(),
                target: 'sanitized_pipeline.c',
                lang: 'C',
                mode: 'assisted',
                verdict: 'SAFE',
                vccs: 18,
                ssa: 42,
                cwes: [],
                score: 100,
                grade: 'A',
                resultsArray: [{ status: 'success', steps: [] }],
                codigoFonte: '// sanitized_pipeline.c\n#include <assert.h>\nint main() {\n    int a = 10;\n    int b = 20;\n    assert(a + b == 30);\n    return 0;\n}',
                repoSummary: null
            },
            {
                id: 4,
                timestamp: '13/10/2026 09:45:00',
                isoDate: new Date(Date.now() - 3600000).toISOString(),
                target: 'concurrency_mutex.c',
                lang: 'C',
                mode: 'assisted',
                verdict: 'SAFE',
                vccs: 24,
                ssa: 58,
                cwes: [],
                score: 100,
                grade: 'A',
                resultsArray: [{ status: 'success', steps: [] }],
                codigoFonte: '// concurrency_mutex.c\n#include <assert.h>\n#include <pthread.h>\nint shared = 0;\nint main() {\n    shared++;\n    assert(shared == 1);\n    return 0;\n}',
                repoSummary: null
            },
            {
                id: 3,
                timestamp: '13/10/2026 09:12:00',
                isoDate: new Date(Date.now() - 7200000).toISOString(),
                target: 'integer_overflow_demo.c',
                lang: 'C',
                mode: 'assisted',
                verdict: 'VIOLATION',
                vccs: 12,
                ssa: 28,
                cwes: [{ cwe: 'CWE-190', message: 'arithmetic overflow on unsigned integer', severity: 'Medium', file: 'integer_overflow_demo.c', line: 14, function: 'calculate_bonus' }],
                score: 72,
                grade: 'C',
                resultsArray: [{ status: 'violation', steps: [{ type: 'violation', cwe: 'CWE-190', message: 'arithmetic overflow', line: 14, file: 'integer_overflow_demo.c' }] }],
                codigoFonte: '// integer_overflow_demo.c\n#include <limits.h>\nint calculate_bonus(int val) {\n    return val + 1000;\n}\nint main() {\n    int x = INT_MAX - 10;\n    int r = calculate_bonus(x);\n    return 0;\n}',
                repoSummary: null
            },
            {
                id: 2,
                timestamp: '12/10/2026 17:30:00',
                isoDate: new Date(Date.now() - 86400000).toISOString(),
                target: 'null_pointer_demo.c',
                lang: 'C',
                mode: 'assisted',
                verdict: 'VIOLATION',
                vccs: 15,
                ssa: 36,
                cwes: [{ cwe: 'CWE-476', message: 'dereference failure: NULL pointer dereference', severity: 'High', file: 'null_pointer_demo.c', line: 8, function: 'process_node' }],
                score: 65,
                grade: 'C',
                resultsArray: [{ status: 'violation', steps: [{ type: 'violation', cwe: 'CWE-476', message: 'dereference failure', line: 8, file: 'null_pointer_demo.c' }] }],
                codigoFonte: '// null_pointer_demo.c\n#include <stdlib.h>\nstruct Node { int val; };\nint process_node(struct Node* n) {\n    return n->val;\n}\nint main() {\n    process_node(NULL);\n    return 0;\n}',
                repoSummary: null
            },
            {
                id: 1,
                timestamp: '12/10/2026 14:15:00',
                isoDate: new Date(Date.now() - 172800000).toISOString(),
                target: 'buffer_overflow_demo.c',
                lang: 'C',
                mode: 'assisted',
                verdict: 'VIOLATION',
                vccs: 22,
                ssa: 50,
                cwes: [
                    { cwe: 'CWE-125', message: 'out-of-bounds read', severity: 'Critical', file: 'buffer_overflow_demo.c', line: 12, function: 'get_element' },
                    { cwe: 'CWE-787', message: 'out-of-bounds write', severity: 'Critical', file: 'buffer_overflow_demo.c', line: 15, function: 'set_element' }
                ],
                score: 45,
                grade: 'D',
                resultsArray: [{ status: 'violation', steps: [{ type: 'violation', cwe: 'CWE-125', message: 'out-of-bounds read', line: 12, file: 'buffer_overflow_demo.c' }] }],
                codigoFonte: '// buffer_overflow_demo.c\nint get_element(int* arr, int idx) {\n    return arr[idx];\n}\nint main() {\n    int a[5] = {1, 2, 3, 4, 5};\n    return get_element(a, 10);\n}',
                repoSummary: null
            }
        ];
        saveVerificationHistory(demoRuns);
        renderCodacyMetricsView();
    }

    function exportHistoryCsv() {
        const history = getVerificationHistory();
        if (history.length === 0) {
            alert('History is empty. There are no runs to export.');
            return;
        }

        const headers = ['ID', 'Date_Time', 'Target', 'Language', 'Mode', 'Verdict', 'VCCs', 'Score', 'Grade', 'CWEs'];
        const rows = history.map(r => [
            r.id,
            `"${r.timestamp}"`,
            `"${r.target}"`,
            r.lang,
            r.mode,
            r.verdict,
            r.vccs,
            r.score,
            r.grade,
            `"${(r.cwes || []).map(c => c.cwe).join('; ')}"`
        ]);

        const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement('a');
        link.setAttribute('href', encodedUri);
        link.setAttribute('download', `esbmc_codacy_history_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    function exportHistoryJson() {
        const history = getVerificationHistory();
        if (history.length === 0) {
            alert('History is empty. There are no runs to export.');
            return;
        }

        const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(history, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute('href', dataStr);
        downloadAnchor.setAttribute('download', `esbmc_codacy_history_${new Date().toISOString().slice(0, 10)}.json`);
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        document.body.removeChild(downloadAnchor);
    }

    function clearCodacyHistory() {
        if (confirm('Delete the entire audit history stored in this browser?')) {
            localStorage.removeItem(STORAGE_KEY_CODACY_HISTORY);
            renderCodacyMetricsView();
        }
    }

    if (btnCarregarDemoCodacy) {
        btnCarregarDemoCodacy.addEventListener('click', () => loadDemoCodacyDataset());
    }

    if (btnExportarCsvCodacy) {
        btnExportarCsvCodacy.addEventListener('click', () => exportHistoryCsv());
    }

    if (btnExportarJsonCodacy) {
        btnExportarJsonCodacy.addEventListener('click', () => exportHistoryJson());
    }

    if (btnLimparHistoricoCodacy) {
        btnLimparHistoricoCodacy.addEventListener('click', () => clearCodacyHistory());
    }

    if (filterHistorySearch) {
        filterHistorySearch.addEventListener('input', () => renderCodacyHistoryTable(getVerificationHistory()));
    }

    if (filterHistoryVerdict) {
        filterHistoryVerdict.addEventListener('change', () => renderCodacyHistoryTable(getVerificationHistory()));
    }

    if (tabelaHistoricoBody) {
        tabelaHistoricoBody.addEventListener('click', (e) => {
            const btnLoad = e.target.closest('.btn-load-run');
            const btnPdf = e.target.closest('.btn-pdf-run');
            const btnDelete = e.target.closest('.btn-delete-run');

            if (btnLoad) {
                const runId = parseInt(btnLoad.dataset.runId, 10);
                loadHistoricalRunIntoDashboard(runId);
            } else if (btnPdf) {
                const runId = parseInt(btnPdf.dataset.runId, 10);
                downloadHistoricalRunPdf(runId);
            } else if (btnDelete) {
                const runId = parseInt(btnDelete.dataset.runId, 10);
                if (confirm(`Remove run #${runId} from the history?`)) {
                    deleteHistoricalRun(runId);
                }
            }
        });
    }

    // Initialize Codacy metrics on load
    renderCodacyMetricsView();

});