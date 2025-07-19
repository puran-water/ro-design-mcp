@echo off
REM Batch installation script for RO Design MCP Server

echo Installing RO Design MCP Server dependencies...
echo.

REM Check for environment variable or use default
if "%VENV_PATH%"=="" (
    set VENV_PATH=C:\Users\hvksh\mcp-servers\venv312
)

REM Activate the virtual environment
echo Activating virtual environment: %VENV_PATH%
call %VENV_PATH%\Scripts\activate.bat

REM Upgrade pip first
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install from requirements.txt
echo.
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt

REM Download IDAES extensions (required for solvers)
echo.
echo Downloading IDAES extensions (solvers)...
idaes get-extensions

echo.
echo Installation complete!
echo.
echo Next steps:
echo 1. Copy .env.example to .env and update with your paths
echo 2. Run the server with: python server.py
pause