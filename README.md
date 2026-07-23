# Shaw IMAX Seat-Availability Scanner

[![Shaw IMAX Availability Scan](https://github.com/shubham93g/shaw-availability/actions/workflows/scan.yml/badge.svg?branch=main)](https://github.com/shubham93g/shaw-availability/actions/workflows/scan.yml)
[![Deploy Shaw IMAX Availability Report](https://github.com/shubham93g/shaw-availability/actions/workflows/deploy.yml/badge.svg?branch=main)](https://github.com/shubham93g/shaw-availability/actions/workflows/deploy.yml)

Scans Shaw Theatres' internal IMAX booking API to see how full upcoming
IMAX showtimes are, across all venues, over the next two weeks.

## What it does

1. Calls `get_show_times` once per date, starting today, for up to 14 days —
   stopping early the first time a date *after today* comes back with zero
   showtimes (the edge of Shaw's published schedule). Today's own count is
   never used to stop the scan, since by the time this runs today's
   showtimes may have already screened.
2. For every showtime found, calls `get_layouts` once to pull the full seat
   map for that performance.
3. Computes seat-availability stats per show, per day, and for the whole
   scan — including the top 10 most-available showtimes across the whole
   scan.
4. Persists results to disk so availability can be tracked over time.
5. Logs progress in real time (which date/showtime it's on) at the default
   log level, so a long scan doesn't look hung — pass `--verbose` for
   full HTTP-level debug logging.

Steps 1–2 and 4 run under the `scan` subcommand; step 3's console report
and `index.html` are built separately by the `report` subcommand from
whatever `scan` last saved — see Usage below.

## Usage

```bash
pip install -r requirements.txt
python main.py scan                        # default: 14 days starting today
python main.py scan --days 3               # scan a shorter window
python main.py scan --start-date 2026-08-01
python main.py scan --verbose
python main.py report                      # build the report from scan_result.json
python main.py report --verbose
```

## APIs used

- `GET https://shaw.sg/internal/get_show_times?date=YYYY-MM-DD&movieId=0&locationId=0&promotionId=0&locationBrand=2`
  — all IMAX showtimes for a date, across every Shaw IMAX venue.
- `GET https://shaw.sg/internal/get_layouts?performanceId=<id>`
  — the full seat map for one showtime.

Both are undocumented internal endpoints (used respectfully: sequential
calls only, throttled 0.5s apart, small `--days` recommended for quick
checks). Each request has a 10s timeout; network errors and HTTP 5xx
responses retry twice with exponential backoff, while HTTP 4xx responses
fail immediately with no retry.

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
literal zero availability.

## Output

`scan` writes `scan_result.json`; `report` reads it and writes `index.html`
(rendered from a Jinja2 template). Both land in `artifacts/` (gitignored),
overwriting the previous run's output.

## Report page

A checkbox per venue lets you narrow the report down to specific cinemas;
all venues are checked by default. The selection is remembered across visits
via `localStorage`, so it persists between page loads on the same browser.

Each show's row in `index.html` has a "Book" link that opens Shaw's own booking
page for that showtime in a new tab. Clicking it also highlights that row (and
its duplicate, if the same show also appears in the "Top Most Available"
table) for the rest of that page view, so you can see at a glance which shows
you've already looked at while scanning the report — this highlight resets
the next time the page is loaded.

"Top Most Available" is computed entirely client-side from whichever venues
are currently checked: unchecking a venue re-ranks the list from the
remaining selected venues rather than just hiding rows from a fixed list.
Each day section's show count and average availability are recomputed the
same way. All of this — the venue filter, the row highlight, and the
Most Available ranking — is plain inline JavaScript with no build step.

## Scheduling

Scanning and publishing are split across two workflows:

- **`.github/workflows/scan.yml`** first runs the test suite
  (`python -m unittest discover -s tests -v`) — a failing suite blocks the
  rest of the run, so a bad change is never scanned or deployed, though
  this only happens when scan.yml itself fires, not on every pull request.
  It then runs `scan` then `report`, writing `scan_result.json` and
  `index.html` to a local `artifacts/` folder, and publishes both as assets
  on a single reused GitHub Release tagged `latest` (overwritten every run
  — it's a snapshot, not a versioned release). It only reacts to
  `workflow_dispatch` — it no longer self-schedules. Runs are triggered
  externally — every 30 minutes from 7:00am to 11:00pm SGT, and every 2
  hours overnight (11:00pm, 1:00am, 3:00am, 5:00am, 7:00am SGT) — by a
  Cloudflare Worker on a Cron Trigger (see [Cron trigger](#cron-trigger-cloudflare-worker)
  below) that calls GitHub's `workflow_dispatch` API. After publishing, it
  dispatches `deploy.yml` itself (`gh workflow run deploy.yml`), unless run
  with its `deploy` input set to `false`.
- **`.github/workflows/deploy.yml`** downloads just the `index.html` asset
  from the `latest` release (`scan_result.json` is published to the release
  but never deployed) and publishes it to Cloudflare Pages. It only reacts
  to `workflow_dispatch` — either the one scan.yml fires automatically after
  a successful scan, or a manual run to retry a failed deploy. It always
  re-fetches whatever `index.html` is currently in the `latest` release, so
  a retry needs no extra bookkeeping about which run it came from.
- **`.github/workflows/pages-redirect.yml`** is not part of this cadence at
  all. It publishes a static redirect page to GitHub Pages and is only run
  manually, once — see [Hosting](#hosting) below.

None of scan.yml, deploy.yml, or the Cloudflare Worker send any kind of
failure notification — a missed or failed run is only discoverable by
checking the GitHub Actions or Cloudflare dashboards by hand.

GitHub Actions' own `schedule: cron` was tried before the current Cloudflare
Worker and dropped: schedules can drift, and are silently suspended after 60
days of repo inactivity. A Worker on a Cron Trigger doesn't depend on any
machine being awake and has neither of those problems.

## Cron trigger (Cloudflare Worker)

`cron-trigger/` is a small Cloudflare Worker that replaces GitHub Actions'
native `schedule: cron` (see [Scheduling](#scheduling) above for why). Every
30 minutes from 7:00am to 11:00pm SGT, and every 2 hours overnight (11:00pm,
1:00am, 3:00am, 5:00am, 7:00am SGT), it calls GitHub's `workflow_dispatch`
API to kick off `scan.yml`. Its dispatch target branch is hardcoded to `main`
(`GITHUB_REF` in `cron-trigger/wrangler.toml`).

**One-time setup:**

1. Install `wrangler` (Cloudflare's CLI), if you don't have it:
   ```bash
   npm install -g wrangler
   ```
2. Log in (opens a browser to authorize against your Cloudflare account —
   create a free account first if you don't have one):
   ```bash
   wrangler login
   ```
3. Create a GitHub **fine-grained personal access token**:
   https://github.com/settings/personal-access-tokens/new
   - Resource owner: the repo's owner
   - Repository access: **Only select repositories** → this repo
   - Permissions: **Actions → Read and write** (nothing else needed)
4. Store the token as a Worker secret (paste the PAT when prompted; it is
   never written to disk in this repo):
   ```bash
   cd cron-trigger
   wrangler secret put GITHUB_TOKEN
   ```
5. Deploy:
   ```bash
   wrangler deploy
   ```

**Verifying it works:**

- After `wrangler deploy`, the Cloudflare dashboard (Workers & Pages →
  `shaw-availability-cron` → Triggers) should list two Cron Triggers —
  `0 15,17,19,21 * * *` and `0,30 23,0-14 * * *` — which together fire every
  30 minutes from 7:00am to 10:30pm SGT, and every 2 hours overnight (Cron
  Triggers run in UTC; SGT is UTC+8 with no DST, so the daytime window is
  23:00 the previous day through 14:30 UTC, and the overnight triggers land
  at 15:00, 17:00, 19:00, and 21:00 UTC).
- To fire a test run without waiting for the schedule, use the dashboard's
  "Trigger Cron Trigger" button under the Triggers tab, or run locally:
  ```bash
  wrangler dev
  # in another terminal:
  curl "http://localhost:8787/__scheduled?cron=0%2C30+23%2C0-14+*+*+*"
  ```
- Either way, check the repo's Actions tab — a new `scan.yml` run should
  start within a few seconds.

**Changing the schedule:** edit the `crons` array in
`cron-trigger/wrangler.toml`, then `wrangler deploy` again.

**Viewing logs:** `[observability]` in `wrangler.toml` persists invocation
logs (not just live tailing), viewable at Workers & Pages →
`shaw-availability-cron` → Logs in the Cloudflare dashboard — each entry
includes whether the GitHub dispatch call succeeded or threw. For live
tailing while testing, `wrangler tail` also works but only shows events from
when you start it.

## Hosting

Cloudflare Pages (`<CLOUDFLARE_PROJECT_NAME>.pages.dev` — a name chosen at
project creation, not tied to any account identity) is the live report,
updated by `deploy.yml` on every scan. GitHub Pages
(`<owner>.github.io/shaw-availability/`) is a static redirect to that URL:
`pages-redirect.yml` publishes a small page there once
(meta-refresh + JS `location.replace`, preserving any query string) and
isn't re-run on the recurring schedule — only if the Cloudflare project
itself ever changes.

The project name is a single GitHub Actions repo **variable**,
`CLOUDFLARE_PROJECT_NAME`, referenced by both `deploy.yml` (the
`wrangler pages deploy` command) and `pages-redirect.yml` (to build the
redirect target URL) — so renaming the Cloudflare project only means
updating it in one place.

One-time setup for the Cloudflare Pages side:
1. Create the Pages project: `wrangler pages project create
   shaw-availability --production-branch=main` (or via the dashboard).
2. Create a Cloudflare API token scoped to **Cloudflare Pages — Edit**:
   https://dash.cloudflare.com/profile/api-tokens
3. Add it, plus the Cloudflare account ID, as GitHub Actions repo secrets:
   `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
4. Add the project name as a GitHub Actions repo variable (Settings →
   Secrets and variables → Actions → Variables), or via `gh`:
   ```bash
   gh variable set CLOUDFLARE_PROJECT_NAME --body "shaw-availability"
   ```

This covers publishing only. Scans won't fire on a schedule until the
[Cron trigger](#cron-trigger-cloudflare-worker) Worker is also set up — it
needs its own one-time setup and a separate GitHub PAT, not the Cloudflare
credentials above.
