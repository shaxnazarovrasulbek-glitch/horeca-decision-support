@echo off
REM One-click start on Windows: creates a virtual environment, installs packages, opens the app.
cd /d "%~dp0"
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
streamlit run app\Home.py
