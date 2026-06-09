#!/bin/bash

echo "============================================="
echo "  A iniciar o servidor backend do ESBMC-Web... "
echo "============================================="

# Garante que o terminal está na pasta correta
cd "$(dirname "$0")"

# Remove o ambiente virtual se ele estiver corrompido ou vazio
if [ -d "venv" ] && [ ! -f "venv/bin/python3" ]; then
    echo "Ambiente virtual corrompido. A remover para recriar..."
    rm -rf venv
fi

# Cria o ambiente virtual com --copies (essencial para partições Windows)
if [ ! -d "venv" ]; then
    echo "A criar o ambiente virtual (venv) com --copies..."
    python3 -m venv venv --copies
    if [ $? -ne 0 ]; then
        echo "ERRO: Falha ao criar o venv. Verifique se o pacote python3-venv está instalado."
        read -p "Pressione Enter para fechar..."
        exit 1
    fi
fi

# Atualiza o pip e instala os requisitos DIRETAMENTE pelo Python do venv (sem usar o comando source)
echo "A verificar e a atualizar as dependências..."
./venv/bin/python3 -m pip install --upgrade pip
./venv/bin/python3 -m pip install -r backend/requirements.txt
if [ $? -ne 0 ]; then
    echo "ERRO: Falha ao instalar as dependências do Python."
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# Inicia o servidor Flask
echo "A iniciar o servidor Flask..."
cd backend
../venv/bin/python3 app.py
