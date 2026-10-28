$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$launcher = Join-Path $PSScriptRoot 'start_pipeline.py'
$secret = $null
$result = 1
try {
    if (-not (Test-Path -LiteralPath $python)) { throw 'The staging Python environment is missing.' }
    Set-Location -LiteralPath $projectRoot
    & $python $launcher --check
    if ($LASTEXITCODE -ne 0) { throw 'Fix the prerequisite check above before starting.' }
    & $python $launcher --worker-running
    if ($LASTEXITCODE -ne 0) {
        $secret = Read-Host 'Saved WORKER MongoDB password (not administrator)' -AsSecureString
        $env:SUPERDEAL_LAUNCH_WORKER_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
    }
    & $python $launcher
    $result = $LASTEXITCODE
}
catch {
    Write-Host 'SuperDeals startup stopped. Check the message above.' -ForegroundColor Red
    if (-not (Test-Path -LiteralPath $python)) { Write-Host 'Missing .venv\Scripts\python.exe' }
}
finally {
    Remove-Item Env:\SUPERDEAL_LAUNCH_WORKER_PASSWORD -ErrorAction SilentlyContinue
    if ($null -ne $secret) { $secret.Dispose() }
}
Read-Host 'Press Enter to close this launcher; service windows stay open'
exit $result
