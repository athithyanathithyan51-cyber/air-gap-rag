# Start the offline assistant on this Windows laptop after a reboot or shutdown.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start-demo-windows.ps1
#
# Starts, in order: Docker Desktop (Qdrant restarts with it), Ollama (the local LLM),
# then the app on 127.0.0.1:8000. Development only. Turn Wi-Fi off after the script
# reports READY to demonstrate isolation.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$dockerApp = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
$python = Join-Path $HOME ".local\micromamba\root\envs\airgap\python.exe"

function Wait-Until($label, $test, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (& $test) { Write-Host "  $label ready"; return }
        Start-Sleep -Seconds 1
    }
    throw "$label did not become ready within $seconds seconds"
}

# 1. Docker Desktop and Qdrant
& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Starting Docker Desktop..."
    Start-Process -FilePath $dockerApp
    Wait-Until "Docker engine" { & $docker info *> $null; $LASTEXITCODE -eq 0 } 240
}
Write-Host "Starting Qdrant..."
& $docker start airgap-dev-qdrant-1 *> $null
Wait-Until "Qdrant" { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:6333/readyz").StatusCode -eq 200 } catch { $false } } 60

# 2. Ollama (local LLM server)
if (-not (Get-Process -Name "ollama" -ErrorAction SilentlyContinue)) {
    Write-Host "Starting Ollama..."
    Start-Process -FilePath $ollamaApp
}
Wait-Until "Ollama" { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:11434/api/version").StatusCode -eq 200 } catch { $false } } 60

# 3. App, in its own window so its logs stay visible
$env:PYTHONPATH = "backend"
$env:AIRGAP_ENVIRONMENT = "development"
$env:AIRGAP_ISOLATION_ALLOW = '["docker0","br-*","vEthernet (WSL*"]'
Write-Host "Starting the app..."
Start-Process -FilePath $python -ArgumentList "-m", "app.main" -WorkingDirectory (Get-Location) -WindowStyle Minimized
Wait-Until "App" { try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:8000/ready").StatusCode -eq 200 } catch { $false } } 120

Write-Host ""
Write-Host "READY: open http://127.0.0.1:8000/ in your browser."
Write-Host "Turn off Wi-Fi now to demonstrate offline operation."
