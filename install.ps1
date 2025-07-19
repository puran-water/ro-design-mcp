# PowerShell installation script for RO Design MCP Server

Write-Host "Installing RO Design MCP Server dependencies..." -ForegroundColor Green
Write-Host ""

# Check for environment variable or use default
$venvPath = if ($env:VENV_PATH) { $env:VENV_PATH } else { "C:\Users\hvksh\mcp-servers\venv312" }

# Activate the virtual environment
Write-Host "Activating virtual environment: $venvPath" -ForegroundColor Yellow
& "$venvPath\Scripts\Activate.ps1"

# Upgrade pip first
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install from requirements.txt
Write-Host ""
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt

# Download IDAES extensions (required for solvers)
Write-Host ""
Write-Host "Downloading IDAES extensions (solvers)..." -ForegroundColor Yellow
idaes get-extensions

Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Copy .env.example to .env and update with your paths"
Write-Host "2. Run the server with: python server.py"