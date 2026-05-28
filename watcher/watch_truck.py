#!/usr/bin/env python3
"""Poll Guadalajara's public CAABSA truck-position feed and notify when any
garbage truck enters a configured block.

All configuration comes from environment variables (see .env.example).
Designed to run as a systemd service; see gdl-garbage-watcher.service.example.
"""
import json, math, os, time, urllib.parse, urllib.request, ssl, sys
from datetime import datetime, timezone, timedelta

API = "https://tequierolimpiapi.guadalajara.gob.mx/caabsa/posiciones"

def env(name, default=None, cast=str, required=False):
    v = os.environ.get(name)
    if v is None or v == "":
        if required:
            sys.exit(f"missing required env var: {name}")
        return default
    try:
        return cast(v)
    except ValueError:
        sys.exit(f"invalid value for {name}: {v!r}")

TARGET_LAT   = env("TARGET_LAT", cast=float, required=True)
TARGET_LON   = env("TARGET_LON", cast=float, required=True)
RADIUS_M     = env("RADIUS_M", 150, cast=int)
POLL_SEC     = env("POLL_SEC", 30, cast=int)
# A "real" stop (truck parked to collect) vs. a drive-by: close AND stopped for
# STOP_DWELL_SEC seconds straight (independent of POLL_SEC).
STOP_RADIUS_M  = env("STOP_RADIUS_M", 60, cast=int)     # tighter ring than RADIUS_M
STOP_SPEED_MAX = env("STOP_SPEED_MAX", 0, cast=float)   # km/h; 0 = fully stopped
STOP_DWELL_SEC = env("STOP_DWELL_SEC", 29, cast=int)    # 29 < POLL_SEC -> fires on the 2nd stopped poll
LOGFILE      = env("LOGFILE")        # if unset, log to stdout only
TZ_OFFSET_H  = env("TZ_OFFSET_H", -6, cast=int)   # Guadalajara = -6, no DST
LOCAL_TZ     = timezone(timedelta(hours=TZ_OFFSET_H))
MAP_URL      = env("MAP_URL", "")    # optional; appended to alerts

NTFY_URL     = env("NTFY_URL")       # optional
TG_BOT_TOKEN = env("TG_BOT_TOKEN")   # optional
TG_CHAT_ID   = env("TG_CHAT_ID")     # optional
TG_HOUR_START = env("TG_HOUR_START", 10, cast=int)  # local-time window [start, end)
TG_HOUR_END   = env("TG_HOUR_END", 12, cast=int)    # for Telegram only; ntfy is unrestricted

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE      # upstream's TLS cert expired

def haversine_m(a_lat, a_lon, b_lat, b_lon):
    R = 6371000
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))

def fetch():
    req = urllib.request.Request(API, headers={"User-Agent": "gdl-garbage-watcher"})
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        return json.loads(r.read())

def log(msg):
    line = f"[{datetime.now(LOCAL_TZ):%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    if LOGFILE:
        with open(LOGFILE, "a") as f:
            f.write(line + "\n")

def ntfy(title, body, priority="default", tags=""):
    if not NTFY_URL:
        return
    try:
        req = urllib.request.Request(
            NTFY_URL,
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": priority, "Tags": tags},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log(f"ntfy push failed: {e}")

def telegram(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    hour = datetime.now(LOCAL_TZ).hour
    if not (TG_HOUR_START <= hour < TG_HOUR_END):
        log(f"telegram suppressed (hour {hour} outside {TG_HOUR_START}:00-{TG_HOUR_END}:00)")
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log(f"telegram push failed: {e}")

inside = {}        # vehicle_name -> first_seen_ts inside RADIUS_M (drives the silent alert)
stop_since = {}    # vehicle_name -> ts it first became close+stopped (a parked candidate)
stop_alerted = set()  # vehicles we've already fired the loud "parked" alert for this stop
last_loud_date = None  # local date of the last loud alert; caps the loud alert to one/day
log(f"watching ({TARGET_LAT},{TARGET_LON}) within {RADIUS_M}m, poll every {POLL_SEC}s")

while True:
    try:
        data = fetch()
        seen_now = set()
        parked_now = set()
        nearest = None
        for t in data.get("posiciones", []):
            try:
                la, lo = float(t["lat"]), float(t["lng"])
            except (TypeError, ValueError, KeyError):
                continue
            try:
                spd = float(t.get("current_speed", 0))
            except (TypeError, ValueError):
                spd = 0.0
            d = haversine_m(TARGET_LAT, TARGET_LON, la, lo)
            if nearest is None or d < nearest[0]:
                nearest = (d, t)

            # loud alert: close AND stopped for >= STOP_DWELL_SEC seconds, at most once per day
            if d <= STOP_RADIUS_M and spd <= STOP_SPEED_MAX:
                pname = t["vehicle_name"]
                parked_now.add(pname)
                stop_since.setdefault(pname, time.time())
                dwell = time.time() - stop_since[pname]
                if dwell >= STOP_DWELL_SEC and pname not in stop_alerted:
                    stop_alerted.add(pname)
                    today = datetime.now(LOCAL_TZ).date()
                    if last_loud_date == today:
                        log(f"PARKED  truck #{pname} d={d:.0f}m dwell={dwell:.0f}s "
                            f"-- loud already sent today, skipping")
                    else:
                        last_loud_date = today
                        log(f"PARKED  truck #{pname} plate={t['vehicle_plate']} "
                            f"d={d:.0f}m speed={spd:.0f} dwell={dwell:.0f}s -- sending LOUD alert")
                        short = (f"Truck {t['vehicle_plate']} is parked {d:.0f}m away "
                                 f"-- go take the trash out!")
                        ntfy("Truck parked at your block", short,
                             priority="max", tags="rotating_light,truck")
                        tg_body = f"🛑 #{pname} PARKED -- {short}"
                        if MAP_URL:
                            tg_body += f"\n🗺️ {MAP_URL}"
                        telegram(tg_body)

            if d <= RADIUS_M:
                seen_now.add(t["vehicle_name"])
                if t["vehicle_name"] not in inside:
                    inside[t["vehicle_name"]] = time.time()
                    log(f"ARRIVED truck #{t['vehicle_name']} plate={t['vehicle_plate']} "
                        f"at ({la:.6f},{lo:.6f}) dist={d:.0f}m speed={t['current_speed']}")
                    short = (f"Truck {t['vehicle_plate']} entered the block "
                             f"({d:.0f}m, {t['current_speed']} km/h) "
                             f"at {datetime.now(LOCAL_TZ):%a %H:%M}")
                    ntfy(f"Trash truck #{t['vehicle_name']}", short,
                         priority="high", tags="garbage,truck")
                    tg_body = f"🚛 #{t['vehicle_name']} — {short}"
                    if MAP_URL:
                        tg_body += f"\n🗺️ {MAP_URL}"
                    telegram(tg_body)
        for name in list(inside):
            if name not in seen_now:
                dur = time.time() - inside.pop(name)
                log(f"LEFT    truck #{name} after {dur:.0f}s in the radius")
        for name in list(stop_since):
            if name not in parked_now:
                stop_since.pop(name, None)
                stop_alerted.discard(name)
        if nearest:
            d, t = nearest
            log(f"... nearest #{t['vehicle_name']} d={d:.0f}m speed={t['current_speed']}")
    except Exception as e:
        log(f"ERROR {type(e).__name__}: {e}")
    time.sleep(POLL_SEC)
