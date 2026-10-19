# Schedule Parser

Serves the class schedule of any Sirius College group as an iCalendar feed, so you can subscribe to it in Apple Calendar, Google Calendar or any other calendar app and always see up-to-date classes.

## Usage

Subscribe to:

```
https://funkov.space:8443/schedule.ics?group=K0609-24
```

| Parameter | Default | Description |
| --- | --- | --- |
| `group` | `K0609-24` | Group code. The letter can be typed in Latin or Cyrillic. |
| `skip_pa` | `1` | Assessment events (ПА/ППА) are hidden by default. Set `0` to keep them. |
| `alarm` | `10` | Reminder lead time in minutes. `0` disables reminders. |

The feed contains the current week and the next two. Weeks without a published schedule are empty.

## How it works

- `server.py` (FastAPI) listens only on `127.0.0.1:8090`, runs as a dedicated `schedule` user and is sandboxed with systemd hardening.
- nginx terminates HTTPS on port 8443 (Let's Encrypt), rate-limits clients and only allows `GET /schedule.ics`.
- Responses are cached for 15 minutes in `/var/lib/schedule-parser`. If the source site is down, the last good copy (up to 7 days old) is served instead of an empty calendar, which would wipe everyone's classes.
- Event UIDs are stable, so calendar apps update existing events instead of recreating them on every refresh.

## Self-hosting

On a Debian/Ubuntu server, as root:

```bash
curl -sSL https://raw.githubusercontent.com/funkovx/schedule-parser/main/setup.sh | bash
```

The installer creates the service user, installs the systemd unit and the nginx config, and requests a certificate. See `deploy/` for the individual pieces.
