# REFORMMED Monitor — Windows Agent Installer
# Run in PowerShell as Administrator:
# irm https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-windows.ps1 | iex

#Requires -RunAsAdministrator
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

$VM_IP   = Read-Host "VM Server IP (e.g. 164.52.221.241)"
$VM_PORT = Read-Host "VM Server port [8000]"
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
if ($confirm -ne "y" -and $confirm -ne "Y") { exit 0 }

Write-Host "[1/5] Checking Python..." -ForegroundColor Blue
$python = $null
foreach ($cmd in @("python","python3","py")) {
    try { $v = & $cmd --version 2>&1; if ($v -match "Python 3") { $python=$cmd; break } } catch {}
}
if (-not $python) {
    Write-Host "Installing Python via winget..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.12 --silent
    $python = "python"
}

Write-Host "[2/5] Creating install directory..." -ForegroundColor Blue
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

Write-Host "[3/5] Downloading agent..." -ForegroundColor Blue
Invoke-WebRequest -Uri "$REPO_RAW/agent.py"        -OutFile "$INSTALL_DIR\agent.py"
Invoke-WebRequest -Uri "$REPO_RAW/requirements.txt" -OutFile "$INSTALL_DIR\requirements.txt"

Write-Host "[4/5] Installing dependencies..." -ForegroundColor Blue
& $python -m venv "$INSTALL_DIR\venv"
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --quiet --upgrade pip
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --quiet -r "$INSTALL_DIR\requirements.txt"
& "$INSTALL_DIR\venv\Scripts\pip.exe" install --quiet WMI pywin32 2>$null

Write-Host "[5/5] Installing as Windows Service..." -ForegroundColor Blue
@"
REFORMMED_SERVER_URL=$SERVER_URL
REFORMMED_API_KEY=$API_KEY
REFORMMED_SYSTEM_NAME=$SYSTEM_NAME
REFORMMED_LOCATION=$LOCATION
REFORMMED_INTERVAL=$INTERVAL
"@ | Out-File -FilePath "$INSTALL_DIR\.env" -Encoding ASCII

# Install via Task Scheduler
$action   = New-ScheduledTaskAction -Execute "$INSTALL_DIR\venv\Scripts\python.exe" -Argument "$INSTALL_DIR\agent.py" -WorkingDirectory $INSTALL_DIR
$trigger  = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 99 -RestartInterval (New-TimeSpan -Seconds 10)
$principal= New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $SERVICE_NAME -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

# Set environment variables
$envVars = @{
    "REFORMMED_SERVER_URL"  = $SERVER_URL
    "REFORMMED_API_KEY"     = $API_KEY
    "REFORMMED_SYSTEM_NAME" = $SYSTEM_NAME
    "REFORMMED_LOCATION"    = $LOCATION
    "REFORMMED_INTERVAL"    = $INTERVAL
}
foreach ($key in $envVars.Keys) {
    [System.Environment]::SetEnvironmentVariable($key, $envVars[$key], "Machine")
}

Start-ScheduledTask -TaskName $SERVICE_NAME

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║        ✅ Installation Complete!             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Install dir : $INSTALL_DIR"
Write-Host "  Stop agent  : Stop-ScheduledTask -TaskName '$SERVICE_NAME'"
Write-Host "  Start agent : Start-ScheduledTask -TaskName '$SERVICE_NAME'"
Write-Host "  Logs        : Get-Content $INSTALL_DIR\agent.log -Tail 50"
Write-Host ""
Write-Host "Agent sending data to: $SERVER_URL" -ForegroundColor Cyan
