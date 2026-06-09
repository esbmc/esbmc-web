@echo off
title Inicializador ESBMC-Web
echo ==========================================
echo A iniciar o ESBMC-Web...
echo ==========================================

:: Garante que o Windows reconhece a pasta atual
cd /d "%~dp0"

:: Limpa quebras de linha do Windows (CRLF para LF) que causam bugs no Linux
wsl -e bash -c "sed -i 's/\r$//' runner.sh"
wsl -e bash -c "sed -i 's/\r$//' backend/requirements.txt"

:: Executa o script do Linux e mantém a janela aberta
start "Backend ESBMC-Web" cmd /k "wsl -e bash runner.sh"

echo A aguardar que o servidor inicie...
timeout /t 8 /nobreak > nul

:: Abre o navegador
start "" "frontend\index.html"
exit
