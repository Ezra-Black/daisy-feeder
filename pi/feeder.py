#!/usr/bin/env python3
"""
Daisy Feeder 1.0 - drops a portion of feed when TikFinity (TikTok LIVE gifts/subs)
calls this Pi over the local network.

Endpoints
  GET/POST /feed?key=KEY[&user=NAME]   queue one portion (what TikFinity calls)
  GET      /status                      JSON: fed today, cap, queue, cooldown
  GET      /                            small status page with a manual "Feed now" button

Safety limits (so a gift spree can't overfeed the duck)
  COOLDOWN_SECONDS  minimum gap between portions
  DAILY_MAX         max portions per calendar day (survives restarts)
  MAX_QUEUE         pending requests; extras get HTTP 429

Settings come from environment variables (installed to /etc/duckfeeder.env).
Set FEEDER_MOCK=1 to run on a PC without a servo (for testing).
"""
import datetime
import hmac
import json
import logging
import os
import queue
import threading
import time
from pathlib import Path

from flask import Flask, abort, jsonify, request


def env(name, default, cast=str):
    try:
        return cast(os.environ.get(name, default))
    except ValueError:
        logging.warning("Bad value for %s, using default %s", name, default)
        return cast(default)


KEY = env("FEEDER_KEY", "")
PORT = env("FEEDER_PORT", "5000", int)
PIN = env("SERVO_PIN", "18", int)                 # GPIO18 = physical pin 12
OPEN_ANGLE = env("OPEN_ANGLE", "90", float)
CLOSED_ANGLE = env("CLOSED_ANGLE", "0", float)
OPEN_SECONDS = env("OPEN_SECONDS", "0.5", float)  # longer = bigger portion
PORTIONS_PER_FEED = env("PORTIONS_PER_FEED", "1", int)
COOLDOWN = env("COOLDOWN_SECONDS", "20", float)
DAILY_MAX = env("DAILY_MAX", "30", int)
MAX_QUEUE = env("MAX_QUEUE", "5", int)
STATE_FILE = Path(env("STATE_FILE", os.path.join(
    os.environ.get("STATE_DIRECTORY", "."), "state.json")))
MOCK = env("FEEDER_MOCK", "0") == "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("duckfeeder")

if not KEY:
    raise SystemExit("FEEDER_KEY is not set. Run install.sh or set it in /etc/duckfeeder.env")


# ---------------------------------------------------------------- servo
class MockServo:
    angle = None

    def detach(self):
        pass


if MOCK:
    servo = MockServo()
    log.info("MOCK mode: no servo will move")
else:
    from gpiozero import AngularServo
    servo = AngularServo(PIN, min_angle=0, max_angle=180,
                         min_pulse_width=0.0005, max_pulse_width=0.0025)
    servo.angle = CLOSED_ANGLE
    time.sleep(0.5)
    servo.detach()  # no jitter / heat while idle


def dispense_once():
    servo.angle = OPEN_ANGLE
    time.sleep(OPEN_SECONDS)
    servo.angle = CLOSED_ANGLE
    time.sleep(0.5)
    servo.detach()


# ---------------------------------------------------------------- state
lock = threading.Lock()
jobs = queue.Queue(maxsize=MAX_QUEUE)


def load_state():
    try:
        data = json.loads(STATE_FILE.read_text())
        return {"day": data["day"], "count": int(data["count"]),
                "last": 0.0, "recent": data.get("recent", [])}
    except Exception:
        return {"day": datetime.date.today().isoformat(), "count": 0, "last": 0.0, "recent": []}


def save_state():
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: state[k] for k in ("day", "count", "recent")}))
        tmp.replace(STATE_FILE)
    except OSError as e:
        log.warning("Could not save state: %s", e)


state = load_state()


def roll_day():
    today = datetime.date.today().isoformat()
    if state["day"] != today:
        state["day"], state["count"] = today, 0


