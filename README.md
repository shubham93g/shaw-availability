# Shaw IMAX Seat-Availability Scanner

Scans Shaw Theatres' internal IMAX booking API to see how full upcoming
IMAX showtimes are, across all venues, over the next two weeks.

## What it does

1. Calls `get_show_times` once per date, starting today, for up to 14 days —
   stopping early the first time a date comes back with zero showtimes (the
   edge of Shaw's published schedule).
2. For every showtime found, calls `get_layouts` once to pull the full seat
   map for that performance.
3. Computes seat-availability stats per show, per day, and for the whole
   scan, and prints a console report.
4. Persists results to disk so availability can be tracked over time.

## Usage

```bash
pip install -r requirements.txt
python main.py                    # default: 14 days starting today
python main.py --days 3           # scan a shorter window
python main.py --start-date 2026-08-01
python main.py --output-dir myrun --verbose
```

## APIs used

- `GET https://shaw.sg/internal/get_show_times?date=YYYY-MM-DD&movieId=0&locationId=0&promotionId=0&locationBrand=2`
  — all IMAX showtimes for a date, across every Shaw IMAX venue.
- `GET https://shaw.sg/internal/get_layouts?performanceId=<id>`
  — the full seat map for one showtime.

Both are undocumented internal endpoints (used respectfully: sequential
calls only, throttled ~0.35s apart, small `--days` recommended for quick
checks).

## Status codes

**Showtime-level `seatingStatus`:** `AV` (available), `SF` (selling fast),
`SO` (sold out — in practice this means *practically* sold out, not
necessarily zero seats; see below). Other values are tolerated and passed
through untouched.

**Seat-level `elementStatusCodeCurrent`** (only `elementCategoryCode ==
"SEAT"` elements are counted):
- `AV` — available
- `SO` — sold
- `BL` — blocked (matched house/companion seats in observed samples)
- `OH` — on hold (temporarily locked, e.g. mid-checkout)
- anything else — bucketed as `unknown`, with the raw code preserved in
  `unknown_codes` rather than discarded, and logged once per unique code

Availability % per show = `AV / (AV + SO + BL + OH)`.

Note: a live example showed `seatingStatus=SO` on a show that still had 21
`AV` seats — all of them in the four least-desirable front rows. `SO`
appears to reflect Shaw's own "practically sold out" threshold rather than
literal zero availability, so this is expected behavior, not flagged as an
anomaly.

## Output

Each run writes to `output/<UTC-timestamp>/`:
- `scan_result.json` — the full scan result
- `shows.csv` / `days.csv` — per-show and per-day stats for that run

...and appends every show's stats (with a `scanned_at` timestamp) to
`output/history_shows.csv`, so availability can be compared across runs.

## Project layout

```
shaw_availability/
├── main.py                  # entrypoint
├── shaw_availability/
│   ├── config.py             # URLs, headers, timing/retry constants
│   ├── api_client.py         # HTTP layer (requests.Session, retries, throttling)
│   ├── models.py             # dataclasses for showtimes, seats, stats, results
│   ├── collector.py          # orchestrates the date/showtime/layout scan
│   ├── stats.py              # pure stat computation, anomaly detection
│   ├── persistence.py        # JSON/CSV output writers
│   ├── report.py             # builds and prints the console report
│   └── cli.py                # argument parsing and wiring
└── output/                   # created at runtime, gitignored
```

## Not yet built

Telegram delivery of results. `report.py` already splits report-building
(`build_report` → structured `ReportData`) from rendering/printing, so a
notifier can be added later without touching collection or stats logic.
