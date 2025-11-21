@echo off
echo Setting up DocFox Backend...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install requirements
echo Installing requirements...
pip install -r requirements.txt

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo Creating .env file from template...
    copy .env.example .env
    echo Please edit .env file with your configuration
)

REM Create uploads directory
if not exist "uploads" (
    mkdir uploads
)

echo Setup complete!
echo.
echo To start the server, run:
echo   venv\Scripts\activate.bat
echo   python main.py
echo.
echo Or simply run: start_server.bat
pause
