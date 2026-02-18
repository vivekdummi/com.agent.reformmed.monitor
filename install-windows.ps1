# REFORMMED Monitor — Windows Agent Installer
# Run in PowerShell as Administrator:
# irm https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-windows.ps1 | iex

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     REFORMMED Monitor — Agent Setup          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "Enter the following details:" -ForegroundColor Yellow
Write-Host ""

$VM_IP       = Read-Host "VM Server IP (e.g. 164.52.221.241)"
$VM_PORT     = Read-Host "VM Server port [8000]"
if (-not $VM_PORT) { $VM_PORT = "8000" }
$API_KEY     = Read-Host "API Secret Key"
$SYSTEM_NAME = Read-Host "Machine name (e.g. Office-PC1)"
$LOCATION    = Read-Host "Location (e.g. Salem)"
$INTERVAL    = Read-Host "Send interval in seconds [1]"
if (-not $INTERVAL) { $INTERVAL = "1" }

$SERVER_URL  = "http://${VM_IP}:${VM_PORT}"
$d           = "C:\reformmed-agent"
$taskName    = "ReformmedMonitorAgent"

Write-Host ""
Write-Host "─────────────────────────────────────────────" -ForegroundColor Blue
Write-Host "  Server URL  : $SERVER_URL" -ForegroundColor White
Write-Host "  API Key     : $($API_KEY.Substring(0,20))..." -ForegroundColor White
Write-Host "  System Name : $SYSTEM_NAME" -ForegroundColor White
Write-Host "  Location    : $LOCATION" -ForegroundColor White
Write-Host "  Interval    : ${INTERVAL}s" -ForegroundColor White
Write-Host "─────────────────────────────────────────────" -ForegroundColor Blue
Write-Host ""
$confirm = Read-Host "Confirm and install? [y/N]"
if ($confirm -ne "y" -and $confirm -ne "Y") { 
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 0 
}

Write-Host ""
Write-Host "[1/5] Setting up directory..." -ForegroundColor Blue
if (Test-Path $d) { 
    Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue | Out-Null
}
New-Item -ItemType Directory -Force -Path $d | Out-Null

Write-Host "[2/5] Downloading agent..." -ForegroundColor Blue
Invoke-WebRequest "https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py" `
    -OutFile "$d\agent.py" -UseBasicParsing | Out-Null

Write-Host "[3/5] Installing Python dependencies..." -ForegroundColor Blue
python -m venv "$d\venv" *>&1 | Out-Null
Start-Sleep -Milliseconds 500
& "$d\venv\Scripts\pip.exe" install psutil requests pynvml *>&1 | Out-Null

Write-Host "[4/5] Writing configuration..." -ForegroundColor Blue
@"
REFORMMED_SERVER_URL=$SERVER_URL
REFORMMED_API_KEY=$API_KEY
REFORMMED_SYSTEM_NAME=$SYSTEM_NAME
REFORMMED_LOCATION=$LOCATION
REFORMMED_INTERVAL=$INTERVAL
"@ | Out-File -FilePath "$d\.env" -Encoding ASCII

@'
import os, subprocess, sys
with open(r"C:\reformmed-agent\.env") as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()
subprocess.run([sys.executable, r"C:\reformmed-agent\agent.py"])
'@ | Out-File -FilePath "$d\launcher.py" -Encoding ASCII

Write-Host "[5/5] Registering scheduled task..." -ForegroundColor Blue
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) { 
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false | Out-Null
}

$action    = New-ScheduledTaskAction -Execute "$d\venv\Scripts\python.exe" -Argument "`"$d\launcher.py`"" -WorkingDirectory $d
$trigger   = New-ScheduledTaskTrigger -AtStartup
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $taskName | Out-Null
Start-Sleep -Seconds 3

$state = (Get-ScheduledTask -TaskName $taskName).State

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║        ✅ Installation Complete!             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Task status : $state" -ForegroundColor Cyan
Write-Host "  Install dir : $d" -ForegroundColor Cyan
Write-Host "  Config file : $d\.env" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Manage agent:" -ForegroundColor Yellow
Write-Host "    Stop    : Stop-ScheduledTask -TaskName '$taskName'"
Write-Host "    Start   : Start-ScheduledTask -TaskName '$taskName'"
Write-Host "    Status  : Get-ScheduledTask -TaskName '$taskName' | Select State"
Write-Host "    Config  : notepad $d\.env"
Write-Host ""
Write-Host "✅ Agent sending data to: $SERVER_URL" -ForegroundColor Cyan
Write-Host "✅ Agent will auto-start on every Windows reboot!" -ForegroundColor Green
Write-Host ""
