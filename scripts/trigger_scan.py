"""
Drives the Shaw IMAX scan from this machine every 2 hours, since GitHub
Actions cron scheduling has proven unreliable.

Normal cycle: bump `.trigger` and git push it to `main`. The push (via
`.github/workflows/scan.yml`'s `on: push: paths: ['.trigger']` trigger) makes
GitHub Actions run the actual scan and publish the report to the `gh-pages`
branch.

If that push fails for any reason (no network, GitHub outage, merge
conflict, ...), this script falls back to running the scan locally
(`main.py`) and publishing the generated report straight to `gh-pages`
itself, bypassing GitHub Actions entirely for that cycle.

Usage:
    python scripts/trigger_scan.py                 # run forever, every 2 hours
    python scripts/trigger_scan.py --force-fallback # run the fallback path once, for testing
"""

import argparse
import html
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIGGER_FILE = REPO_ROOT / ".trigger"
CYCLE_SECONDS = 2 * 60 * 60
SINGAPORE = ZoneInfo("Asia/Singapore")


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {message}", flush=True)


def run(args: list[str], cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def current_branch() -> str:
    result = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()


def try_trigger_push() -> bool:
    """Bump .trigger and push it to main. Returns True on success."""
    branch = current_branch()
    if branch != "main":
        log(f"refusing to trigger: repo is on branch '{branch}', not 'main'")
        return False

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
            return False

    log("triggered scan via push to main")
    return True


def build_report_html(report_text: str) -> str:
    generated = datetime.now(SINGAPORE).strftime("%Y-%m-%d %H:%M %Z")
    escaped = html.escape(report_text)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Shaw IMAX Availability</title></head><body>"
        "<h1>Shaw IMAX Availability Report</h1>"
        f"<p>Generated: {generated} (local fallback)</p>"
        f"<pre>{escaped}</pre></body></html>"
    )


def run_scan_locally() -> str:
    log("running scan locally: python main.py")
    result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def publish_to_gh_pages(index_html: str) -> bool:
    remote_has_branch = run(["git", "ls-remote", "--exit-code", "origin", "gh-pages"]).returncode == 0

    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp) / "gh-pages"
        if remote_has_branch:
            add = run(["git", "worktree", "add", str(worktree), "gh-pages"])
            if add.returncode != 0:
                log(f"failed to add gh-pages worktree: {add.stderr}")
                return False
        else:
            add = run(["git", "worktree", "add", "--detach", str(worktree)])
            if add.returncode != 0:
                log(f"failed to add detached worktree: {add.stderr}")
                return False
            run(["git", "checkout", "--orphan", "gh-pages"], cwd=worktree)
            run(["git", "rm", "-rf", "."], cwd=worktree)

        (worktree / "index.html").write_text(index_html)

        commit_steps = [
            ["git", "add", "-A"],
            ["git", "commit", "-m", f"local fallback publish {datetime.now(timezone.utc).isoformat()}"],
            ["git", "push", "origin", "gh-pages"],
        ]
        ok = True
        for step in commit_steps:
            result = run(step, cwd=worktree)
            if result.returncode != 0:
                log(f"publish step failed: {' '.join(step)}\n{result.stdout}{result.stderr}")
                ok = False
                break

        run(["git", "worktree", "remove", "--force", str(worktree)])
        return ok


def run_fallback() -> None:
    log("running fallback: local scan + direct gh-pages publish")
    report_text = run_scan_locally()
    index_html = build_report_html(report_text)
    if publish_to_gh_pages(index_html):
        log("fallback publish succeeded")
    else:
        log("fallback publish FAILED")


def run_cycle(force_fallback: bool) -> None:
    if force_fallback or not try_trigger_push():
        run_fallback()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="skip the trigger push and run the local fallback once, for testing",
    )
    args = parser.parse_args()

    if args.force_fallback:
        run_cycle(force_fallback=True)
        return

    log(f"starting trigger loop, cycling every {CYCLE_SECONDS // 3600}h")
    try:
        while True:
            run_cycle(force_fallback=False)
            log(f"sleeping {CYCLE_SECONDS // 3600}h until next cycle")
            time.sleep(CYCLE_SECONDS)
    except KeyboardInterrupt:
        log("stopped by user")


if __name__ == "__main__":
    main()
