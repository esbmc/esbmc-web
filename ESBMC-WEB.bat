@echo off
title ESBMC-Web Launcher
echo ==========================================
echo Starting ESBMC-Web...
echo ==========================================

:: Make sure Windows uses the current folder
cd /d "%~dp0"

:: Strip Windows line endings (CRLF to LF), which break the scripts on Linux
wsl -e bash -c "sed -i 's/\r$//' runner.sh"
wsl -e bash -c "sed -i 's/\r$//' backend/requirements.txt"

:: Run the Linux script and keep the window open
start "Backend ESBMC-Web" cmd /k "wsl -e bash runner.sh"

echo Waiting for the backend server to start...
timeout /t 5 /nobreak > nul

:: Open the web interface in the default browser
start "" "frontend\index.html"
exit
