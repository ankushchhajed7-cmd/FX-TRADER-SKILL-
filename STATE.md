# STATE: FX-TRADER-SKILL-

## Goal
Forex/gold version of the day-trader-skill pack. Same idea (opening-range breakout), applied to XAUUSD at the London and New York session opens. Order route (later): GitHub ticket -> EA on the VPS places the order only after the owner's "yes".

## Version history
- **v1.00** (2026-11-04, branch `feature-v1.0.0`): first build.
  - `mt5/FX Bars Pusher v1.00.mq5`: pushes closed M5 bars to the `data` branch, one JSON per UTC day. Never trades.
  - `fx-entry/fx_entry.py`: session range + entry trigger (long and short), `sync`, `check`. 15 offline tests pass.
  - NOT yet compiled in MetaEditor. NOT yet run against real bars.

- **v1.10** (2026-11-04, branch `feature-v1.1.0`): app icons added in `icons/` (SVG source, 192/512 PNG, apple-touch, favicon) for the mobile dashboard app that comes later. EA and fx-entry are unchanged (EA still v1.00).

## Decisions
- Instrument: XAUUSD only to start. Broker symbol is an input (Exness: `XAUUSDm`).
- Sessions: London open 08:00 (Europe/London) and New York open 09:30 (America/New_York), both. DST follows each city's clock.
- Opening range = first 15 minutes (3 M5 bars). Entry = first M5 bar that closes outside it. Long and short.
- No entries later than 180 minutes after the open (flag `--until-min`).
- Data path: MT5 EA -> GitHub `data` branch (`data/XAUUSD/M5/YYYY-MM-DD.json`) -> `fx_entry.py sync`. The `data/` folder is git-ignored on every other branch.
- Repo is private (it will later hold order tickets). The EA needs a fine-grained token, this repo only, Contents read+write. The token goes in the EA inputs only, never in chat or in a file.
- Logo: gold arrow breaking out of an opening-range box on a dark navy background. Icon content is kept inside the maskable safe zone.
- Bar JSON: `[time_utc_epoch, open, high, low, close, tick_volume, spread_points]`.

## Known limits (v1.00)
- Server time offset: the EA reads one live offset (server minus UTC) and applies it to all history. If the broker's server clock changes with daylight saving, bars from before the change are shifted by one hour in the files. Exness uses a fixed GMT+0 server time, so it is fine there. Check the first bar (checklist).
- Volume is tick volume, not real volume.
- The first backfill takes about 3 seconds per missing day (60 days = a few minutes).
- GitHub commit noise: about 288 commits a day on the `data` branch. That is why it is a separate branch.

## Pending work
- Part 3: fx-exit (stop at range midpoint, target 1R/2R, flat-by time)
- Part 4: fx-timemachine on real XAUUSD bars. Decide whether to continue only after this.
- Part 5: lot sizing for XAUUSD (contract size, tick value)
- Part 6: risk gate (spread, session window, daily loss)
- Part 7: order executor (ticket -> GitHub -> VPS EA, demo first)

## Verify checklist for v1.00
See README "Verify" section in the chat message that came with this build; the same steps:
1. Compile `FX Bars Pusher v1.00.mq5` in MetaEditor: 0 errors.
2. MT5 > Tools > Options > Expert Advisors > allow WebRequest, add `https://api.github.com`.
3. Attach to any chart. Inputs: `GitHubToken`, `BrokerSymbol` (your XAUUSD name), leave the rest.
4. Chart corner shows "Backfill: running", then "Backfill: done". Experts tab shows "pushed YYYY-MM-DD (N bars)".
5. GitHub > branch `data` > `data/XAUUSD/M5/`: day files appear. Open today's file: last bar is 5-10 minutes old at most.
6. First-bar check: a 08:00 UK bar in the file has epoch time equal to 08:00 UTC in winter (07:00 UTC in summer).
7. Run `python3 fx-entry/fx_entry.py sync` then `check`.
