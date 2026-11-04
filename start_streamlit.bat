@echo off
chcp 65001 >nul
title LibreWarp - Streamlit
cd /d "%~dp0"

rem ---- crear o reutilizar el entorno virtual ----
rem Siempre se trabaja sobre .venv (aislado del Python del sistema). Si ya existe
rem y funciona se reutiliza tal cual; si no, se crea aqui mismo.
set PY=
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 set PY=".venv\Scripts\python.exe"
)
if not defined PY (
    echo [INFO] Creando entorno virtual .venv...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo [ERROR] No se encontro Python funcional. Instala Python 3.10-3.13 desde python.org
        pause
        exit /b 1
    )
    set PY=".venv\Scripts\python.exe"
)

rem ---- instalar dependencias solo si faltan ----
rem Con el venv ya preparado esto no hace nada y el arranque es inmediato.
%PY% -c "import streamlit, cv2, numpy, scipy" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Instalando dependencias de requirements.txt...
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo la instalacion de dependencias. Revisa el mensaje de arriba.
        pause
        exit /b 1
    )
)

rem ---- salida UTF-8 en consola (evita cp1252 con tildes y emojis del wizard) ----
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem ---- lanzar el wizard ----
rem Streamlit abre el navegador por su cuenta y por defecto sirve en el puerto 8501.
echo [INFO] Iniciando LibreWarp... se abrira el navegador en http://localhost:8501
echo [INFO] Para detenerlo pulsa Ctrl+C en esta ventana.
echo.
%PY% -m streamlit run wizard.py
if errorlevel 1 (
    echo.
    echo [ERROR] Streamlit termino con error. Revisa el mensaje de arriba.
    pause
)
