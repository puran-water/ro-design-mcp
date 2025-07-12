# PowerShell installation script for RO Design MCP Server

Write-Host "Installing RO Design MCP Server dependencies..." -ForegroundColor Green
Write-Host ""

# Activate the virtual environment
& "C:\Users\hvksh\mcp-servers\venv312\Scripts\Activate.ps1"

# Upgrade pip first
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install core dependencies
Write-Host ""
Write-Host "Installing core dependencies..." -ForegroundColor Yellow
pip install fastmcp numpy papermill nbformat pydantic

# Install WaterTAP and related dependencies
Write-Host ""
Write-Host "Installing WaterTAP dependencies (this may take a while)..." -ForegroundColor Yellow
pip install watertap pyomo idaes-pse pandas matplotlib seaborn

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To run the server, use: python server.py" -ForegroundColor Cyan