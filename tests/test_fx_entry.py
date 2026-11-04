"""Offline tests for fx-entry. Run: python3 -m unittest discover -s tests -v"""
import importlib.util
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from io import StringIO

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("fx_entry", os.path.join(HERE, "..", "fx-entry", "fx_entry.py"))
fx = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fx)

UTC = timezone.utc
D_WINTER = date(2026, 11, 4)       # Wednesday. London = GMT, New York = EST (US DST ended Nov 1)


def bar(t, o, h, l, c, v=100, spread=20):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "spread": spread}


def london_day(extra):
    """3 range bars 08:00/08:05/08:10 (high 2650.50, low 2648.00) plus the extra bars from 08:15 on."""
    t0 = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
    bars = [bar(t0, 2649.0, 2650.0, 2648.5, 2649.5),
            bar(t0 + timedelta(minutes=5), 2649.5, 2650.5, 2648.0, 2650.0),
            bar(t0 + timedelta(minutes=10), 2650.0, 2650.3, 2648.6, 2649.8)]
    for i, (o, h, l, c, v) in enumerate(extra):
        bars.append(bar(t0 + timedelta(minutes=15 + 5 * i), o, h, l, c, v))
    return bars


def at(h, m):
    return datetime(2026, 11, 4, h, m, tzinfo=UTC)


class SessionTimes(unittest.TestCase):
    def test_london_follows_uk_clock(self):
        self.assertEqual(fx.session_open_utc("london", date(2026, 11, 4)), at(8, 0))
        self.assertEqual(fx.session_open_utc("london", date(2026, 7, 15)),
                         datetime(2026, 7, 15, 7, 0, tzinfo=UTC))

    def test_new_york_follows_us_clock(self):
        self.assertEqual(fx.session_open_utc("ny", date(2026, 11, 4)), at(14, 30))      # EST
        self.assertEqual(fx.session_open_utc("ny", date(2026, 10, 28)),
                         datetime(2026, 10, 28, 13, 30, tzinfo=UTC))                    # EDT


