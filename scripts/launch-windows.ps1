# One-click launcher for the offline assistant on the Windows demo laptop.
#
#   powershell -ExecutionPolicy Bypass -File scripts\launch-windows.ps1
#
# Starts Docker Desktop, the Ollama container (GPU), Qdrant and the app if they are not
# already running, then opens the app in its own browser window. Development only.
# Uses the Docker Ollama container, so it stops the native Windows Ollama app first:
# that app holds port 11434 and blocks the GPU container.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$dockerApp = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$python = Join-Path $HOME ".local\micromamba\root\envs\airgap\python.exe"
$compose = "deploy\docker-compose.dev.yml"
$url = "http://127.0.0.1:8000/"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"

function Wait-Until($label, $test, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (& $test) { Write-Host "  $label ready"; return }
        Start-Sleep -Seconds 1
    }
    throw "$label did not become ready within $seconds seconds"
}
function Test-Http($uri) {
    try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $uri).StatusCode -eq 200 } catch { $false }
}

# 1. Docker Desktop
& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting Docker Desktop..."
    Start-Process -FilePath $dockerApp
    Wait-Until "Docker engine" { & $docker info *> $null; $LASTEXITCODE -eq 0 } 240
}

# 2. Native Ollama would block the GPU container on port 11434
Get-Process -Name "ollama app", "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force

# 3. Qdrant and Ollama (GPU) containers
Write-Host "Starting Qdrant and Ollama containers..."
& $docker compose -f $compose up -d | Out-Null
Wait-Until "Qdrant" { Test-Http "http://127.0.0.1:6333/readyz" } 60
Wait-Until "Ollama" { Test-Http "http://127.0.0.1:11434/api/version" } 60

# 4. App
if (-not (Test-Http "http://127.0.0.1:8000/health")) {
    Write-Host "Starting the app..."
    $env:PYTHONPATH = "backend"
    $env:AIRGAP_ENVIRONMENT = "development"
    $env:AIRGAP_ISOLATION_ALLOW = '["docker0","br-*","vEthernet (WSL*"]'
    Start-Process -FilePath $python -ArgumentList "-m", "app.main" -WorkingDirectory (Get-Location) -WindowStyle Minimized
}
Wait-Until "App" { Test-Http "http://127.0.0.1:8000/ready" } 120

# 5. Open in its own window, like an app
$browser = if (Test-Path $edge) { $edge } elseif (Test-Path $chrome) { $chrome } else { $null }
if ($browser) {
    Start-Process -FilePath $browser -ArgumentList "--app=$url"
} else {
    Start-Process $url
}
Write-Host ""
Write-Host "READY: the assistant is open at $url"
