#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════╗"
echo "║     REFORMMED Monitor — Agent Setup          ║"
echo "╚══════════════════════════════════════════════╝"

# Collect inputs
echo "Enter the following details:"
read -p "VM Server IP (e.g. 164.52.221.241): " SERVER_IP
read -p "VM Server port [8000]: " SERVER_PORT
SERVER_PORT=${SERVER_PORT:-8000}
read -p "API Secret Key: " API_SECRET
read -p "Machine name (e.g. Salem-Hospital-PC1): " SYSTEM_NAME
read -p "Location (e.g. Salem): " LOCATION
read -p "Send interval in seconds [15]: " INTERVAL
INTERVAL=${INTERVAL:-15}

echo "─────────────────────────────────────────────"
echo "  Server URL  : http://$SERVER_IP:$SERVER_PORT"
echo "  System Name : $SYSTEM_NAME"
echo "  Location    : $LOCATION"
echo "  Interval    : ${INTERVAL}s"
echo "─────────────────────────────────────────────"
read -p "Confirm and install? [y/N]: " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# Fix apt_pkg error first
echo "[0/7] Fixing apt_pkg error..."
sudo apt --fix-broken install -y 2>/dev/null || true

echo "[1/7] Installing system dependencies..."
sudo apt update -qq 2>/dev/null || true
sudo apt install -y python3 python3-pip python3-venv curl || {
    echo "⚠️  Warning: Some packages may have failed, continuing..."
}

echo "[2/7] Creating dedicated service account..."
if ! id -u reformmed &>/dev/null; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin reformmed
fi
# Group membership for GPU/sensor device access (harmless if groups don't exist)
sudo usermod -aG video,render reformmed 2>/dev/null || true

echo "[3/7] Creating agent directory..."
sudo mkdir -p /opt/reformmed-agent
sudo chown -R reformmed:reformmed /opt/reformmed-agent
cd /opt/reformmed-agent

echo "[4/7] Downloading agent code..."
sudo -u reformmed curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/agent.py -o agent.py

echo "[5/7] Setting up Python environment..."
sudo -u reformmed python3 -m venv venv
sudo -u reformmed ./venv/bin/pip install --quiet --upgrade pip
# NOTE: python-dotenv is required — agent.py imports it on line 1.
# Missing it here was the bug that caused ModuleNotFoundError on every
# fresh install and required a manual "pip install python-dotenv" patch.
sudo -u reformmed ./venv/bin/pip install --quiet psutil requests pynvml python-dotenv

# Detect GPU
GPU_TYPE="none"
if command -v nvidia-smi &> /dev/null; then
    GPU_TYPE="nvidia"
elif command -v intel_gpu_top &> /dev/null; then
    GPU_TYPE="intel"
fi

echo "[6/7] Creating configuration..."
sudo -u reformmed tee .env > /dev/null <<EOF
REFORMMED_API_URL=http://$SERVER_IP:$SERVER_PORT
REFORMMED_API_SECRET=$API_SECRET
REFORMMED_SYSTEM_NAME=$SYSTEM_NAME
REFORMMED_LOCATION=$LOCATION
REFORMMED_INTERVAL=$INTERVAL
GPU_TYPE=$GPU_TYPE
EOF
sudo chmod 600 .env
sudo chown reformmed:reformmed .env

echo "[7/7] Setting up systemd service..."
sudo tee /etc/systemd/system/reformmed-agent.service > /dev/null <<'SERVICEEOF'
[Unit]
Description=REFORMMED Monitor Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=reformmed
Group=reformmed
WorkingDirectory=/opt/reformmed-agent
ExecStart=/opt/reformmed-agent/venv/bin/python /opt/reformmed-agent/agent.py
Restart=always
RestartSec=10
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
SERVICEEOF

sudo systemctl daemon-reload
sudo systemctl enable reformmed-agent
sudo systemctl restart reformmed-agent

sleep 3

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        ✅ Installation Complete!             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📊 Agent Status:"
sudo systemctl status reformmed-agent --no-pager -l | head -10
echo ""
echo "📋 Check logs:"
echo "   sudo journalctl -u reformmed-agent -f"
echo ""
echo "🌐 Dashboard:"
echo "   http://$SERVER_IP:5000"
echo ""
echo "🔧 Control commands:"
echo "   sudo systemctl start reformmed-agent"
echo "   sudo systemctl stop reformmed-agent"
echo "   sudo systemctl restart reformmed-agent"
echo ""
