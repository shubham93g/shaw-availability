# CLAUDE.md

Operating notes for working in this repo. Product-level docs (what the tool
does, usage, output, deployment) live in `README.md` — this file assumes that
context and focuses on how to change and verify code here safely.

## Project layout

```
shaw_availability/
├── main.py                  # entrypoint
├── shaw_availability/
│   ├── config.py             # URLs, headers, timing/retry constants
│   ├── api_client.py         # HTTP layer (requests.Session, retries, throttling)
│   ├── models.py             # dataclasses for showtimes, seats, stats, results
│   ├── collector.py          # orchestrates the date/showtime/layout scan
│   ├── stats.py              # pure stat computation
│   ├── seat_geometry.py      # classifies/compresses best-available seat ranges
│   ├── persistence.py        # writes index.html/scan_result.json
│   ├── report.py             # builds the report and renders text/HTML output
│   ├── templates/            # Jinja2 templates for index.html
│   └── cli.py                # argument parsing and wiring
```

## Running tests

Stdlib `unittest`, not pytest (no pytest in `requirements.txt`, no pytest config
anywhere in the repo):

```bash
python3 -m unittest discover -s tests -v
```

Tests **do** run in CI: `.github/workflows/scan.yml` runs this exact command
before every scan, and a failing suite blocks that cycle's scan and deploy.
They're not a PR/merge gate, though — scan.yml only fires on its own
`workflow_dispatch`, never on `pull_request` — so a bad change won't be caught
until the next scheduled run tries to fire.

Observed conventions across `tests/test_collector.py`, `test_persistence.py`,
`test_seat_geometry.py`:
- Test class naming: `<WhatItTests>Test`, never `TestXxx`. Method naming: long,
  sentence-like `test_<full behavior description>` — the name doubles as the
  spec, not just a label.
- `@patch` targets the import site inside the module under test (e.g.
  `shaw_availability.collector.api_client.get_show_times`, not
  `shaw_availability.api_client.get_show_times`), with a `side_effect`
  function branching on the input rather than a canned `return_value` list.
- Only `test_persistence.py` uses `setUp` + `self.addCleanup(...)` (not
  `tearDown`) to swap `config.ARTIFACTS_DIR` to a temp dir — the pattern to
  reuse for any new test that touches disk or global config. This works
  because module-level config is deliberately mutable; tests lean on that.
- Fixtures: real captured API JSON lives under `tests/fixtures/`, loaded
  through the actual production parser (`collector.parse_seat_elements`)
  rather than hand-built objects, with a class docstring explaining the
  real-world quirk the fixture pins down (see `test_seat_geometry.py`).
- No test resets `collector.py`'s module-level dedup sets (see gotcha below),
  and none currently exercises the "unknown status code" logging path — a
  future test that does must reset them manually.

## Verifying report/template changes without hitting Shaw's live API

The `report` CLI subcommand reads the already-committed `artifacts/scan_result.json`
(via `persistence.load_scan_result_json`) and rebuilds `artifacts/index.html`
purely from that file — no network call to Shaw. It also prints the plain-text
report to stdout, so the same command covers both output formats:

```bash
python3 main.py report
```

Run this after any change to `index.html.j2` (or the Python that feeds it) and
open `artifacts/index.html` in a browser to check it, instead of writing one-off
render scripts or scanning the live API just to see a template change.

## Code conventions

No linter, formatter, or type-checker is configured anywhere in the repo (no
`pyproject.toml`, `.ruff.toml`, `mypy.ini`, etc.) — these are observed
conventions, not enforced ones:

- Every module starts with `from __future__ import annotations`.
- Dataclasses for all data models (`models.py`, plus local ones in
  `collector.py`/`report.py`), plain and mutable — no `frozen`, `slots`, or
  field validation. `FailedCall.kind` and `ScanResult.stop_reason`
  (`models.py:62,73`) are the closest thing to an enum in the codebase — their
  allowed values are documented only in a trailing `#` comment, not
  `typing.Literal`, so nothing catches a typo'd value at runtime.
- Constants and magic strings are centralized in `config.py` rather than
  inlined at the call site.
- `logging.getLogger(__name__)` per module, not `print` — the one deliberate
  exception is the CLI's own text-report output in `cli.py`.
- Docstrings are rare, reserved for non-obvious "why." Comments are preferred
  over docstrings for explaining tricky logic inline.

## Template (Jinja2) notes

