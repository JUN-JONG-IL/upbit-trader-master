@echo off
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "PYEXE=C:\Users\jji24\anaconda3\envs\py311\python.exe"
echo ==== DEBUG RUN START ==== > "%~dp0exporter_debug.log"
echo DATE: %DATE% %TIME% >> "%~dp0exporter_debug.log"
echo USER: %USERNAME% >> "%~dp0exporter_debug.log"
echo CD: %CD% >> "%~dp0exporter_debug.log"
echo SCRIPT_DIR: %SCRIPT_DIR% >> "%~dp0exporter_debug.log"
echo REPO_ROOT: %REPO_ROOT% >> "%~dp0exporter_debug.log"
echo PYEXE: %PYEXE% >> "%~dp0exporter_debug.log"
echo CMD: "%PYEXE%" "%REPO_ROOT%\tools\prometheus_exporter.py" >> "%~dp0exporter_debug.log"
if exist "%REPO_ROOT%\tools\prometheus_exporter.py" ( echo script exists >> "%~dp0exporter_debug.log" ) else ( echo script missing "%REPO_ROOT%\tools\prometheus_exporter.py" >> "%~dp0exporter_debug.log" )
"%PYEXE%" "%REPO_ROOT%\tools\prometheus_exporter.py" >> "%~dp0exporter_debug.log" 2>&1
echo ==== DEBUG RUN END ==== >> "%~dp0exporter_debug.log"
