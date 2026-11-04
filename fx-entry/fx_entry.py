#!/usr/bin/env python3
"""fx-entry: session opening-range entry timer for XAUUSD (or any FX symbol).

Reads the closed M5 bars that "FX Bars Pusher" writes (data/<SYMBOL>/M5/<date>.json),
builds the opening range of the London and/or New York session (first 15 minutes by
default) and calls the entry on the first completed M5 bar that CLOSES above the range
high (long) or below the range low (short). It never places an order.

Standard library only. Python 3.9+ (zoneinfo).
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")
BAR = timedelta(minutes=5)

# Session opens are in the session's own local time, so daylight saving is automatic.
SESSIONS = {
    "london": {"tz": "Europe/London", "open": (8, 0), "label": "London open 08:00"},
    "ny": {"tz": "America/New_York", "open": (9, 30), "label": "New York open 09:30"},
}


# --------------------------------------------------------------------------- time
def session_open_utc(name, d):
    """The session open of date d as an aware UTC datetime."""
    s = SESSIONS[name]
    h, m = s["open"]
    local = datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(s["tz"]))
    return local.astimezone(UTC)


def fmt_time(dt):
    return "%s UTC / %s IST" % (dt.astimezone(UTC).strftime("%H:%M"), dt.astimezone(IST).strftime("%H:%M"))


# --------------------------------------------------------------------------- data
def load_bars(data_dir, symbol, d):
    """Closed M5 bars of one UTC day. Returns (bars, digits). bars is [] when no file."""
    path = os.path.join(data_dir, symbol, "M5", "%s.json" % d.isoformat())
    if not os.path.isfile(path):
        return [], 2
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    bars = []
    for row in doc.get("bars", []):
        t, o, h, l, c, v = row[:6]
        spread = row[6] if len(row) > 6 else None
        bars.append({"t": datetime.fromtimestamp(int(t), UTC), "o": float(o), "h": float(h),
                     "l": float(l), "c": float(c), "v": float(v), "spread": spread})
    bars.sort(key=lambda b: b["t"])
    return bars, int(doc.get("digits", 2))


# --------------------------------------------------------------------------- rule
def evaluate(bars, name, d, now, or_minutes=15, until_min=180, min_vol_x=0.0):
    """Status of one session on date d at time now (aware UTC).

    status: closed | not_open | forming | no_data | waiting | triggered | expired
    """
    open_t = session_open_utc(name, d)
    range_end = open_t + timedelta(minutes=or_minutes)
    until_t = open_t + timedelta(minutes=until_min)
    res = {"session": name, "label": SESSIONS[name]["label"], "date": d.isoformat(),
           "open_utc": open_t.isoformat(), "range_end_utc": range_end.isoformat(),
           "until_utc": until_t.isoformat(), "status": None, "direction": None,
           "detail": "", "range_high": None, "range_low": None, "range_bars": 0,
           "level": None, "price": None, "time_utc": None, "bar_open_utc": None,
           "spread_points": None, "volume_x": None}
    if d.weekday() >= 5:
        res.update(status="closed", detail="Weekend: gold is closed.")
        return res
    if now < open_t:
        res.update(status="not_open", detail="Session opens %s." % fmt_time(open_t))
        return res
    if now < range_end:
        res.update(status="forming", detail="The opening range is still forming until %s." % fmt_time(range_end))
        return res

    closed = [b for b in bars if b["t"] + BAR <= now]          # a bar counts only once it has closed
    need = or_minutes // 5
    rng = [b for b in closed if open_t <= b["t"] < range_end]
    if len(rng) < need:
        res.update(status="no_data", range_bars=len(rng),
                   detail="Only %d of %d range bars found. Is FX Bars Pusher running and the data synced?" % (len(rng), need))
        return res
    hi = max(b["h"] for b in rng)
    lo = min(b["l"] for b in rng)
    avg_vol = sum(b["v"] for b in rng) / float(len(rng))
    res.update(range_high=hi, range_low=lo, range_bars=len(rng))

    after = [b for b in closed if b["t"] >= range_end]
    for b in after:
        if b["t"] + BAR > until_t:
            break
        direction = "long" if b["c"] > hi else ("short" if b["c"] < lo else None)
        if direction is None:
            continue                                            # a wick, or a close exactly on the level, is not a trigger
        vx = (b["v"] / avg_vol) if avg_vol > 0 else None
        if min_vol_x and (vx is None or vx < min_vol_x):
            continue
        res.update(status="triggered", direction=direction, level=hi if direction == "long" else lo,
                   price=b["c"], time_utc=(b["t"] + BAR).isoformat(), bar_open_utc=b["t"].isoformat(),
                   spread_points=b["spread"], volume_x=vx,
                   detail="The %s bar closed %s the range %s." % (
                       b["t"].astimezone(UTC).strftime("%H:%M"),
                       "above" if direction == "long" else "below",
                       "high" if direction == "long" else "low"))
        return res

    last = after[-1] if after else rng[-1]
    res["last_close"] = last["c"]
    if now >= until_t:
        res.update(status="expired", detail="No close outside the range before %s." % fmt_time(until_t))
    else:
        res.update(status="waiting",
                   detail="Last close %.2f: %.2f under the high, %.2f over the low." % (
                       last["c"], hi - last["c"], last["c"] - lo))
    return res


def pick_primary(results):
    """The result to write to entry.json: latest trigger, else the latest session that has started."""
    trig = [r for r in results if r["status"] == "triggered"]
    if trig:
        return max(trig, key=lambda r: r["time_utc"])
    started = [r for r in results if r["status"] not in ("not_open", "closed")]
    if started:
        return max(started, key=lambda r: r["open_utc"])
    return results[0]


# --------------------------------------------------------------------------- output
def render(res, symbol, digits):
    f = "%%.%df" % digits
    head = "%s  %s  %s" % (symbol, res["date"], res["label"])
    st = res["status"]
    lines = [head]
    if res["range_high"] is not None:
        lines.append("Opening range: high %s, low %s (%d bars)." % (f % res["range_high"], f % res["range_low"], res["range_bars"]))
    if st == "triggered":
        t = datetime.fromisoformat(res["time_utc"])
        side = "LONG (buy)" if res["direction"] == "long" else "SHORT (sell)"
        lines.append("TRIGGERED %s at %s, %s: %s" % (side, fmt_time(t), f % res["price"], res["detail"]))
        extra = []
        if res["spread_points"] is not None:
            extra.append("spread %s points" % res["spread_points"])
        if res["volume_x"] is not None:
            extra.append("volume %.2fx the range bars" % res["volume_x"])
        if extra:
            lines.append("Trigger bar: " + ", ".join(extra) + ".")
        lines.append("Nothing was placed. Next: set the stop and target BEFORE any order.")
    else:
        lines.append("%s: %s" % (st.upper().replace("_", " "), res["detail"]))
    return "\n".join(lines)


def write_entry(out_dir, symbol, res, digits):
    os.makedirs(out_dir, exist_ok=True)
    doc = {"symbol": symbol, "digits": digits}
    doc.update(res)
    path = os.path.join(out_dir, "entry.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return path


# --------------------------------------------------------------------------- commands
def parse_now(s):
    if not s:
        return datetime.now(UTC)
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)


def cmd_check(a):
    now = parse_now(a.now)
    d = date.fromisoformat(a.date) if a.date else now.date()
    names = ["london", "ny"] if a.session == "both" else [a.session]
    bars, digits = load_bars(a.data, a.symbol, d)
    if not bars and not os.path.isdir(os.path.join(a.data, a.symbol)):
        print("No data folder for %s in '%s'. Run: fx_entry.py sync" % (a.symbol, a.data))
        return 2
    results = [evaluate(bars, n, d, now, a.or_minutes, a.until_min, a.min_volume_x) for n in names]
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        print("\n\n".join(render(r, a.symbol, digits) for r in results))
    if a.write:
        p = write_entry(a.out, a.symbol, pick_primary(results), digits)
        print("\nWrote %s" % p)
    return 0 if any(r["status"] == "triggered" for r in results) else 1


def cmd_sync(a):
    """Copy data/ from the repo's data branch into the working folder (no checkout, nothing staged)."""
    r = subprocess.run(["git", "fetch", "origin", a.branch], capture_output=True, text=True)
    if r.returncode != 0:
        lines = r.stderr.strip().splitlines()
        print("git fetch failed: %s" % (lines[-1] if lines else "unknown error"))
        return 2
    p = subprocess.run(["git", "archive", "origin/%s" % a.branch, "data"], capture_output=True)
    if p.returncode != 0:
        print("The %s branch has no data/ folder yet. Is FX Bars Pusher running?" % a.branch)
        return 1
    dest = os.path.abspath(a.dest)
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        members = []
        for m in tf.getmembers():
            target = os.path.abspath(os.path.join(dest, m.name))
            if (m.isfile() or m.isdir()) and (target == dest or target.startswith(dest + os.sep)):
                members.append(m)
        try:
            tf.extractall(dest, members=members, filter="data")
        except TypeError:                                       # Python before the extraction filters
            tf.extractall(dest, members=members)
    n = sum(len(fs) for _, _, fs in os.walk(os.path.join(dest, "data")))
    print("Synced %d files into %s" % (n, os.path.join(dest, "data")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Session opening-range entry timer for XAUUSD (never places an order).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="status of the London / New York opening range")
    c.add_argument("--symbol", default="XAUUSD")
    c.add_argument("--session", choices=["london", "ny", "both"], default="both")
    c.add_argument("--date", help="UTC date YYYY-MM-DD (default: today)")
    c.add_argument("--now", help='pin the clock, UTC: "2026-11-04 08:30"')
    c.add_argument("--or-minutes", type=int, default=15, dest="or_minutes")
    c.add_argument("--until-min", type=int, default=180, dest="until_min",
                   help="no entries later than this many minutes after the open (default 180)")
    c.add_argument("--min-volume-x", type=float, default=0.0, dest="min_volume_x",
                   help="trigger bar tick volume must be this multiple of the range bars' average")
    c.add_argument("--data", default="data")
    c.add_argument("--out", default="trader")
    c.add_argument("--write", action="store_true", help="write trader/entry.json")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("sync", help="copy data/ from the data branch (git fetch + archive)")
    s.add_argument("--branch", default="data")
    s.add_argument("--dest", default=".")
    s.set_defaults(fn=cmd_sync)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
