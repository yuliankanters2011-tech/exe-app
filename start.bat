@echo off
chcp 65001 >nul
title SchijfOpschoner

python --version >nul 2>&1
if errorlevel 1 (
    echo [FOUT] Python niet gevonden!
    echo.
    echo Installeer Python van https://www.python.org/downloads/
    echo Vink "Add python.exe to PATH" aan tijdens de installatie.
    echo.
    pause
    exit /b 1
)

echo SchijfOpschoner starten...
python app.py
pause
