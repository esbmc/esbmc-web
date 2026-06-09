@echo off
title Inicializador ESBMC-Web
echo ==========================================
echo Iniciando o ESBMC-Web...
echo ==========================================

:: Forca o Windows a entrar na pasta exata onde este arquivo .bat esta salvo
cd /d "%~dp0"

:: 1. Cria um arquivo limpo de instrucoes para o Linux (runner.sh)
echo echo "Iniciando servidor backend do ESBMC-Web..." > runner.sh
echo if [ ! -d "venv" ]; then >> runner.sh
echo     echo "Criando ambiente virtual (isso demora um pouco na primeira vez)..." >> runner.sh
echo     python3 -m venv venv >> runner.sh
echo fi >> runner.sh
echo source venv/bin/activate >> runner.sh
echo cd backend >> runner.sh
echo echo "Verificando pacotes..." >> runner.sh
echo pip install -r requirements.txt >> runner.sh
echo echo "Iniciando o Flask..." >> runner.sh
echo python3 app.py >> runner.sh

:: 2. Remove quebras de linha invisiveis do Windows que quebram o Linux
wsl -e bash -c "sed -i 's/\r$//' runner.sh"

:: 3. Executa as instrucoes e MANTEM a janela preta aberta (cmd /k)
start "Backend ESBMC-Web" cmd /k "wsl -e bash runner.sh"

echo Aguardando o servidor subir...
timeout /t 8 /nobreak > nul

:: 4. Abre a interface web
start "" "frontend\index.html"

exit