class Rule(unittest.TestCase):
    def test_before_open_and_forming(self):
        self.assertEqual(fx.evaluate([], "london", D_WINTER, at(7, 59))["status"], "not_open")
        self.assertEqual(fx.evaluate(london_day([]), "london", D_WINTER, at(8, 7))["status"], "forming")

    def test_weekend_is_closed(self):
        self.assertEqual(fx.evaluate([], "london", date(2026, 11, 7), at(9, 0))["status"], "closed")

    def test_no_data(self):
        r = fx.evaluate([], "london", D_WINTER, at(8, 30))
        self.assertEqual(r["status"], "no_data")

    def test_waiting_and_range(self):
        r = fx.evaluate(london_day([(2649.8, 2650.4, 2649.0, 2650.2, 100)]), "london", D_WINTER, at(8, 20))
        self.assertEqual(r["status"], "waiting")
        self.assertEqual(r["range_high"], 2650.5)
        self.assertEqual(r["range_low"], 2648.0)

    def test_wick_and_equal_close_are_not_triggers_then_long_trigger(self):
        extra = [(2650.0, 2650.4, 2649.5, 2650.3, 100),     # 08:15 inside
                 (2650.3, 2652.0, 2650.0, 2650.5, 100),     # 08:20 wick above, close exactly on the high
                 (2650.5, 2651.5, 2650.4, 2651.0, 100)]     # 08:25 closes above
        r = fx.evaluate(london_day(extra), "london", D_WINTER, at(8, 40))
        self.assertEqual(r["status"], "triggered")
        self.assertEqual(r["direction"], "long")
        self.assertEqual(r["price"], 2651.0)
        self.assertEqual(r["time_utc"], at(8, 30).isoformat())           # bar close time, not bar open time
        self.assertEqual(r["level"], 2650.5)

    def test_short_trigger(self):
        extra = [(2648.5, 2648.9, 2647.0, 2647.5, 100)]
        r = fx.evaluate(london_day(extra), "london", D_WINTER, at(8, 30))
        self.assertEqual((r["status"], r["direction"], r["price"], r["level"]), ("triggered", "short", 2647.5, 2648.0))

    def test_unclosed_bar_does_not_count(self):
        extra = [(2650.0, 2650.4, 2649.5, 2650.3, 100), (2650.3, 2652.0, 2650.0, 2651.5, 100)]
        r = fx.evaluate(london_day(extra), "london", D_WINTER, at(8, 22))   # the 08:20 bar closes at 08:25
        self.assertEqual(r["status"], "waiting")

    def test_volume_check_moves_the_trigger(self):
        extra = [(2650.3, 2651.5, 2650.2, 2651.0, 50),       # thin breakout bar, 0.5x the range average
                 (2651.0, 2652.5, 2650.9, 2652.0, 300)]      # heavy bar, 3x
        thin = fx.evaluate(london_day(extra), "london", D_WINTER, at(8, 40), min_vol_x=0.0)
        heavy = fx.evaluate(london_day(extra), "london", D_WINTER, at(8, 40), min_vol_x=1.5)
        self.assertEqual(thin["price"], 2651.0)
        self.assertEqual(heavy["price"], 2652.0)

    def test_expired_when_window_ends_without_trigger(self):
        extra = [(2650.0, 2650.4, 2649.5, 2650.3, 100)] * 40
        r = fx.evaluate(london_day(extra), "london", D_WINTER, at(11, 30), until_min=180)
        self.assertEqual(r["status"], "expired")

    def test_trigger_after_cutoff_is_ignored(self):
        t0 = datetime(2026, 11, 4, 8, 0, tzinfo=UTC)
        bars = london_day([])
        bars.append(bar(t0 + timedelta(minutes=180), 2650.5, 2655.0, 2650.4, 2654.0))   # bar starting 11:00
        r = fx.evaluate(bars, "london", D_WINTER, at(11, 30), until_min=180)
        self.assertEqual(r["status"], "expired")

    def test_primary_prefers_latest_trigger(self):
        a = {"status": "triggered", "time_utc": "2026-11-04T08:30:00+00:00", "open_utc": "x"}
        b = {"status": "triggered", "time_utc": "2026-11-04T14:50:00+00:00", "open_utc": "y"}
        c = {"status": "waiting", "time_utc": None, "open_utc": "z"}
        self.assertIs(fx.pick_primary([a, b, c]), b)


class Cli(unittest.TestCase):
    def test_check_reads_pusher_file_and_writes_entry_json(self):
        t0 = int(datetime(2026, 11, 4, 8, 0, tzinfo=UTC).timestamp())
        rows = [[t0, 2649.0, 2650.0, 2648.5, 2649.5, 100, 20],
                [t0 + 300, 2649.5, 2650.5, 2648.0, 2650.0, 100, 20],
                [t0 + 600, 2650.0, 2650.3, 2648.6, 2649.8, 100, 20],
                [t0 + 900, 2650.0, 2651.5, 2649.9, 2651.0, 120, 25]]
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "data", "XAUUSD", "M5")
            os.makedirs(folder)
            with open(os.path.join(folder, "2026-11-04.json"), "w") as f:
                json.dump({"symbol": "XAUUSD", "digits": 2, "bars": rows}, f)
            out = os.path.join(tmp, "trader")
            buf = StringIO()
            with redirect_stdout(buf):
                code = fx.main(["check", "--session", "london", "--now", "2026-11-04 08:25",
                                "--data", os.path.join(tmp, "data"), "--out", out, "--write"])
            self.assertEqual(code, 0)
            self.assertIn("TRIGGERED LONG", buf.getvalue())
            self.assertIn("13:50 IST", buf.getvalue())                    # 08:20 UTC = 13:50 IST
            with open(os.path.join(out, "entry.json")) as f:
                doc = json.load(f)
            self.assertEqual((doc["status"], doc["direction"], doc["price"]), ("triggered", "long", 2651.0))

    def test_missing_data_folder_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = StringIO()
            with redirect_stdout(buf):
                code = fx.main(["check", "--now", "2026-11-04 09:00", "--data", os.path.join(tmp, "nope")])
            self.assertEqual(code, 2)
            self.assertIn("sync", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
