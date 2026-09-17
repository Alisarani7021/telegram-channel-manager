#!/usr/bin/env bash
# Update + restart. Run inside project dir.
set -e
git pull 2>/dev/null || echo "(git repo نیست؛ رد شد)"
.venv/bin/pip install -r requirements.txt
sudo systemctl restart tcm-bot
echo "✅ آپدیت و ری‌استارت شد."
sudo journalctl -u tcm-bot -n 30 --no-pager
