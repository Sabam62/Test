@echo off
setlocal EnableExtensions
title Atlantic Biochar
cd /d "%~dp0"

echo Atlantic Biochar - demarrage
echo.

set "CONDA_CMD="
for /f "delims=" %%C in ('where conda 2^>nul') do if not defined CONDA_CMD set "CONDA_CMD=%%C"

if not defined CONDA_CMD for %%P in (
  "%USERPROFILE%\miniforge3\condabin\conda.bat"
  "%USERPROFILE%\miniconda3\condabin\conda.bat"
  "%LOCALAPPDATA%\miniforge3\condabin\conda.bat"
  "C:\miniforge3\condabin\conda.bat"
  "C:\miniconda3\condabin\conda.bat"
  "C:\ProgramData\Miniforge3\condabin\conda.bat"
) do if not defined CONDA_CMD if exist "%%~P" set "CONDA_CMD=%%~P"

if not defined CONDA_CMD goto manque_conda

echo Verification de l'environnement Python...
call "%CONDA_CMD%" run -n ab-dss python -c "import fastapi, geopandas, bw2data, bw2calc" >nul 2>&1
if errorlevel 1 (
  echo Creation ou mise a jour de l'environnement. Cette etape peut prendre 10 a 20 minutes...
  call "%CONDA_CMD%" env update -n ab-dss -f "%~dp0environment.yml"
  if errorlevel 1 (
    call "%CONDA_CMD%" env create -f "%~dp0environment.yml"
    if errorlevel 1 goto erreur_environnement
  )
)

if not exist "%~dp0data\processed\rapport_controle.html" (
  echo Premiere preparation des donnees. Environ 1,1 Go seront telecharges...
  echo Cette etape peut durer plusieurs minutes. Laissez cette fenetre ouverte.
  call "%CONDA_CMD%" run --no-capture-output -n ab-dss python -m scripts.download
  if errorlevel 1 echo Certaines sources n'ont pas ete telechargees ; la preparation va verifier les fichiers requis.
  call "%CONDA_CMD%" run --no-capture-output -n ab-dss python -m scripts.prepare
  if errorlevel 1 goto erreur_donnees
)

echo Ouverture de l'application dans le navigateur...
call "%CONDA_CMD%" run --no-capture-output -n ab-dss python -m ab_dss
if errorlevel 1 goto erreur_lancement
goto fin

:manque_conda
echo Miniforge est introuvable.
echo Installez Miniforge depuis https://github.com/conda-forge/miniforge, puis relancez ce fichier.
goto erreur

:erreur_environnement
echo Impossible de creer l'environnement ab-dss. Verifiez Internet et relancez ce fichier.
goto erreur

:erreur_donnees
echo La preparation des donnees a echoue. Consultez le message ci-dessus et docs\donnees_manuelles.md.
goto erreur

:erreur_lancement
echo L'application s'est arretee avec une erreur. Consultez le message ci-dessus.
goto erreur

:erreur
echo.
pause
exit /b 1

:fin
endlocal
