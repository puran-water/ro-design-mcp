# PowerShell script to run the multi-configuration economic test
# This script activates the virtual environment and runs the test

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Running Multi-Configuration Economic Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Navigate to the project directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& "..\venv312\Scripts\Activate.ps1"

# Run the test
Write-Host "`nRunning economic analysis test..." -ForegroundColor Yellow
python test_multi_config_economics.py

# Check exit code
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nTest completed successfully!" -ForegroundColor Green
} else {
    Write-Host "`nTest failed with exit code: $LASTEXITCODE" -ForegroundColor Red
}

Write-Host "`nPress any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")