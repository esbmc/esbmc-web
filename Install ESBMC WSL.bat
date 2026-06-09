@echo off
title Instalador do ESBMC (WSL)
echo ==========================================
echo Preparando o ambiente e baixando o ESBMC...
echo ==========================================
echo.
echo O Windows vai acessar o seu WSL. Se pedir senha, digite a sua senha do Linux (Ubuntu).

wsl -e bash -c "sudo apt-get update && sudo apt-get install -y wget unzip python3-venv python3-pip clang && echo 'Baixando ESBMC do GitHub...' && wget -qO esbmc.zip https://github.com/esbmc/esbmc/releases/download/v7.4.0/ESBMC-Linux.zip && echo 'Extraindo...' && sudo unzip -o esbmc.zip -d /usr/local/bin/esbmc-folder && sudo ln -sf /usr/local/bin/esbmc-folder/bin/esbmc /usr/local/bin/esbmc && rm esbmc.zip && echo '======================================' && echo 'INSTALACAO DO ESBMC CONCLUIDA COM SUCESSO!' && echo '======================================' || echo 'Houve um erro na instalacao.'"

echo.
pause
exit
