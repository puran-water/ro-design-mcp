@echo off
echo Installing RO Design MCP Server dependencies...
echo.

REM Activate the virtual environment
call C:\Users\hvksh\mcp-servers\venv312\Scripts\activate.bat

REM Upgrade pip first
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install core dependencies
echo.
echo Installing core dependencies...
pip install fastmcp numpy papermill nbformat pydantic

REM Install WaterTAP and related dependencies
echo.
echo Installing WaterTAP dependencies (this may take a while)...
pip install watertap pyomo idaes-pse pandas matplotlib seaborn

echo.
echo Installation complete!
echo.
echo To run the server, use: python server.py
pause