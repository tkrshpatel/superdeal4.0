param([Parameter(Mandatory=$true)][ValidateSet('api','frontend','worker','tunnel','ollama','notifications')][string]$Service)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$Host.UI.RawUI.WindowTitle = "SuperDeals - $Service"
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'start_pipeline.py') --service $Service
$serviceExit = $LASTEXITCODE
Write-Host "Service stopped (exit $serviceExit). Keep the error above for diagnosis." -ForegroundColor Yellow
Read-Host 'Press Enter to close this service window'
