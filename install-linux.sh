#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# REFORMMED Monitor — Linux Agent Installer
# Usage: curl -sSL https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main/install-linux.sh | sudo bash
# ─────────────────────────────────────────────────────────────────────────────
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="/opt/reformmed-agent"
SERVICE_NAME="reformmed-agent"
REPO_RAW="https://raw.githubusercontent.com/vivekdummi/com.agent.reformmed.monitor/main"

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║     REFORMMED Monitor — Agent Setup          ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root: sudo bash install-linux.sh${NC}"
    exit 1
fi

echo -e "${BOLD}Enter the following details:${NC}"
echo ""
read -p "$(echo -e ${YELLOW}"VM Server IP or domain (e.g. 164.52.221.241): "${NC})" VM_IP
read -p "$(echo -e ${YELLOW}"VM Server port [8000]: "${NC})" VM_PORT
VM_PORT="${VM_PORT:-8000}"
read -p "$(echo -e ${YELLOW}"API Secret Key: "${NC})" API_KEY
read -p "$(echo -e ${YELLOW}"This machine name (e.g. Office-PC1): "${NC})" SYSTEM_NAME
read -p "$(echo -e ${YELLOW}"This machine location (e.g. Mumbai): "${NC})" LOCATION
read -p "$(echo -e ${YELLOW}"Send interval in seconds [1]: "${NC})" INTERVAL
INTERVAL="${INTERVAL:-1}"

echo ""
echo -e "${BLUE}─────────────────────────────────────────────${NC}"
echo -e "  Server URL  : http://${VM_IP}:${VM_PORT}"
echo -e "  System Name : ${SYSTEM_NAME}"
echo -e "  Location    : ${LOCATION}"
echo -e "  Interval    : ${INTERVAL}s"
echo -e "${BLUE}─────────────────────────────────────────────${NC}"
echo ""
read -p "Confirm and install? [y/N]: " CONFIRM
[ "${CONFIRM,,}" != "y" ] && echo "Cancelled." && exit 0

echo ""
echo -e "${BLUE}[1/5]${NC} Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv curl

echo -e "${BLUE}[2/5]${NC} Creating install directory..."
mkdir -p "${INSTALL_DIR}"

echo -e "${BLUE}[3/5]${NC} Downloading agent..."
curl -sSL "${REPO_RAW}/agent.py" -o "${INSTALL_DIR}/agent.py"
curl -sSL "${REPO_RAW}/requirements.txt" -o "${INSTALL_DIR}/requirements.txt"

echo -e "${BLUE}[4/5]${NC} Installing Python dependencies..."
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

echo -e "${BLUE}[5/5]${NC} Configuring and starting service..."
cat > "${INSTALL_DIR}/.env" << ENVEOF
REFORMMED_SERVER_URL=http://${VM_IP}:${VM_PORT}
REFORMMED_API_KEY=${API_KEY}
REFORMMED_SYSTEM_NAME=${SYSTEM_NAME}
REFORMMED_LOCATION=${LOCATION}
REFORMMED_INTERVAL=${INTERVAL}
ENVEOF
chmod 600 "${INSTALL_DIR}/.env"

cat > "${INSTALL_DIR}/run.sh" << 'RUNEOF'
#!/bin/bash
set -a
source /opt/reformmed-agent/.env
set +a
exec /opt/reformmed-agent/venv/bin/python3 /opt/reformmed-agent/agent.py
RUNEOF
chmod +x "${INSTALL_DIR}/run.sh"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVCEOF
[Unit]
Description=REFORMMED Monitor Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/run.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=reformmed-agent

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 3
STATUS=$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || echo "unknown")

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║        ✅ Installation Complete!             ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Service status : ${STATUS}"
echo -e "  Config file    : ${INSTALL_DIR}/.env"
echo -e "  View logs      : journalctl -u ${SERVICE_NAME} -f"
echo -e "  Stop agent     : systemctl stop ${SERVICE_NAME}"
echo -e "  Start agent    : systemctl start ${SERVICE_NAME}"
echo -e "  Restart agent  : systemctl restart ${SERVICE_NAME}"
echo ""
echo -e "${CYAN}✅ Agent sending data to:${NC} http://${VM_IP}:${VM_PORT}"
echo ""
