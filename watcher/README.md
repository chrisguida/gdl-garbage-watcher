# Watcher (optional)

A small Python service that polls the same upstream feed and notifies you when
a CAABSA truck enters a block you care about. Designed for an always-on Linux
box (home server, VPS, Raspberry Pi) running systemd.

It uses only the Python standard library — no `pip install` step.

## Install

```bash
# 1. Pick a user-owned location for the install.
sudo mkdir -p /home/$USER/gdl-garbage-watcher
sudo chown $USER:$USER /home/$USER/gdl-garbage-watcher
cp watch_truck.py /home/$USER/gdl-garbage-watcher/

# 2. Create the env file from the template.
cp .env.example /home/$USER/gdl-garbage-watcher/.env
chmod 600 /home/$USER/gdl-garbage-watcher/.env
$EDITOR /home/$USER/gdl-garbage-watcher/.env       # fill in TARGET_LAT/LON etc.

# 3. Install the systemd unit (edit YOURUSER first).
sed "s/YOURUSER/$USER/g" gdl-garbage-watcher.service.example \
    | sudo tee /etc/systemd/system/gdl-garbage-watcher.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now gdl-garbage-watcher.service
systemctl status gdl-garbage-watcher.service --no-pager
```

The service polls every `POLL_SEC` seconds (default 60), and on each truck
entry into the `RADIUS_M`-meter circle around (`TARGET_LAT`, `TARGET_LON`),
it sends one notification per configured backend:

- **ntfy** if `NTFY_URL` is set (POST to that topic URL).
- **Telegram** if both `TG_BOT_TOKEN` and `TG_CHAT_ID` are set.

If neither is set, the watcher just logs to stdout / `LOGFILE`.

## Logs

```bash
journalctl -u gdl-garbage-watcher.service -f
```

…or `tail -F` whatever `LOGFILE` points to if you set it.

## Notes

- The upstream API's TLS cert is expired; the script keeps transport
  encryption but doesn't verify the cert (`CERT_NONE`). For public truck-GPS
  data this is acceptable.
- `.env` should be `chmod 600`. It contains your Telegram bot token if you
  use Telegram.
- The ntfy topic is essentially a public broadcast channel — anyone who knows
  the topic name receives every notification. Choose a random, unguessable
  topic name.
