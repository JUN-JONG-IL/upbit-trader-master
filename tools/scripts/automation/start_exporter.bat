@echo off
REM store script directory (%~dp0 ends with \)
set "SCRIPT_DIR=%~dp0"
REM compute repo root (absolute path)
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

REM absolute python executable path
set "PYEXE=C:\Users\jji24\anaconda3\envs\py311\python.exe"

REM change working directory to repo root
pushd "%REPO_ROOT%"

REM environment variables
set "PYTHONPATH=%REPO_ROOT%"
set "SNAPSHOT_TARGETS=KRW-TEST:1m,KRW-BTC:1m"
set "SCRAPE_INTERVAL_SECONDS=15"

REM log file in scheduler folder (append)
set "LOGFILE=%~dp0exporter.log"
"%PYEXE%" "%REPO_ROOT%\tools\prometheus_exporter.py" >> "%LOGFILE%" 2>&1

popd
