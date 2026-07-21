"""
Drives the Shaw IMAX scan from this machine every 2 hours, since GitHub
Actions cron scheduling has proven unreliable.

Each cycle: bump `.trigger` and git push it to `main`. The push (via
`.github/workflows/scan.yml`'s `on: push: paths: ['.trigger']` trigger) makes
GitHub Actions run the scan and publish the report to the `gh-pages` branch.

Usage:
    python scripts/trigger_scan.py
"""

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIGGER_FILE = REPO_ROOT / ".trigger"
CYCLE_SECONDS = 2 * 60 * 60


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {message}", flush=True)


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)


def current_branch() -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def trigger_scan() -> None:
    branch = current_branch()
    if branch != "main":
        log(f"refusing to trigger: repo is on branch '{branch}', not 'main'")
        return

    TRIGGER_FILE.write_text(datetime.now(timezone.utc).isoformat() + "\n")

    steps = [
        ["git", "add", ".trigger"],
        ["git", "commit", "-m", f"trigger: scan {datetime.now(timezone.utc).isoformat()}"],
        ["git", "pull", "--rebase", "origin", "main"],
        ["git", "push", "origin", "main"],
    ]
    for step in steps:
        result = run(step)
        if result.returncode != 0:
            log(f"trigger step failed: {' '.join(step)}\n{result.stdout}{result.stderr}")
            return

    log("triggered scan via push to main")


def main() -> None:
    log(f"starting trigger loop, cycling every {CYCLE_SECONDS // 3600}h")
    try:
        while True:
            trigger_scan()
            log(f"sleeping {CYCLE_SECONDS // 3600}h until next cycle")
            time.sleep(CYCLE_SECONDS)
    except KeyboardInterrupt:
        log("stopped by user")


if __name__ == "__main__":
    main()
