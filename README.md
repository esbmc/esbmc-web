# ESBMC-Web - ESBMC Code Analyzer

Este repositório contém o dashboard web para análise de código com ESBMC.

## Arquitetura (Fluxo de Dados)

graph TD;
    subgraph "Navegador do Usuário"
        A["Frontend (index.html)"]
        D["Dashboard (script.js)"]
    end

    subgraph "Servidor"
        B["Backend (app.py)"]
    end

    subgraph "Ferramenta"
         C["ESBMC (Core)"]
    end
    
    A -- "1. Envia (Código + Flags) via API" --> B;
    B -- "2. Executa o ESBMC com os dados" --> C;
    C -- "3. Retorna Relatório (JSON/Texto)" --> B;
    B -- "4. Envia Resultado (JSON) de volta" --> D;
    D -- "5. Renderiza o Dashboard na UI" --> A;

sequenceDiagram
    actor User
    participant F as "Frontend (script.js)"
    participant B as "Backend (app.py)"
    participant E as "ESBMC"
    
    User->>F: "1. Insere código, flags e clica em Analyze"
    activate F
    F->>B: "2. Envia POST /analisar (JSON com código e flags)"
    deactivate F
    activate B
    B->>E: "3. Executa 'esbmc [flags] codigo.c --generate-json-report'"
    activate E
    E-->>B: "4. Retorna (Saída de texto + report.json)"
    deactivate E
    B-->>F: "5. Retorna JSON (resultado_texto, dashboard_data)"
    deactivate B
    activate F
    F->>F: "6. Chama renderDashboard(data)"
    
    alt "Verificação Falhou"
        F->>User: "7a. Exibe Banner VERMELHO e Contra-exemplo"
    else "Verificação OK"
        F->>User: "7b. Exibe Banner VERDE (SUCCESSFUL)"
    end
    deactivate F


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
