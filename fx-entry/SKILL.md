---
name: fx-entry
description: >-
  FX Entry Timer for XAUUSD. Builds the opening range of the London (08:00 UK)
  and New York (09:30 US East) sessions from the closed M5 bars that
  FX Bars Pusher writes to GitHub, and calls the entry on the first completed
  bar that CLOSES above the range high (long) or below the range low (short).
  Says waiting, triggered with time and price, expired, forming or no data, and
  writes trader/entry.json. Never places an order. Use when the user says
  "check the London range", "has gold broken out", "New York open range",
  "entry signal for XAUUSD", "watch gold", or before setting a stop and target.
argument-hint: "[--session london|ny|both] [--now \"YYYY-MM-DD HH:MM\"]"
---

# fx-entry

`${CLAUDE_SKILL_DIR}` below is this skill's folder.

```bash
python3 "${CLAUDE_SKILL_DIR}/fx_entry.py" sync                         # data/ from the data branch
python3 "${CLAUDE_SKILL_DIR}/fx_entry.py" check                        # both sessions, today (UTC)
python3 "${CLAUDE_SKILL_DIR}/fx_entry.py" check --session ny --write   # also save trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/fx_entry.py" check --min-volume-x 1.5     # breakout bar needs 1.5x the range volume
```

Other flags: `--date`, `--or-minutes` (15), `--until-min` (180: no entries later than 3 hours after the open), `--symbol`, `--data`, `--out`, `--json`.

## The rule

- Range = high and low of the first 15 minutes (three M5 bars) after the session open.
- Trigger = the first completed M5 bar after the range that CLOSES above the high (long) or below the low (short). A wick is not a trigger. A close exactly on the level is not a trigger.
- Time = that bar's close time. Price = its close.
- Only closed bars count. The EA only ever sends closed bars.
- Statuses: not_open, forming, no_data, waiting, triggered, expired, closed (weekend).

## Steps

1. Run `sync` first, then `check`. Tell the user the status in one line per session, with the time in IST.
2. On `no_data`, say that FX Bars Pusher may not be running or the data is not synced. Do not guess.
3. When triggered, say the side, the time and the price, and that nothing was placed.
4. The next step is the stop and target (fx-exit, not built yet). Never suggest an order before them.

## Rules

- Never places an order.
- Bars are the broker's own XAUUSD M5 bars. If the server time offset looks wrong, the ranges are wrong: see STATE.md.
- Say once that a clean signal is not a prediction and most intraday traders lose money.
