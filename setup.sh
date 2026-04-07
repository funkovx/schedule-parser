#!/bin/bash

REPO_RAW_URL="https://raw.githubusercontent.com/qfunky/schedule-parser/main"

apt update && apt install python3-venv python3-pip git curl -y

cd /root
curl -L -O "$REPO_RAW_URL/server.py"

python3 -m venv .venv
/root/.venv/bin/pip install --upgrade pip
/root/.venv/bin/pip install fastapi uvicorn icalendar pytz pyrinium

cat << EOF > /etc/systemd/system/schedule-parser.service
[Unit]
Description=FastAPI Schedule Parser
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/root/.venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable schedule-parser.service
systemctl restart schedule-parser.service

systemctl status schedule-parser.service --no-pager