- `report.py:15-16` — `autoescape=True` is set explicitly, not via
  `select_autoescape()`, because that helper's filename-sniffing wouldn't match
  `*.j2` — don't "simplify" this back.
- New template logic should be a Python helper registered on
  `_jinja_env.globals` (`report.py:50-53`), matching the existing
  `booking_url`/`status_label`/`short_date`/`availability_style` pattern — not
  inline Jinja logic or a custom filter.
- All row/cell rendering goes through the `cell()`/`book_cell()`/
  `show_table_head()`/`show_row()` macros in `index.html.j2`, reused at two
  call sites (the day-sections loop and the most-available loop) — new columns
  should go through these macros, not a hand-written `<td>` at one call site
  only.
- The row-click highlight script matches rows purely by `data-performance-id`
  on `<tr>` (set in `show_row`) — any future row-emitting path that bypasses
  `show_row()` would silently break highlighting.
- `.row-clicked` styling is split across three CSS rules (base background,
  `:hover`, and a `box-shadow` accent bar) that must be kept in sync if the
  highlight color ever changes.
- No template inheritance/partials — single flat file, macros defined inline
  at the top of `<body>`.

## Gotchas / invariants to know before touching this code

- `report.py:78-82` — `total_shows` is `len(result.shows)` directly, not a sum
  over `day_sections`, so it stays correct even if a future show lacks a
  matching day aggregate.
- `collector.py:149-151` — an empty result for *today* (offset 0) must never be
  treated as reaching the edge of Shaw's schedule (today's shows may have
  already screened); only offset ≥1 empty triggers the stop condition.
- `collector.py:180-183` — a show's `display_date` can be a day after the
  `day_str` it was fetched under (post-midnight showings); `run_scan` unions
  dates before building day aggregates so these don't vanish from by-day
  breakdowns.
- `seat_geometry.py:13-19` — row letters aren't reliable front/back indicators;
  "best seat" classification uses each performance's live `x`/`y` coordinates
  instead.
- `seat_geometry.py:42-48,65` — separately, column references can be
  non-numeric companion/handicap seat labels (e.g. `"H12"`); `_compress_row`
  excludes these from numeric-range compression (`column.isdigit()`) and lists
  them individually.
- `persistence.py:11-13,24` — `load_scan_result_json` calls `_artifact_path`,
  which unconditionally `mkdir`s `ARTIFACTS_DIR` even on a read path — running
  `report` before ever running `scan` silently creates an empty `artifacts/`
  dir before failing with `FileNotFoundError`.
- `config.py:48` vs `report.py:12` — `ARTIFACTS_DIR = Path("artifacts")` is
  resolved relative to the process's cwd, while the templates dir is resolved
  relative to the package's install location. Running `main.py` from outside
  the repo root silently reads/writes `artifacts/` in the wrong place while
  template loading keeps working fine — easy to misdiagnose as a template bug.
- `stats.py:19-20,68` — a show with zero seats in `{AV,SO,BL,OH}` (empty
  layout, or every seat status unknown) gets `availability_pct = 0.0`, which
  `aggregate_day`'s `sold_out_show_count` check (`== 0.0`) can't distinguish
  from a legitimately sold-out show — missing seat data silently reads as
  "sold out."
- `stats.py:67` — `avg_availability_pct` is an unweighted mean of per-show
  percentages, not weighted by `total_seats` — a 10-seat show and a 500-seat
  show count equally toward a day's average.
- `report.py:174-178` — the explicit `.astimezone(config.SGT)` swap exists
  purely so `strftime("%Z")` prints `"SGT"` instead of a generic UTC offset.
- `report.py:42-47` — the availability-gradient alpha is deliberately capped at
  0.28, not 1.0 — washed-out green at 100% availability is intentional.
- `api_client.py:49-88` — `>=500` responses retry with backoff; `>=400` fails
  immediately with no retry — don't "fix" perceived flakiness around 4xx.
  Separately, `_throttle()` (`api_client.py:58,69,91-93`) fires after *every*
  attempt, success or failure, in addition to the backoff sleep on retry — a
  retried request waits throttle *plus* backoff, not backoff alone.
- `config.py:10-15` — `locationBrand=2` is the IMAX filter in the fixed
  show-times query params; editing `config.py` without knowing this could
  silently broaden the scan beyond IMAX.
- `collector.py:14-15` — two module-level mutable sets dedup "unknown status
  code" log lines *per process*, not per scan — a gotcha if tests share a
  process and expect log output to reset.
