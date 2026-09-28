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

echo A abrir interface ESBMC-Web (o painel monitorizara o arranque do servidor em tempo real)...
timeout /t 1 /nobreak > nul

:: Abre o navegador imediatamente com a tela de inicializacao inteligente
start "" "frontend\index.html"
exit
