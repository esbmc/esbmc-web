#!/bin/bash

echo "============================================="
echo "  A iniciar o servidor backend do ESBMC-Web... "
echo "============================================="

# Garante que o terminal está na pasta correta
cd "$(dirname "$0")"

# 1. VERIFICAÇÃO INTELIGENTE DO SISTEMA
# Se o pacote python3-venv não estiver instalado, ele instala agora!
if ! dpkg -l | grep -q "python3-venv"; then
    echo "Aviso: O pacote python3-venv não foi detetado."
    echo "A instalar pacotes essenciais do Python (pode pedir a sua palavra-passe do Linux)..."
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip
fi

# 2. AUTO-RECUPERAÇÃO
# Remove o ambiente virtual se ele estiver corrompido
if [ -d "venv" ] && [ ! -f "venv/bin/python3" ]; then
    echo "Ambiente virtual corrompido. A remover para recriar..."
    rm -rf venv
fi

# 3. CRIAÇÃO BLINDADA DO AMBIENTE VIRTUAL
if [ ! -d "venv" ]; then
    echo "A criar o ambiente virtual (venv)..."
    # Tenta criar com --copies primeiro (melhor para partições Windows)
    python3 -m venv venv --copies
    
    # Se falhar, tenta o Plano B (padrão do Linux)
    if [ $? -ne 0 ]; then
        echo "Aviso: Tentativa com --copies falhou. A tentar método padrão..."
        python3 -m venv venv
        
        # Se falhar de novo, aborta com erro claro
        if [ $? -ne 0 ]; then
            echo "ERRO CRÍTICO: Não foi possível criar o venv de forma alguma."
            read -p "Pressione Enter para fechar..."
            exit 1
        fi
    fi
fi

# 4. INSTALAÇÃO DE DEPENDÊNCIAS
echo "A verificar e a atualizar as dependências do projeto..."
./venv/bin/python3 -m pip install --upgrade pip
./venv/bin/python3 -m pip install -r backend/requirements.txt
if [ $? -ne 0 ]; then
    echo "ERRO: Falha ao instalar as dependências do requirements.txt."
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# 5. INÍCIO DO SERVIDOR
echo "A iniciar o servidor Flask..."
cd backend
../venv/bin/python3 app.py
