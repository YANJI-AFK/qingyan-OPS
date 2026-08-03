@echo off
chcp 65001 >nul
cd /d "%~dp0"
title QingyanOPS - Quick Start

echo.
echo  ============================================================
echo    QingyanOPS - One-Click Quick Start
echo  ============================================================
echo.
echo    This script will:
echo      1. Check Python ^& create virtual environment
echo      2. Install backend dependencies
echo      3. Check sherpa-onnx offline TTS model
echo      4. Check Node.js ^& install frontend dependencies
echo      5. Check Ollama ^& pull model qwen3:8b
echo      6. Test model connectivity
echo      7. Check database ^& auto-restore from backup
echo      8. Start backend (port 5000) ^& frontend (port 5173)
echo.
echo  ============================================================
echo.

echo  [1/10] Checking Python ...
where python >nul 2>nul
if errorlevel 1 goto err_python
python --version 2>&1
echo.

echo  [2/10] Setting up virtual environment ...
if exist "venv\Scripts\python.exe" (
    echo         [SKIP] venv already exists.
) else (
    echo         Creating venv ...
    python -m venv venv
    if errorlevel 1 goto err_venv
    echo         [OK] venv created.
)
echo.

echo  [3/10] Installing backend dependencies ...
venv\Scripts\python.exe -m pip install -r backend\requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 goto err_pip
echo         [OK] Backend dependencies installed.
echo.

echo  [4/10] Checking sherpa-onnx offline TTS model ...
if exist "C:\sherpa-tts\sherpa-onnx-vits-zh-ll\model.onnx" (
    echo         [SKIP] TTS model already exists.
) else (
    echo         Downloading offline TTS model, about 115MB ...
    echo         URL: github.com/k2-fsa/sherpa-onnx/releases ...
    if not exist "C:\sherpa-tts" mkdir "C:\sherpa-tts"
    curl.exe -L -o "C:\sherpa-tts\sherpa-onnx-vits-zh-ll.tar.bz2" "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-vits-zh-ll.tar.bz2"
    if errorlevel 1 (
        echo         [WARN] TTS model download failed.
        echo                The app will fall back to Windows SAPI voices.
        echo                To retry, run the script again or download manually.
    ) else (
        tar -xf "C:\sherpa-tts\sherpa-onnx-vits-zh-ll.tar.bz2" -C "C:\sherpa-tts"
        del /q "C:\sherpa-tts\sherpa-onnx-vits-zh-ll.tar.bz2"
        echo         [OK] TTS model ready.
    )
)
echo.

echo  [5/10] Checking Node.js ...
where node >nul 2>nul
if errorlevel 1 goto err_node
node --version 2>&1
echo.

echo  [6/10] Installing frontend dependencies (npm install) ...
if exist "frontend\node_modules" (
    echo         [SKIP] node_modules already exists.
) else (
    echo         Running npm install - this may take a few minutes on first run ...
    pushd frontend
    call npm install
    if errorlevel 1 goto err_npm
    popd
    echo         [OK] Frontend dependencies installed.
)
echo.

echo  [7/10] Checking Ollama ...
where ollama >nul 2>nul
if errorlevel 1 goto err_ollama
echo         [OK] Ollama found.
echo.

echo  [8/10] Checking model qwen3:8b ...
ollama list 2>nul | findstr /c:"qwen3:8b" >nul
if errorlevel 1 (
    echo         Model not found. Pulling qwen3:8b ...
    echo         This may take 10-30 minutes depending on network speed.
    echo.
    ollama pull qwen3:8b
    if errorlevel 1 goto err_model
    echo         [OK] Model pulled.
) else (
    echo         [OK] Model qwen3:8b already exists.
)
echo.

echo  [9/10] Testing model connectivity ...
venv\Scripts\python.exe -c "import requests; r=requests.post('http://localhost:11434/api/generate', json={'model':'qwen3:8b','prompt':'hi','stream':False}, timeout=30); exit(0 if r.status_code==200 else 1)"
if errorlevel 1 goto err_model_test
echo         [OK] Model responds correctly.
echo.

echo  [10/10] Database setup ...
venv\Scripts\python.exe _db_setup.py
if errorlevel 1 goto err_db
echo.

echo  ============================================================
echo    All checks passed! Starting services ...
echo  ============================================================
echo.
echo    Starting backend (Flask, port 5000) ...
start "QingyanOPS-Backend" venv\Scripts\python.exe backend\app.py
echo    Starting frontend (Vite, port 5173) ...
start "QingyanOPS-Frontend" cmd /c "cd frontend && npm run dev"
echo.
echo  ============================================================
echo    Frontend : http://localhost:5173
echo    Backend  : http://localhost:5000
echo.
echo    Close the backend/frontend windows to stop services.
echo  ============================================================
echo.
pause
goto end

:err_python
echo  [ERROR] Python not found.
echo          Please install Python 3.12+ and ensure it is added to PATH.
echo          Download: https://www.python.org/downloads/
pause
exit /b 1

:err_venv
echo  [ERROR] Failed to create virtual environment.
echo          Try manually: python -m venv venv
pause
exit /b 1

:err_pip
echo  [ERROR] Failed to install backend dependencies.
echo          Try manually:
echo            venv\Scripts\activate
echo            pip install -r backend\requirements.txt
pause
exit /b 1

:err_node
echo  [ERROR] Node.js not found.
echo          Please install Node.js 22.18+ and ensure it is added to PATH.
echo          Download: https://nodejs.org/
pause
exit /b 1

:err_npm
echo  [ERROR] npm install failed.
echo          Try manually: cd frontend ^&^& npm install
pause
exit /b 1

:err_ollama
echo  [ERROR] Ollama not found.
echo          Please install Ollama from https://ollama.com
echo          After installation, make sure Ollama is running.
pause
exit /b 1

:err_model
echo  [ERROR] Failed to pull model qwen3:8b.
echo          Check network connection and try manually: ollama pull qwen3:8b
pause
exit /b 1

:err_model_test
echo  [ERROR] Model test failed.
echo          Make sure Ollama is running (start the Ollama application).
echo          Then try again.
pause
exit /b 1

:err_db
echo  [ERROR] Database setup failed.
echo          Make sure OpsCenter.bak is in the project root directory.
echo          Or restore the database manually via SSMS, then run again.
pause
exit /b 1

:end