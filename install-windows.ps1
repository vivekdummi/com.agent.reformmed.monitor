# REFORMMED Monitor — Windows Agent Installer
# Run in PowerShell as Administrator OR from cmd:
# powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-windows.ps1 | iex"

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$INSTALL_DIR = "C:\reformmed-agent"
$SERVICE_NAME = "ReformmedMonitorAgent"
$REPO_RAW = "https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     REFORMMED Monitor — Agent Setup          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$VM_IP       = Read-Host "VM Server IP (e.g. 164.52.221.241)"
$VM_PORT     = Read-Host "VM Server port [8000]"
if (-not $VM_PORT) { $VM_PORT = "8000" }
$API_KEY     = Read-Host "API Secret Key"
$SYSTEM_NAME = Read-Host "This machine name (e.g. Office-PC1)"
$LOCATION    = Read-Host "This machine location (e.g. Delhi)"
$INTERVAL    = Read-Host "Send interval in seconds [1]"
if (-not $INTERVAL) { $INTERVAL = "1" }

$SERVER_URL = "http://${VM_IP}:${VM_PORT}"

Write-Host ""
Write-Host "Server : $SERVER_URL" -ForegroundColor Blue
Write-Host "Name   : $SYSTEM_NAME" -ForegroundColor Blue
Write-Host "Loc    : $LOCATION" -ForegroundColor Blue
$confirm = Read-Host "Install? [y/N]"
if ($confirm -ne "y" -and $confirm -ne "Y") { Write-Host "Cancelled."; exit 0 }

# ── Step 1: Find Python ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "[1/5] Checking Python..." -ForegroundColor Blue
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python 3") { $python = $cmd; break }
    } catch {}
}
if (-not $python) {
    Write-Host "Python not found. Installing via winget..." -ForegroundColor Yellow
    try {
        winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
        $python = "python"
    } catch {
        Write-Host "Please install Python 3 from https://python.org and re-run" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  Python found: $python" -ForegroundColor Green

# ── Step 2: Create directory ──────────────────────────────────────────────────
Write-Host "[2/5] Creating install directory..." -ForegroundColor Blue
if (Test-Path $INSTALL_DIR) {
    Remove-Item -Recurse -Force $INSTALL_DIR
}
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

# ── Step 3: Download agent ────────────────────────────────────────────────────
Write-Host "[3/5] Downloading agent..." -ForegroundColor Blue
Invoke-WebRequest -Uri "$REPO_RAW/agent.py"        -OutFile "$INSTALL_DIR\agent.py"
Invoke-WebRequest -Uri "$REPO_RAW/requirements.txt" -OutFile "$INSTALL_DIR\requirements.txt"

# ── Step 4: Install dependencies ─────────────────────────────────────────────
Write-Host "[4/5] Installing dependencies..." -ForegroundColor Blue

# Create venv to avoid permission issues
& $python -m venv "$INSTALL_DIR\venv" 2>&1 | Out-Null
$pip    = "$INSTALL_DIR\venv\Scripts\pip.exe"
$pypython = "$INSTALL_DIR\venv\Scripts\python.exe"

& $pip install --quiet --upgrade pip 2>&1 | Out-Null
& $pip install --quiet psutil requests pynvml 2>&1 | Out-Null
Write-Host "  Dependencies installed" -ForegroundColor Green

# ── Step 5: Write config and create startup task ──────────────────────────────
Write-Host "[5/5] Configuring auto-start..." -ForegroundColor Blue

# Write .env config
@"
REFORMMED_SERVER_URL=$SERVER_URL
REFORMMED_API_KEY=$API_KEY
REFORMMED_SYSTEM_NAME=$SYSTEM_NAME
REFORMMED_LOCATION=$LOCATION
REFORMMED_INTERVAL=$INTERVAL
"@ | Out-File -FilePath "$INSTALL_DIR\.env" -Encoding ASCII

# Write launcher script that loads env vars
@"
import os, subprocess, sys

env_file = r"$INSTALL_DIR\.env"
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()

agent = r"$INSTALL_DIR\agent.py"
subprocess.run([sys.executable, agent])
"@ | Out-File -FilePath "$INSTALL_DIR\launcher.py" -Encoding ASCII

# Remove old task if exists
Unregister-ScheduledTask -TaskName $SERVICE_NAME -Confirm:$false -ErrorAction SilentlyContinue

# Create Task Scheduler entry — runs at startup, restarts on failure
$action   = New-ScheduledTaskAction `
    -Execute $pypython `
    -Argument "`"$INSTALL_DIR\launcher.py`"" `
    -WorkingDirectory $INSTALL_DIR

$trigger  = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $SERVICE_NAME `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

# Set environment variables system-wide
[System.Environment]::SetEnvironmentVariable("REFORMMED_SERVER_URL",  $SERVER_URL,  "Machine")
[System.Environment]::SetEnvironmentVariable("REFORMMED_API_KEY",     $API_KEY,     "Machine")
[System.Environment]::SetEnvironmentVariable("REFORMMED_SYSTEM_NAME", $SYSTEM_NAME, "Machine")
[System.Environment]::SetEnvironmentVariable("REFORMMED_LOCATION",    $LOCATION,    "Machine")
[System.Environment]::SetEnvironmentVariable("REFORMMED_INTERVAL",    $INTERVAL,    "Machine")

# Start immediately
Write-Host "  Starting agent now..." -ForegroundColor Blue
Start-ScheduledTask -TaskName $SERVICE_NAME

Start-Sleep -Seconds 3

# Check if running
$task = Get-ScheduledTask -TaskName $SERVICE_NAME -ErrorAction SilentlyContinue
$state = if ($task) { $task.State } else { "Unknown" }

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║        ✅ Installation Complete!             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Task status  : $state"
Write-Host "  Install dir  : $INSTALL_DIR"
Write-Host "  Config file  : $INSTALL_DIR\.env"
Write-Host ""
Write-Host "  Manage agent:" -ForegroundColor Yellow
Write-Host "  Stop    : Stop-ScheduledTask -TaskName '$SERVICE_NAME'"
Write-Host "  Start   : Start-ScheduledTask -TaskName '$SERVICE_NAME'"
Write-Host "  Remove  : Unregister-ScheduledTask -TaskName '$SERVICE_NAME' -Confirm:`$false"
Write-Host "  Status  : Get-ScheduledTask -TaskName '$SERVICE_NAME' | Select State"
Write-Host ""
Write-Host "✅ Agent sending data to: $SERVER_URL" -ForegroundColor Cyan
Write-Host ""
