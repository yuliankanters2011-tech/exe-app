@echo off
chcp 65001 >nul
echo ============================================
echo  SchijfOpschoner - Bouwen naar .exe
echo ============================================
echo.

:: Controleer Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [FOUT] Python niet gevonden!
    echo.
    echo Installeer Python van https://www.python.org/downloads/
    echo BELANGRIJK: vink "Add python.exe to PATH" aan tijdens installatie!
    echo.
    pause
    exit /b 1
)

echo [1/3] PyInstaller installeren...
pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [FOUT] PyInstaller installatie mislukt.
    pause
    exit /b 1
)

echo.
echo [2/3] Bouwen naar SchijfOpschoner.exe ...
pyinstaller --onefile --windowed --name SchijfOpschoner --clean app.py
if errorlevel 1 (
    echo [FOUT] Bouwen mislukt.
    pause
    exit /b 1
)

echo.
echo [3/3] Klaar!
echo.
echo  Je .exe staat in:  dist\SchijfOpschoner.exe
echo  Kopieer die naar je Desktop en dubbelklik om te starten.
echo  (Geen installatie nodig - het is een draagbaar programma.)
echo.
pause
