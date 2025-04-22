@echo off
echo ============================
echo  Starting CodePortal Server
echo ============================

:: Create virtual environment if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Install requirements
pip install -r requirements.txt

:: Start the server
python code_portal_mcp.py

pause