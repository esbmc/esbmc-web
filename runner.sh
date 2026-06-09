#!/bin/bash

echo "============================================="
echo "  A iniciar o servidor backend do ESBMC-Web... "
echo "============================================="

# Força o Linux a reconhecer as pastas onde instalámos o ESBMC e o Clang
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Garante que o terminal está na pasta correta
cd "$(dirname "$0")"

# Remove o ambiente virtual se ele estiver corrompido
if [ -d "venv" ] && [ ! -f "venv/bin/python3" ]; then
    echo "Ambiente virtual corrompido. A remover para recriar..."
    rm -rf venv
fi

# Verifica pacotes do Ubuntu
if ! dpkg -l | grep -q "python3-venv"; then
    echo "Aviso: O pacote python3-venv não foi detetado."
    sudo apt-get update
    sudo apt-get install -y python3-venv python3-pip
fi

# Cria o ambiente virtual
if [ ! -d "venv" ]; then
    echo "A criar o ambiente virtual (venv)..."
    python3 -m venv venv --copies
    if [ $? -ne 0 ]; then
        python3 -m venv venv
        if [ $? -ne 0 ]; then
            echo "ERRO CRÍTICO: Não foi possível criar o venv."
            read dummy
            exit 1
        fi
    fi
fi

# Instala dependências
echo "A verificar e a atualizar as dependências..."
./venv/bin/python3 -m pip install --upgrade pip
./venv/bin/python3 -m pip install -r backend/requirements.txt

# Inicia o servidor Flask
echo "A iniciar o servidor Flask..."
cd backend
../venv/bin/python3 app.py
