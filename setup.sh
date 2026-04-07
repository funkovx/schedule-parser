#!/bin/bash

REPO_RAW_URL="https://raw.githubusercontent.com/qfunky/schedule-parser/main"

apt update && apt install python3-venv python3-pip git curl -y

read -p "Включить/создать Swap файл на 1ГБ? (y/n): " confirm_swap
if [[ $confirm_swap == [yY] ]]; then
    if [ ! -f /swapfile ]; then
        echo "Создание Swap..."
        fallocate -l 1G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    else
        echo "Swap уже существует."
    fi
fi

cd /root

echo "Загрузка server.py..."
curl -L -O "$REPO_RAW_URL/server.py"

# Создание и настройка venv
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn icalendar pytz pyrinium

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

echo "---------------------------------------"
echo "Установка завершена. Статус службы:"
systemctl status schedule-parser.service --no-pager