### 1. Подготовка окружения и зависимостей

``` bash
apt update && apt install python3-venv python3-pip git -y
cd /root
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn icalendar pytz pyrinium
```

### 2. Создание файла парсера

Нужно создать файл `server.py`

```bash
nano /root/server.py # Вставить код server.py
```

![[server.py]]


### 3. Создание системной службы (systemd)

Чтобы сервер запускался сам и работал в фоне, создать файл службы.

```bash
nano /etc/systemd/system/schedule-parser.service
```

```toml
[Unit]
Description=FastAPI Schedule Parser
After=network.target

[Service]
User=root
WorkingDirectory=/root
ExecStart=/root/.venv/bin/python3 /root/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
OOMScoreAdjust=-500 #Заставляет systemd не дропать службу если OOM

[Install]
WantedBy=multi-user.target
```

### 4. Запуск службы

```Bash
systemctl daemon-reload
systemctl enable schedule-parser.service
systemctl start schedule-parser.service
systemctl status schedule-parser.service
```

---

Если мало оперативки на сервере, то можно настроить swap

```bash
fallocate -l 2G /swapfile # Создание файла свап
chmod 600 /swapfile # Права доступа (только для root)
mkswap /swapfile # Разметка файла как swap
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab # Чтобы жил после перезагрузки
```

**Swappiness**

Он определяет, насколько охотно система переносит данные из RAM в Swap.

- **По умолчанию:** 60.
- **Для серверов с малым объемом RAM:** Рекомендуется значение **10**. Это заставит систему использовать оперативную память до последнего, обращаясь к медленному диску только в критических ситуациях.

```bash
sysctl vm.swappiness=10 # Временная установка (до перезагрузки)
echo 'vm.swappiness=10' >> /etc/sysctl.conf # Постоянная установка
```

