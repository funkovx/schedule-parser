#!/bin/bash
# Ставит парсер за nginx: приложение на 127.0.0.1:8090 от отдельного пользователя,
# старые ссылки на портах 8000/8001 продолжают работать, новый адрес по HTTPS на 8443.
# Запускать от root из папки, где лежат server.py и deploy/.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/schedule-parser
DOMAIN=funkov.space

echo "=== Пользователь и файлы ==="
id schedule >/dev/null 2>&1 || useradd --system --home-dir "$APP" --no-create-home --shell /usr/sbin/nologin schedule
install -d -m 755 "$APP"
install -m 644 "$SRC/server.py" "$APP/server.py"

if [ ! -x "$APP/.venv/bin/python3" ]; then
    apt-get install -y python3-venv nginx certbot >/dev/null
    python3 -m venv "$APP/.venv"
fi
"$APP/.venv/bin/pip" install -q --disable-pip-version-check \
    fastapi==0.141.1 uvicorn==0.52.0 icalendar==7.2.2 pyrinium==0.1.1 requests==2.34.2

echo "=== Служба ==="
install -m 644 "$SRC/deploy/schedule-parser.service" /etc/systemd/system/schedule-parser.service
systemctl daemon-reload
systemctl enable schedule-parser.service
systemctl restart schedule-parser.service
for _ in $(seq 1 20); do curl -fs http://127.0.0.1:8090/health >/dev/null && break; sleep 1; done
curl -fs -o /dev/null http://127.0.0.1:8090/schedule.ics

echo "=== Сертификат ==="
if [ ! -e "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && [ -n "$(ls -A /etc/letsencrypt/accounts 2>/dev/null)" ]; then
    certbot certonly --webroot -w /var/www/html -d "$DOMAIN" --non-interactive \
        --deploy-hook "systemctl reload nginx" || true
fi

CONF=/etc/nginx/sites-available/schedule-parser
if [ -e "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    install -m 644 "$SRC/deploy/nginx-schedule.conf" "$CONF"
else
    echo "Сертификата нет, порт 8443 пока не включаю"
    sed '/^# Новый адрес/,$d' "$SRC/deploy/nginx-schedule.conf" > "$CONF"
fi
ln -sf "$CONF" /etc/nginx/sites-enabled/schedule-parser
nginx -t

echo "=== Переключение старых портов на nginx ==="
OLD="schedule-parser-8000.service schedule-parser-8001.service"
systemctl stop $OLD 2>/dev/null || true
if ! systemctl reload nginx || ! { sleep 1; curl -fs -o /dev/null http://127.0.0.1:8000/schedule.ics; }; then
    echo "nginx не поднялся, возвращаю старые службы"
    rm -f /etc/nginx/sites-enabled/schedule-parser
    systemctl reload nginx || true
    systemctl start $OLD
    exit 1
fi
systemctl disable $OLD 2>/dev/null || true

echo "=== Готово ==="
ss -tlnp | grep -E ':(8000|8001|8090|8443) '
