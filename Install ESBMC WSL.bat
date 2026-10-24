@echo off
title ESBMC Installer (WSL)
echo ==========================================
echo Preparing the environment and installing ESBMC...
echo ==========================================
echo.
echo Windows will now access your WSL. If prompted, enter your Linux (Ubuntu) password.

wsl -e bash -c "sudo apt-get update && sudo apt-get install -y software-properties-common python3-venv python3-pip clang && echo 'Adding the official ESBMC repository...' && sudo add-apt-repository -y ppa:esbmc/esbmc && sudo apt-get update && echo 'Installing the latest ESBMC version...' && sudo apt-get install -y esbmc && echo '======================================' && echo 'ESBMC INSTALLATION COMPLETED SUCCESSFULLY!' && echo '======================================' || echo 'The installation failed.'"

echo.
pause
exit
