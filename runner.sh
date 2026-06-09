#!/bin/bash
echo "============================================="
echo "  Iniciando servidor backend do ESBMC-Web... "
echo "============================================="

# Garante que estamos na pasta correta onde o script está localizado
cd "$(dirname "$0")"

# Cria o ambiente virtual se não existir usando --copies para compatibilidade com NTFS/Windows
if [ ! -d "venv" ]; then
    echo "Criando ambiente virtual Python (venv) usando --copies..."
    echo "Nota: --copies e usado para compatibilidade com caminhos do Windows no WSL."
    python3 -m venv venv --copies
    if [ $? -ne 0 ]; then
        echo "ERRO: Falha ao criar o venv. Certifique-se de que o python3-venv esta instalado."
        read -p "Pressione Enter para fechar..."
        exit 1
    fi
fi

# Ativa o ambiente virtual
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "ERRO: Falha ao ativar o ambiente virtual (venv)."
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# Entra na pasta do backend
cd backend
if [ $? -ne 0 ]; then
    echo "ERRO: Pasta 'backend' nao encontrada na raiz do projeto."
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# Garante a instalação e atualização segura das dependências
echo "Verificando dependencias (requirements.txt)..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERRO: Falha ao instalar as dependencias do Python."
    read -p "Pressione Enter para fechar..."
    exit 1
fi

# Executa o Flask com segurança
echo "Iniciando o servidor Flask..."
python3 app.py
