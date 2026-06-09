@echo off
title Inicializador ESBMC-Web
echo ==========================================
echo Iniciando o ESBMC-Web...
echo ==========================================

:: Garante que o terminal do Windows reconheça a pasta atual
cd /d "%~dp0"

:: Corrige quebras de linha invisíveis do Windows no script de inicialização Linux (CRLF para LF)
wsl -e bash -c "sed -i 's/\r$//' runner.sh"

:: Executa o runner.sh de forma isolada dentro do WSL
start "Backend ESBMC-Web" cmd /k "wsl -e bash runner.sh"

echo Aguardando o servidor subir...
timeout /t 8 /nobreak > nul

:: Abre a interface gráfica no navegador padrão
start "" "frontend\index.html"
exit
