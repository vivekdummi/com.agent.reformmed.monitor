# REFORMMED Monitor — Agent

Lightweight monitoring agent for Ubuntu/Linux and Windows.
Sends metrics every N seconds (default: **15s**, configurable at install time) to your REFORMMED Monitor server.

---

## 🐧 Install on Ubuntu/Linux
```bash
curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-linux.sh -o /tmp/install.sh
chmod +x /tmp/install.sh
sudo bash /tmp/install.sh
```

**What it asks:**
- VM Server IP (e.g. 164.52.221.241)
- Port [8000]
- API Secret Key
- Machine name (e.g. Salem-Hospital-PC1)
- Location (e.g. Salem)
- Send interval [15]

The agent runs under a dedicated, unprivileged **`reformmed`** system account (not root) via systemd, with `/opt/reformmed-agent` owned by that user from install time — no manual `chown` ever needed.

---

## 🪟 Install on Windows

Open **PowerShell as Administrator**, then run:
```powershell
irm https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-windows.ps1 | iex
```

**What it asks:**
- VM Server IP (e.g. 164.52.221.241)
- VM Server port [8000]
- API Secret Key
- Machine name (e.g. Office-PC1)
- Location (e.g. Delhi)
- Send interval in seconds [15]

Then confirms all settings before installing. Runs as a Scheduled Task under the `SYSTEM` account.

> **Note:** CPU temperature and Intel iGPU detail stats are Linux-only features (`psutil`/`intel_gpu_top` don't support Windows) — those fields report empty/0 on Windows agents. CPU/RAM/disk and NVIDIA GPU (via `pynvml`) all work normally.

---

## 📋 What You Need

| Field | Example | Where to get it |
|---|---|---|
| VM Server IP | 164.52.221.241 | Your server's public IP |
| Port | 8000 | Default is 8000 |
| API Secret Key | 6aec8f303a91bedf21f9362257f9f4d5cb5168b1 | From server setup (`API_SECRET` in the server's `.env`) |
| Machine Name | Salem-Hospital-PC1 | Choose a name (no spaces) |
| Location | Salem | Choose location |

---

## 📊 Metrics Collected (every `INTERVAL` seconds, default 15s)

- ✅ CPU usage % (total + per core) + frequency + temperature (Linux only)
- ✅ RAM used/total/% + swap
- ✅ GPU — NVIDIA / Intel iGPU (Linux) / auto-detected
- ✅ Disk usage per partition + read/write speed (snap/loop excluded)
- ✅ Network bytes/sec in and out
- ✅ Top 20 processes by CPU
- ✅ System uptime, hostname, OS version, public IP (refreshed every 10 min, not on every send)

---

## 🔧 Linux Agent Management
```bash
# Check status
systemctl status reformmed-agent

# View logs live
journalctl -u reformmed-agent -f

# View last 20 lines
journalctl -u reformmed-agent --no-pager -n 20

# Restart
sudo systemctl restart reformmed-agent

# Stop
sudo systemctl stop reformmed-agent

# Start
sudo systemctl start reformmed-agent

# Edit config (change server, name, location)
sudo nano /opt/reformmed-agent/.env
sudo systemctl restart reformmed-agent

# Update to latest version
# (use -u reformmed so the file keeps correct ownership — a plain root curl
#  would re-break the no-chown-needed setup)
sudo -u reformmed curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py \
  -o /opt/reformmed-agent/agent.py
sudo systemctl restart reformmed-agent

# Remove completely
sudo systemctl stop reformmed-agent
sudo systemctl disable reformmed-agent
sudo rm -f /etc/systemd/system/reformmed-agent.service
sudo systemctl daemon-reload
sudo rm -rf /opt/reformmed-agent
sudo userdel reformmed   # optional — removes the dedicated service account too
```

---

## 🪟 Windows Agent Management
```powershell
# Check status
Get-ScheduledTask -TaskName 'ReformmedMonitorAgent' | Select-Object TaskName, State

# Stop agent
Stop-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Start agent
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Edit config (change server, name, location)
notepad C:\reformmed-agent\.env
Stop-ScheduledTask -TaskName 'ReformmedMonitorAgent'
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Update to latest version
Stop-ScheduledTask -TaskName 'ReformmedMonitorAgent'
Invoke-WebRequest "https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py" `
    -OutFile "C:\reformmed-agent\agent.py" -UseBasicParsing
Start-ScheduledTask -TaskName 'ReformmedMonitorAgent'

# Remove completely
Get-ScheduledTask -TaskName 'ReformmedMonitorAgent' | Unregister-ScheduledTask -Confirm:$false
Remove-Item -Recurse -Force "C:\reformmed-agent"
```

---

## ♻️ Auto-Start on Reboot

**Linux:** Agent runs as a systemd service under the `reformmed` user — auto-starts on every reboot.

**Windows:** Agent runs as a Scheduled Task with an `AtStartup` trigger — auto-starts on every reboot.

---

## 🔗 Links

- **Server Repo:** https://github.com/vivekdummi/com.server.reformmed.monitor
- **Dashboard:** http://164.52.221.241:5000
- **API Health:** http://164.52.221.241:8000/health

---

*REFORMMED Monitor — Healthcare Infrastructure Monitoring*
