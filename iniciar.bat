@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo A ATHENA ainda nao foi instalada. Rodando o instalador...
    call instalar.bat
    exit /b
)
REM Use "iniciar.bat debug" pra ver as mensagens (abre com janela de terminal)
if /i "%1"=="debug" (
    ".venv\Scripts\python.exe" main.py
    pause
) else (
    start "" ".venv\Scripts\pythonw.exe" main.py
)
