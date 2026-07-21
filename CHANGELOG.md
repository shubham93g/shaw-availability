# Changelog

## Initial build

Full scanner implementation: `config`, `models`, `api_client`, `collector`,
`stats`, `persistence`, `report`, `cli` modules plus a `main.py` entrypoint.

- Scans `get_show_times` across up to 14 days from a start date (default
  today), stopping early on the first date with zero showtimes.
- Calls `get_layouts` per showtime and computes per-show/day/scan
  availability stats, with availability % = `AV / (AV + SO + BL)`.
- A single bad HTTP call (either endpoint) is recorded as a `FailedCall` and
  skipped rather than aborting the run; a failed `get_show_times` call is
  never mistaken for "no showtimes that day."
- Unrecognized seat/showtime status codes are tolerated: bucketed as
  `unknown`, logged once per unique code, and preserved in the output rather
  than discarded.
- Each run prints a console report and writes `scan_result.json`,
  `shows.csv`, `days.csv` to a timestamped `output/` subdirectory, plus
  appends to `output/history_shows.csv` for cross-run trend tracking.
- `report.py` separates building structured report data (`build_report`)
  from rendering/printing it, so a future notifier (e.g. Telegram) can reuse
  the same structured data without touching collection or stats logic.
- Verified against the live API: a 14-day scan correctly stopped early once
  it hit the edge of Shaw's published schedule (10 days out at the time),
  with zero failed calls across 174 showtimes.

## Added `OH` (on hold) as a recognized seat status

Live data showed a seat status beyond `AV`/`SO`/`BL`: `OH`, appearing to mean
"on hold" (e.g. seats temporarily locked mid-checkout). Added it to
`config.KNOWN_SEAT_STATUSES`, added an `on_hold` field to `ShowStats` and
`DayAggregate`, and included it in the availability % denominator alongside
`BL` — on-hold seats aren't currently bookable, so they count as
unavailable.

## Removed a false-positive anomaly rule

`stats._detect_anomaly()` previously flagged any showtime where
`seatingStatus == "SO"` but the seat layout still had `AV` seats, on the
assumption `SO` meant zero seats remained. Live investigation of a real
example (Lido IMAX, `performanceId=504185`) disproved this: the showtime was
marked `SO` with 21 of 413 seats still `AV`, and every one of those 21 sat in
the four front-most, least desirable rows (confirmed via seat-map
coordinates and a rendered seating chart). `SO` appears to reflect a
"practically sold out" business threshold rather than literal zero
availability, so this pattern is expected, not anomalous. The rule was
removed rather than replaced with a guessed percentage threshold, since
there isn't enough data yet to know where Shaw's actual cutoff sits. The
other anomaly rule (`seatingStatus == "AV"` with computed 0% availability)
is unaffected.
