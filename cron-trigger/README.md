# shaw-availability-cron

A Cloudflare Worker that replaces GitHub Actions' native `schedule: cron`.
Hourly, 7am-11pm Singapore time, it calls GitHub's `workflow_dispatch` API to kick off
`../.github/workflows/scan.yml`. GitHub's own schedule cron can drift or get
silently suspended after 60 days of repo inactivity; a Worker on a Cron
Trigger doesn't have either problem and doesn't depend on any local machine
being awake.

## One-time setup

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
   - Resource owner: `shubham93g`
   - Repository access: **Only select repositories** → `shaw-availability`
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

## Verifying it works

- After `wrangler deploy`, the Cloudflare dashboard (Workers & Pages →
  `shaw-availability-cron` → Triggers) should list the `0 0-15,23 * * *`
  Cron Trigger (hourly, 7am-11pm Singapore time / UTC 23:00 and 00:00-15:00).
- To fire a test run without waiting for the schedule, use the dashboard's
  "Trigger Cron Trigger" button under the Triggers tab, or run locally:
  ```bash
  wrangler dev
  # in another terminal:
  curl "http://localhost:8787/__scheduled?cron=0+0-15,23+*+*+*"
  ```
- Either way, check the repo's Actions tab — a new `scan.yml` run should
  start within a few seconds.

## Changing the schedule

Edit the `crons` array in `wrangler.toml`, then `wrangler deploy` again.

## Viewing logs

`[observability]` in `wrangler.toml` persists invocation logs (not just live
tailing), viewable at Workers & Pages → `shaw-availability-cron` → Logs in
the Cloudflare dashboard — each entry includes whether the GitHub dispatch
call succeeded or threw. For live tailing while testing, `wrangler tail`
also works but only shows events from when you start it.
