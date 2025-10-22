# ESBMC-Web - ESBMC Code Analyzer

Este repositório contém o dashboard web para análise de código com ESBMC.

## Arquitetura (Fluxo de Dados)
The diagram below illustrates the order of interactions:

```mermaid
graph TD;
    subgraph "User Browser"
        A["Frontend (index.html)"]
        D["Dashboard (script.js)"]
    end

    subgraph "Server"
        B["Backend (app.py)"]
    end

    subgraph "Tool"
         C["ESBMC (Core)"]
    end
    
    A -- "1. Sends (Code + Flags) via API" --> B;
    B -- "2. Executes ESBMC with data" --> C;
    C -- "3. Returns Report (JSON/Text)" --> B;
    B -- "4. Sends Result (JSON) back" --> D;
    D -- "5. Renders Dashboard on UI" --> A;

```

## Architecture (Sequence of Events)
The diagram below illustrates the order of interactions:

```mermaid
sequenceDiagram
    actor User
    participant Frontend as "Frontend (index.htm)"
    participant Backend_App as "Backend (app.py)"
    participant ESBMC as ESBMC
    participant Dashboard as "Dashboard (script.js)"

    User->>Frontend: 1. Inserts Code, Selects Flags, Clicks "Analyze"
    activate Frontend
    Frontend->>Backend_App: 2. POST /analyze (Code + Flags)
    deactivate Frontend
    activate Backend_App
    Backend_App->>ESBMC: 3. Executes ESBMC with code.c and flags
    activate ESBMC
    ESBMC-->>Backend_App: 4. Returns ESBMC Output (JSON + Text)
    deactivate ESBMC

    alt Analysis Successful
        Backend_App->>Dashboard: 5a. Returns JSON (SUCCESS)
        activate Dashboard
        Dashboard->>User: 6a. Displays SUCCESS Result on UI
        deactivate Dashboard
    else Analysis Failed / Violation
        Backend_App->>Dashboard: 5b. Returns JSON (ERROR / VIOLATION)
        activate Dashboard
        Dashboard->>User: 6b. Displays ERROR / VIOLATION (Counter-example) on UI
        deactivate Dashboard
    end
    deactivate Backend_App
```


## Arquitetura

O projeto é dividido em duas partes:
* `/backend`: Um servidor Flask (Python) que recebe o código e executa o ESBMC.
* `/frontend`: Uma página HTML/JS estática que serve como interface para o usuário.

## Instalação (Setup)

1.  Clone o repositório:
    ```bash
    git clone [https://github.com/esbmc/esbmc-web.git](https://github.com/esbmc/esbmc-web.git)
    cd esbmc-web
    ```

2.  Crie e ative um ambiente virtual (recomendado):
    ```bash
    python -m venv venv
    source venv/bin/activate  # No Linux/macOS
    # ou
    .\venv\Scripts\activate   # No Windows
    ```

3.  Instale as dependências do backend:
    ```bash
    pip install -r backend/requirements.txt
    ```

## Como Executar (Usage)

1.  Inicie o servidor backend:
    ```bash
    python backend/app.py
    ```

2.  Abra o arquivo `frontend/index.html` diretamente no seu navegador.
