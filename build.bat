@echo off
REM ================================================================
REM Build script para Ping Wheel v1.1
REM Genera dist\PingWheel.exe portable
REM ================================================================

setlocal enabledelayedexpansion

echo.
echo ====== Ping Wheel - Build script ======
echo.

REM ----- Detectar comando de Python disponible -----
set PYTHON_CMD=
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python
    goto :python_found
)
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=py
    goto :python_found
)
where python3 >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python3
    goto :python_found
)

echo [X] No se encontro Python instalado.
echo Instala Python desde https://www.python.org/downloads/
pause
exit /b 1

:python_found
echo Usando: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

REM ----- Actualizar pip -----
echo Actualizando pip...
%PYTHON_CMD% -m pip install --upgrade pip --quiet
echo.

REM ----- Instalar dependencias de runtime -----
echo Instalando PySide6 y pynput...
%PYTHON_CMD% -m pip install --upgrade PySide6 pynput
if %ERRORLEVEL% neq 0 (
    echo [X] Error instalando PySide6 o pynput.
    pause
    exit /b 1
)
echo.

REM ----- Instalar herramientas de build -----
echo Instalando PyInstaller y Pillow...
%PYTHON_CMD% -m pip install --upgrade pyinstaller Pillow
if %ERRORLEVEL% neq 0 (
    echo [X] Error instalando PyInstaller o Pillow.
    pause
    exit /b 1
)
echo.

REM ----- Limpiar builds anteriores -----
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist PingWheel.spec del /q PingWheel.spec

REM ----- Verificar archivos necesarios -----
if not exist ping_wheel.py (
    echo [X] No se encuentra ping_wheel.py en la carpeta actual.
    pause
    exit /b 1
)
if not exist icons (
    echo [X] No se encuentra la carpeta icons.
    pause
    exit /b 1
)

REM Sounds es opcional: si no existe, advertir pero seguir
set SOUNDS_ARG=
if exist sounds (
    set SOUNDS_ARG=--add-data "sounds;sounds"
    echo Carpeta sounds detectada, sera incluida en el .exe.
) else (
    echo [!] Carpeta sounds no encontrada. El .exe se compilara sin sonidos.
)

REM Icono opcional
set ICON_ARG=
if exist icons\Caution_ping.png (
    set ICON_ARG=--icon=icons\Caution_ping.png
)

echo.
echo Compilando .exe ^(esto tarda 1-3 minutos^)...
echo.

%PYTHON_CMD% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --add-data "icons;icons" ^
    %SOUNDS_ARG% ^
    %ICON_ARG% ^
    --name PingWheel ^
    ping_wheel.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [X] Build fallo. Mira el log arriba para mas detalles.
    pause
    exit /b 1
)

echo.
echo ====== Build completo ======
echo.
echo El ejecutable esta en: dist\PingWheel.exe
echo.
pause
