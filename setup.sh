#!/bin/bash

REPO_RAW_URL="https://raw.githubusercontent.com/qfunky/schedule-parser/main"
WORK_DIR="/root/schedule-parser"

echo "=== Установка зависимостей ==="
apt update && apt install python3-venv python3-pip git curl -y

echo "=== Создание рабочей директории ==="
mkdir -p $WORK_DIR
cd $WORK_DIR

echo "=== Скачивание server.py ==="
curl -L -O "$REPO_RAW_URL/server.py"

echo "=== Настройка виртуального окружения ==="
python3 -m venv .venv
$WORK_DIR/.venv/bin/pip install --upgrade pip
$WORK_DIR/.venv/bin/pip install fastapi uvicorn icalendar pytz pyrinium

echo "=== Создание службы для К0609-24 (Порт 8000) ==="
cat << EOF > /etc/systemd/system/schedule-parser-8000.service
[Unit]
Description=FastAPI Schedule Parser (Group K0609-24)
After=network.target

[Service]
User=root
WorkingDirectory=$WORK_DIR
Environment="TARGET_GROUP=К0609-24"
ExecStart=$WORK_DIR/.venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
EOF

echo "=== Создание службы для К0409-25/1 (Порт 8001) ==="
cat << EOF > /etc/systemd/system/schedule-parser-8001.service
[Unit]
Description=FastAPI Schedule Parser (Group K0409-25/1)
After=network.target

[Service]
User=root
WorkingDirectory=$WORK_DIR
Environment="TARGET_GROUP=К0409-25/1"
ExecStart=$WORK_DIR/.venv/bin/python3 -m uvicorn server:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
EOF

echo "=== Перезагрузка и запуск служб ==="
systemctl daemon-reload
systemctl enable schedule-parser-8000.service
systemctl enable schedule-parser-8001.service
systemctl restart schedule-parser-8000.service
systemctl restart schedule-parser-8001.service

echo "=== Готово! ==="
echo "Порт 8000: Расписание К0609-24"
echo "Порт 8001: Расписание К0409-25/1"
