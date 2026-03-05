@echo off
REM Axis Camera Batch Programmer - GUI Launcher
REM Double-click this file to start the program

cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

REM Check if dependencies are installed
python -c "import requests, psutil" >nul 2>&1
if errorlevel 1 (
    echo Installing required dependencies...
    echo.
    pip install -r requirements.txt
    echo.
)

REM Launch the GUI
echo Starting Axis Camera Batch Programmer GUI...
echo.
python axis_batch_programmer_gui.py

if errorlevel 1 (
    echo.
    echo Program exited with error. Check axis_programmer.log for details.
    pause
)
