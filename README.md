# REFORMMED Monitor — Agent

Lightweight monitoring agent for Ubuntu/Linux and Windows.
Sends metrics every second to your REFORMMED Monitor server.

---

## 🐧 Install on Ubuntu/Linux
```bash
curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-linux.sh -o /tmp/install.sh
chmod +x /tmp/install.sh
sudo bash /tmp/install.sh
```

---

## 🪟 Install on Windows

Open **PowerShell as Administrator** (search PowerShell → right-click → Run as Administrator), then paste this one-liner:
```powershell
$d="C:\reformmed-agent"; if(Test-Path $d){Remove-Item -Recurse -Force $d}; New-Item -ItemType Directory -Force -Path $d|Out-Null; Invoke-WebRequest "https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py" -OutFile "$d\agent.py" -UseBasicParsing; python -m venv "$d\venv"; & "$d\venv\Scripts\pip.exe" install -q psutil requests pynvml; $sn=Read-Host "Machine name (e.g. Office-PC1)"; $loc=Read-Host "Location (e.g. Salem)"; Set-Content "$d\.env" "REFORMMED_SERVER_URL=http://164.52.221.241:8000`nREFORMMED_API_KEY=6aec8f303a91bedf21f9362257f9f4d5cb5168b1`nREFORMMED_SYSTEM_NAME=$sn`nREFORMMED_LOCATION=$loc`nREFORMMED_INTERVAL=1"; Set-Content "$d\launcher.py" "import os,subprocess,sys`n[os.environ.update({k.strip():v.strip()}) for l in open(r'C:\reformmed-agent\.env') for k,v in [l.strip().split('=',1)] if '=' in l and not l.startswith('#')]`nsubprocess.run([sys.executable,r'C:\reformmed-agent\agent.py'])"; Get-ScheduledTask 'ReformmedMonitorAgent' -ErrorAction SilentlyContinue|Unregister-ScheduledTask -Confirm:$false; $a=New-ScheduledTaskAction -Execute "$d\venv\Scripts\python.exe" -Argument "`"$d\launcher.py`"" -WorkingDirectory $d; $t=New-ScheduledTaskTrigger -AtStartup; $s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 3650); $p=New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest; Register-ScheduledTask -TaskName 'ReformmedMonitorAgent' -Action $a -Trigger $t -Settings $s -Principal $p -Force|Out-Null; Start-ScheduledTask 'ReformmedMonitorAgent'; Start-Sleep 3; Write-Host "✅ Done! State: $((Get-ScheduledTask 'ReformmedMonitorAgent').State)" -ForegroundColor Green
```

---

## 📋 Install Details to Enter

| Field | Value |
|---|---|
| VM Server IP | 164.52.221.241 |
| Port | 8000 |
| API Secret | 6aec8f303a91bedf21f9362257f9f4d5cb5168b1 |
| Machine Name | e.g. Salem-Hospital-PC1 |
| Location | e.g. Salem |
| Interval | 1 |

---

## 🔧 Windows Agent Management
```powershell
# Check status
Get-ScheduledTask -TaskName 'ReformmedMonitorAgent' | Select-Object TaskName, State

# Stop agent
Stop-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Start agent
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Remove agent completely
Get-ScheduledTask -TaskName 'ReformmedMonitorAgent' | Unregister-ScheduledTask -Confirm:$false
Remove-Item -Recurse -Force "C:\reformmed-agent"

# Edit config (change name, location, server)
notepad C:\reformmed-agent\.env
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Update agent to latest version
Stop-ScheduledTask -TaskName 'ReformmedMonitorAgent'
Invoke-WebRequest "https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py" -OutFile "C:\reformmed-agent\agent.py" -UseBasicParsing
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'
```

---

## 🐧 Linux Agent Management
```bash
# Check status
systemctl status reformmed-agent

# Stop
sudo systemctl stop reformmed-agent

# Start
sudo systemctl start reformmed-agent

# Restart
sudo systemctl restart reformmed-agent

# View logs live
journalctl -u reformmed-agent -f

# Edit config
sudo nano /opt/reformmed-agent/.env
sudo systemctl restart reformmed-agent

# Update to latest version
sudo curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py \
  -o /opt/reformmed-agent/agent.py
sudo systemctl restart reformmed-agent

# Remove completely
sudo systemctl stop reformmed-agent
sudo systemctl disable reformmed-agent
sudo rm -f /etc/systemd/system/reformmed-agent.service
sudo systemctl daemon-reload
sudo rm -rf /opt/reformmed-agent
```

---

## 📊 Metrics Collected

- CPU usage % (total + per core) + frequency + temperature
- RAM used/total/% + swap
- GPU — NVIDIA / Intel iGPU / AMD (auto-detected)
- Disk usage per partition + read/write speed (snap/loop excluded)
- Network bytes/sec in and out
- Top 10 processes by CPU
- System uptime, hostname, OS version, public IP

---

## 🔗 Server Repo

https://github.com/vivekdummi/com.server.reformmed.monitor
