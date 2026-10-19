#!/bin/bash
# Быстрая установка: скачивает репозиторий и запускает deploy/install.sh
set -euo pipefail
apt-get update && apt-get install -y git curl python3-venv nginx certbot
rm -rf /tmp/schedule-parser
git clone --depth 1 https://github.com/qfunky/schedule-parser /tmp/schedule-parser
bash /tmp/schedule-parser/deploy/install.sh
