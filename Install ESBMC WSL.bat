@echo off
title Instalador do ESBMC (WSL)
echo ==========================================
echo A preparar o ambiente e a instalar o ESBMC...
echo ==========================================
echo.
echo O Windows vai aceder ao seu WSL. Se for solicitada, digite a sua palavra-passe do Linux (Ubuntu).

wsl -e bash -c "sudo apt-get update && sudo apt-get install -y software-properties-common python3-venv python3-pip clang && echo 'A adicionar o repositorio oficial do ESBMC...' && sudo add-apt-repository -y ppa:esbmc/esbmc && sudo apt-get update && echo 'A instalar a ultima versao do ESBMC...' && sudo apt-get install -y esbmc && echo '======================================' && echo 'INSTALACAO DO ESBMC CONCLUIDA COM SUCESSO!' && echo '======================================' || echo 'Houve um erro na instalacao.'"

echo.
pause
exit
