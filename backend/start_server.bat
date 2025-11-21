@echo off
echo Starting DocFox Backend Server...

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start the server
echo Server starting at http://localhost:8000
echo API documentation available at http://localhost:8000/docs
echo.
python main.py
