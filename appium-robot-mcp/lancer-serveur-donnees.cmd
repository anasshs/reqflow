@echo off
rem Serveur de donnees de l'atelier (base partagee entre postes). Bibliotheque standard de Python seulement.
rem   lancer-serveur-donnees.cmd --base D:\atelier\atelier.db --hote 0.0.0.0 --port 8443 --cert serveur.pem --cle serveur.key
rem HTTPS obligatoire hors de la machine (voir docs\BASE_ATELIER.md).
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYCMD="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo   Python 3.10 ou plus recent est introuvable : l'installer, puis relancer.
  pause
  exit /b 1
)
%PYCMD% serveur_donnees.py %*
if errorlevel 1 pause
endlocal
