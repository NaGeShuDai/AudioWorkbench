@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto :setup
".venv\Scripts\python.exe" -c "import PySide6, numpy, scipy, soundfile, noisereduce, imageio_ffmpeg" >nul 2>nul
if errorlevel 1 goto :setup
goto :launch
:setup
  echo First launch: installing the local runtime...
  where uv >nul 2>nul
  if errorlevel 1 (
    echo uv is required. Install it from https://docs.astral.sh/uv/ and try again.
    pause
    exit /b 1
  )
  uv venv --allow-existing --python 3.11 .venv
  if errorlevel 1 goto :failed
  uv pip install --python .venv\Scripts\python.exe -r requirements.lock.txt
  if errorlevel 1 goto :failed
:launch
start "" ".venv\Scripts\pythonw.exe" "main.py"
exit /b 0
:failed
echo Setup failed. Please read the error above.
pause
exit /b 1
