# FX-TRADER-SKILL-

Forex / gold version of the day-trader-skill idea: a session opening-range breakout on XAUUSD.
Built part by part. Nothing here places an order yet.

## How it works (v1.00)

```
MT5 (VPS)                         GitHub                           Claude
FX Bars Pusher EA  --M5 bars-->   branch "data"                    fx-entry check
(never trades)                    data/XAUUSD/M5/<day>.json  <--sync--  (reads the bars, calls the entry)
```

1. **FX Bars Pusher** (`mt5/FX Bars Pusher v1.00.mq5`) sends every closed M5 bar of XAUUSD to the `data` branch, one JSON file per UTC day.
2. **fx-entry** (`fx-entry/fx_entry.py`) builds the opening range of the **London** (08:00 UK time) and **New York** (09:30 US East time) sessions: the high and low of the first 15 minutes. The entry is the first completed M5 bar that **closes** above the range high (long) or below the range low (short). A wick, or a close exactly on the level, is not a trigger. Daylight saving is handled automatically. Times are shown in UTC and IST.

```bash
python3 fx-entry/fx_entry.py sync                      # copy data/ from the data branch
python3 fx-entry/fx_entry.py check                     # both sessions, today (UTC)
python3 fx-entry/fx_entry.py check --session london --write
python3 fx-entry/fx_entry.py check --now "2026-11-04 08:30" --min-volume-x 1.5
python3 -m unittest discover -s tests -v               # offline tests
```

## Roadmap

| part | what | status |
| --- | --- | --- |
| 1 | FX Bars Pusher EA | v1.00 built, needs a compile + run on the VPS |
| 2 | fx-entry (session range + trigger) | v1.00 built, tests pass |
| 3 | fx-exit (stop, target, flat-by) | next |
| 4 | fx-timemachine (10,000 replays + real history on XAUUSD) | next |
| 5 | lot sizing | later |
| 6 | risk gate (spread, session window, loss limits) | later |
| 7 | order executor (GitHub ticket -> VPS EA, only after your yes, demo first) | later |

Not financial advice. Most people who trade intraday lose money. Test on demo first.
