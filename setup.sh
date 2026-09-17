#!/usr/bin/env bash
# One-command installer for Ubuntu 22.04/24.04 VPS.
# Usage:  bash setup.sh
set -e

echo "=== 1) System update ==="
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-dev git nano curl build-essential

echo "=== 2) Virtualenv + deps ==="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
mkdir -p data

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> .env ساخته شد. حالا با nano بازش کن و پرش کن:"
  echo "    nano .env"
else
  echo ">>> .env از قبل هست."
fi

echo "=== 3) systemd service ==="
SERVICE=/etc/systemd/system/tcm-bot.service
sudo tee $SERVICE > /dev/null <<EOF
[Unit]
Description=Telegram Channel Manager (free)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/.venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable tcm-bot

echo ""
echo "=========================================="
echo " نصب تمام شد! قدم‌های بعدی:"
echo "  1) nano .env   (توکن و API_ID/HASH رو بذار)"
echo "  2) sudo systemctl start tcm-bot"
echo "  3) sudo journalctl -u tcm-bot -f   (دیدن لاگ)"
echo "=========================================="
