#!/usr/bin/env bash
set -euo pipefail

GH=/opt/homebrew/bin/gh
REPO=shubham93g/shaw-availability
WORKFLOW=scan.yml

log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" "$1"
}

log "triggering $WORKFLOW"
if "$GH" workflow run "$WORKFLOW" --repo "$REPO"; then
  log "triggered successfully"
else
  status=$?
  log "trigger failed (exit $status)"
  exit "$status"
fi
