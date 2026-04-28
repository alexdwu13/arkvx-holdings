# ARKVX Holdings Tracker

Downloads the daily ARK Venture Fund (ARKVX) full holdings CSV from [ark-funds.com](https://www.ark-funds.com/funds/arkvx) and visualizes the holdings as a stacked-percent chart in the terminal.

> Note: ARK publishes holdings on a quarterly cadence, so daily downloads will be byte-identical between publishings. The chart will show flat bars across a single quarter and shift only when new holdings are released.

## Setup

```bash
chmod +x download.sh
./download.sh         # writes data/ARKVX_HOLDINGS_YYYY-MM-DD.csv
```

## Schedule via cron

The downloader is idempotent — running multiple times per day re-uses the existing file. Schedule a few runs to catch the publish window:

```
0 8,10,12,14,16 * * 1-5 cd /Users/alexwu/work/arkvx-holdings && { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')]"; ./download.sh; } >> cron.log 2>&1
```

macOS cron does not run while the machine is asleep — if reliability matters, use `launchd` with `StartCalendarInterval` or keep the Mac awake during business hours.

## Visualize

```bash
python3 visualize.py
```
<img width="821" height="846" alt="image" src="https://github.com/user-attachments/assets/eb2747cd-82b4-4c28-a7cb-cef8eae8e3fd" />


Renders a stacked-100% bar chart with one column per snapshot and a legend showing the latest weight per holding. Holdings whose cumulative weight from the bottom is under `--other-pct` (default 10%) are folded into a gray "Other" band.

Flags:

- `--other-pct N` — bottom-N% of holdings to fold into "Other" (default 10).
- `--height N` — chart height in rows.
- `--width N` — total width in columns.
- `--data PATH` — alternate data directory.

Requires a 24-bit-color terminal (most modern terminals — iTerm2, Terminal.app, Alacritty, kitty, etc.).

## Files

- `download.sh` — Downloads the CSV, skips if today's file already exists.
- `visualize.py` — Terminal stacked-percent chart, stdlib only.
- `data/` — Daily CSVs stored as `ARKVX_HOLDINGS_YYYY-MM-DD.csv`, plus reference PDFs.
- `cron.log` — Append-only log from scheduled runs.

## Source

CSV URL: `https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_VENTURE_FUND_ARKVX_HOLDINGS.csv`


