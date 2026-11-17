@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Instalador da ATHENA

echo.
echo   ============================================
echo      ATHENA - instalador
echo   ============================================
echo.

REM ---------- 1. Python ----------
set "PY="
where py >nul 2>nul && (
    py -3.12 -V >nul 2>nul && set "PY=py -3.12"
    if not defined PY py -3.11 -V >nul 2>nul && set "PY=py -3.11"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [!] Python nao encontrado.
    echo     Instale o Python 3.12 em https://www.python.org/downloads/
    echo     IMPORTANTE: marque a opcao "Add python.exe to PATH" na instalacao.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] Usando: %PY%

REM ---------- 2. Ambiente virtual + bibliotecas ----------
if not exist ".venv\Scripts\python.exe" (
    echo [2/5] Criando ambiente virtual...
    %PY% -m venv .venv || (echo [!] Falha ao criar o ambiente & pause & exit /b 1)
)
echo [2/5] Instalando bibliotecas (pode demorar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] Erro instalando as bibliotecas. Veja a mensagem acima.
    pause
    exit /b 1
)

REM ---------- 3. Detector da palavra "Atena" (Vosk) ----------
if not exist "modelos\vosk-pt" (
    echo [3/5] Baixando o detector da palavra "Atena" ^(~30 MB^)...
    if not exist modelos mkdir modelos
    powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip' -OutFile 'modelos\vosk.zip'; Expand-Archive 'modelos\vosk.zip' -DestinationPath 'modelos' -Force; Remove-Item 'modelos\vosk.zip'; Rename-Item 'modelos\vosk-model-small-pt-0.3' 'vosk-pt'"
    if not exist "modelos\vosk-pt" echo [!] Nao consegui baixar. A ATHENA funciona mesmo assim, so gasta mais CPU ouvindo.
) else (
    echo [3/5] Detector da palavra "Atena" ja instalado.
)

REM ---------- 4. Ollama (cerebro) ----------
where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo [4/5] O Ollama ^(cerebro da ATHENA^) nao esta instalado.
    where winget >nul 2>nul && (
        choice /c SN /m "      Instalar agora pelo winget"
        if !errorlevel! equ 1 winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
    )
    where ollama >nul 2>nul || (
        echo       Baixe em https://ollama.com/download , instale e rode este instalador de novo.
        start https://ollama.com/download
        pause
        exit /b 0
    )
)
echo.
echo [4/5] Qual modelo de IA baixar? (ele pensa E enxerga a tela)
echo       1 = qwen3-vl:8b  ^(recomendado: placa de video com 10 GB ou mais, ~6 GB de download^)
echo       2 = qwen3-vl:4b  ^(placa com 6-8 GB, ~3.3 GB^)
echo       3 = qwen3-vl:2b  ^(placa fraca ou sem placa, ~2 GB^)
echo       4 = pular
choice /c 1234 /m "      Escolha"
set "MODELO="
if %errorlevel% equ 1 set "MODELO=qwen3-vl:8b"
if %errorlevel% equ 2 set "MODELO=qwen3-vl:4b"
if %errorlevel% equ 3 set "MODELO=qwen3-vl:2b"
if defined MODELO (
    ollama pull %MODELO%
    ".venv\Scripts\python.exe" -c "from athena.config import Config; Config().salvar_geral({'cerebro': {'modelo': '%MODELO%'}, 'visao': {'modelo': '%MODELO%'}})"
)

REM ---------- Extra: sensores de temperatura ----------
echo.
echo [+] Monitor do PC: temperaturas, clocks e ventoinhas usam o LibreHardwareMonitor (gratis).
where winget >nul 2>nul && (
    choice /c SN /m "      Instalar o LibreHardwareMonitor"
    if !errorlevel! equ 1 (
        winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor --accept-package-agreements --accept-source-agreements
        echo       Depois abra ele como administrador e ligue: Options ^> Remote Web Server ^> Run
    )
)

REM ---------- 5. Atalhos ----------
echo.
echo [5/5] Criando atalho na Area de Trabalho...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\ATHENA.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0main.py\"'; $s.WorkingDirectory='%~dp0'; $s.Description='ATHENA'; $s.Save()"
choice /c SN /m "      Abrir a ATHENA junto com o Windows"
if %errorlevel% equ 1 (
    powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\ATHENA.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='\"%~dp0main.py\"'; $s.WorkingDirectory='%~dp0'; $s.Save()"
)

echo.
echo   ============================================
echo      Pronto! Abra a ATHENA pelo atalho na
echo      Area de Trabalho ou pelo iniciar.bat
echo   ============================================
echo.
choice /c SN /m "Abrir agora"
if %errorlevel% equ 1 start "" ".venv\Scripts\pythonw.exe" main.py
endlocal