def worker():
    while True:
        who = jobs.get()
        with lock:
            roll_day()
            if state["count"] >= DAILY_MAX:
                log.info("Daily max (%d) reached - not feeding for %s", DAILY_MAX, who)
                continue
            wait = state["last"] + COOLDOWN - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            for _ in range(PORTIONS_PER_FEED):
                dispense_once()
        except Exception:
            log.exception("Servo error")
            continue
        with lock:
            state["count"] += 1
            state["last"] = time.time()
            state["recent"] = ([{"who": who, "at": datetime.datetime.now().strftime("%H:%M:%S")}]
                               + state["recent"])[:10]
            save_state()
            log.info("Fed the duck thanks to %s (%d/%d today)", who, state["count"], DAILY_MAX)


# ---------------------------------------------------------------- web
app = Flask(__name__)


def key_ok():
    given = (request.args.get("key")
             or request.headers.get("X-Feeder-Key")
             or (request.get_json(silent=True) or {}).get("key")
             or "")
    return hmac.compare_digest(str(given), KEY)


@app.route("/feed", methods=["GET", "POST"])
def feed():
    if not key_ok():
        abort(403)
    body = request.get_json(silent=True) or {}
    who = (request.args.get("user") or body.get("nickname") or body.get("user")
           or "someone")[:40]
    with lock:
        roll_day()
        if state["count"] >= DAILY_MAX:
            return jsonify(status="daily limit reached", fed_today=state["count"]), 200
    try:
        jobs.put_nowait(who)
    except queue.Full:
        return jsonify(status="busy - queue full"), 429
    return jsonify(status="queued", waiting=jobs.qsize())


def status_dict():
    with lock:
        roll_day()
        return dict(fed_today=state["count"], daily_max=DAILY_MAX, waiting=jobs.qsize(),
                    cooldown_seconds=COOLDOWN, recent=state["recent"], mock=MOCK)


@app.route("/status")
def status():
    return jsonify(status_dict())


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Daisy Feeder</title>
<style>body{font-family:system-ui,sans-serif;max-width:420px;margin:24px auto;padding:0 16px;color:#1e293b}
h1{font-size:1.6rem}.big{font-size:2.4rem;font-weight:700}.card{background:#f1f5f9;border-radius:12px;padding:16px;margin:12px 0}
input,button{font-size:1rem;padding:10px;border-radius:8px;border:1px solid #cbd5e1;width:100%;box-sizing:border-box;margin-top:8px}
button{background:#16a34a;color:#fff;border:0;font-weight:700}li{margin:4px 0}#msg{margin-top:8px}</style></head>
<body><h1>&#129414; Daisy Feeder</h1>
<div class="card"><div>Portions today</div><div class="big"><span id="n">-</span> / <span id="max">-</span></div>
<div>Waiting in queue: <span id="q">-</span> &middot; Cooldown: <span id="cd">-</span>s</div></div>
<div class="card"><b>Recent feeds</b><ul id="recent"><li>-</li></ul></div>
<div class="card"><b>Manual test</b><input id="key" type="password" placeholder="Feeder key">
<button onclick="feed()">Feed now</button><div id="msg"></div></div>
<script>
async function load(){try{const s=await (await fetch('/status')).json();
n.textContent=s.fed_today;max.textContent=s.daily_max;q.textContent=s.waiting;cd.textContent=s.cooldown_seconds;
recent.innerHTML=s.recent.length?s.recent.map(r=>'<li>'+r.at+' - '+r.who.replace(/[<>&]/g,'')+'</li>').join(''):'<li>None yet</li>';}catch(e){}}
async function feed(){const r=await fetch('/feed',{method:'POST',headers:{'Content-Type':'application/json','X-Feeder-Key':key.value},body:JSON.stringify({user:'manual test'})});
msg.textContent=r.status==403?'Wrong key':(await r.json()).status;load();}
load();setInterval(load,3000);
</script></body></html>"""


@app.route("/")
def home():
    return PAGE


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    log.info("Daisy Feeder 1.0 listening on port %d (cooldown %ss, daily max %d)", PORT, COOLDOWN, DAILY_MAX)
    app.run(host="0.0.0.0", port=PORT)
