@echo off
rem Atelier : assistant d'installation et de lancement (Windows). Double-clic, ou « lancer-atelier.cmd » dans un terminal.
rem Trouve Python 3.10+ (py, puis python) ; s'il manque, propose de l'installer (winget), puis lance lanceur.py qui
rem prepare le poste (.venv, dependances, navigateur, projet de tests) et demarre l'atelier.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PYCMD="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PYCMD=python"
)
if defined PYCMD goto lancer

echo.
echo   Python 3.10 ou plus recent est introuvable sur ce poste.
where winget >nul 2>nul
if errorlevel 1 goto manuel
choice /C ON /M "  Installer Python 3.13 maintenant (winget, pour l'utilisateur courant)"
if errorlevel 2 goto manuel
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manuel
echo.
echo   Python est installe. Fermer cette fenetre, puis relancer lancer-atelier.cmd.
pause
exit /b 0

:manuel
echo.
echo   Installer Python depuis https://www.python.org/downloads/windows/
echo   (cocher « Add python.exe to PATH »), puis relancer lancer-atelier.cmd.
start "" https://www.python.org/downloads/windows/
pause
exit /b 1

:lancer
%PYCMD% lanceur.py %*
if errorlevel 1 pause
endlocal
