@echo off
REM start_dashboard.bat - Lance le dashboard EDI (et son watcher intégré)
REM
REM Utilisation manuelle : double-clique sur ce fichier.
REM Utilisation automatique : voir deploy\README_WINDOWS.md pour le
REM configurer comme tâche de démarrage Windows (redémarre tout seul
REM après une coupure de courant / un redémarrage du PC).

cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
    echo [ERREUR] Environnement virtuel introuvable. Lancez d'abord :
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Boucle infinie : si Streamlit plante ou si Windows le tue au moment
REM d'une coupure de courant, il redémarre tout seul 5 secondes après.
REM Pas besoin de compter sur le Planificateur de tâches pour ça.
:loop
streamlit run app.py
echo.
echo [%date% %time%] Le dashboard s'est arrêté, redémarrage dans 5 secondes...
timeout /t 5 /nobreak >nul
goto loop

