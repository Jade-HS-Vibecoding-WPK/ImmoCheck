@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.9 oder neuer wird gebraucht: https://www.python.org/downloads/ ^(Haken "Add python.exe to PATH" setzen^) & pause & exit /b 1)
if not exist .venv (
  echo Erste Einrichtung, das dauert einige Minuten ...
  python -m venv .venv
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
.venv\Scripts\streamlit run app.py
pause
