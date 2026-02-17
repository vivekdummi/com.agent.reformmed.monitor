# REFORMMED Monitor — Agent

Lightweight monitoring agent for Ubuntu/Linux and Windows machines.
Sends metrics every second to your REFORMMED Monitor server.

## Install on Ubuntu/Linux
```bash
curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-linux.sh | sudo bash
```

## Install on Windows (PowerShell as Administrator)
```powershell
irm https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-windows.ps1 | iex
```

## What you need ready

| Field | Where to get it |
|---|---|
| VM Server IP | Your VM public IP |
| API Secret Key | From server install output |
| Machine Name | You choose (e.g. Office-PC1) |
| Location | You choose (e.g. Mumbai) |

## Metrics collected every second

- CPU usage % (total + per core) + frequency
- RAM used/total/% + swap
- GPU (NVIDIA/AMD/Intel) usage, VRAM, temperature
- Disk usage per partition + read/write speed
- Network bytes/sec in and out
- Top 10 processes by CPU
- System uptime, hostname, OS version
- Public IP address

## Agent management
```bash
# View live logs
journalctl -u reformmed-agent -f

# Restart
systemctl restart reformmed-agent

# Stop
systemctl stop reformmed-agent

# Edit config (change VM IP, name, etc.)
nano /opt/reformmed-agent/.env
systemctl restart reformmed-agent
```

## Server repo

https://github.com/vivekdummi/com.server.reformmed.monitor
