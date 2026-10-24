# ESBMC-Web

A browser front end for [ESBMC](https://github.com/esbmc/esbmc), the SMT-based bounded model checker. Verify C, C++ and Python code from an editor, uploaded files, or a public Git repository, and get the verdict, counterexample trace and reports without leaving the browser.

## Features

- **Editor and uploads**: CodeMirror editor for C, C++ and Python, plus extra dependency files (`.h`, `.hpp`, `.c`, `.cpp`, `.py`).
- **Git repositories**: paste a repository URL, or a `/tree/` or `/blob/` link to verify only one folder or file. Repository mode ranks modules by risk and verifies them in batch, with an optional language filter.
- **Code preparation** (`backend/sanitizers/`): generates a `main()` harness with nondeterministic inputs for code without an entry point, links implementation files from other directories, lowers C++20 constructs to C++14, and stubs headers missing from ESBMC's C++ library. Pick **Strict Pure ESBMC** to run ESBMC on the code unchanged.
- **Results**: raw ESBMC output or a dashboard with the violated property, highlighted source lines and a step-by-step trace.
- **Reports**: SV-COMP witnesses (GraphML, YAML), JSON, CSV, a LaTeX table and a standalone HTML report.
- **Background runs**: live logs and progress, with a cancel button.

> Generated harnesses and stubs approximate the real code. Before trusting a verdict, inspect the code ESBMC actually checked with **View Code** in the dashboard.

## How it works

1. The frontend (`frontend/`) sends the code or repository URL to the Flask API (`backend/app.py`, `POST /analisar`).
2. The backend clones the repository if there is one (shallow, `blob:none`), then prepares each target with the sanitizers.
3. It runs ESBMC in a background task. The frontend polls `GET /status/<task_id>` for logs and progress; `POST /cancelar/<task_id>` stops the run.
4. The backend parses ESBMC's output into the dashboard data and reports.

Related tools: the [VS Code extension](https://github.com/esbmc/vscode-esbmc) and [AI agent plugins](https://github.com/esbmc/agent-marketplace).

## Installation

### Windows (WSL)

1. Install WSL with Ubuntu, then clone this repository.
2. Run `Install ESBMC WSL.bat` once. It installs ESBMC, Clang and Python inside WSL.
3. Run `ESBMC-WEB.bat`. It starts the backend on port 5000 and opens the UI in your browser.

### Linux / macOS

Requires Python 3.10+ and `esbmc` on `PATH`. Clang is optional; the C++ sanitizer uses it.

```bash
git clone https://github.com/esbmc/esbmc-web.git && cd esbmc-web
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cd backend && python3 app.py   # serves http://127.0.0.1:5000
```

Then open `frontend/index.html` in a browser. Set `ESBMC_WEB_DEBUG=1` to enable Flask debug mode.

## Tests

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt
python3 -m pytest                    # ESBMC-backed tests skip if esbmc is not on PATH

(cd backend && python3 app.py) &     # the UI test drives the real backend on :5000
node tests/e2e/ui_verdicts.mjs       # needs Chrome (or CHROME_BIN), Node >= 22 and esbmc
```

Known defects are marked strict `xfail` (pytest) or `knownDefect` (UI test). They assert the correct behaviour, so an unexpected pass fails the run until the marker is removed.

## Citation

ESBMC-Web was developed at the Federal University of Amazonas (UFAM). If you use it in research, please cite ESBMC:

- M. R. Gadelha, F. R. Monteiro, J. Morse, L. C. Cordeiro, B. Fischer, D. A. Nicole. *ESBMC 5.0: An Industrial-Strength C Model Checker.* ASE 2018. [doi:10.1145/3238147.3240481](https://doi.org/10.1145/3238147.3240481)
- B. Farias, R. Menezes, E. B. de Lima Filho, Y. Sun, L. C. Cordeiro. *ESBMC-Python: A Bounded Model Checker for Python Programs.* ISSTA 2024. [doi:10.1145/3650212.3685304](https://doi.org/10.1145/3650212.3685304)
