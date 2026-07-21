#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.shubham93g.shaw-availability.trigger-scan.plist"
PLIST_NAME="$(basename "$PLIST_SRC")"
DEST="$HOME/Library/LaunchAgents/$PLIST_NAME"
LABEL="$(plutil -extract Label raw "$PLIST_SRC")"
DOMAIN="gui/$(id -u)"
TARGET="$DOMAIN/$LABEL"
LOG_FILE="$(plutil -extract StandardOutPath raw "$PLIST_SRC")"
LOG_LINES=5

# The wrapper script must live outside TCC-protected folders (Documents,
# Desktop, Downloads, ...) or launchd fails to exec it with "Operation not
# permitted" — so it's installed to Application Support, not run in place.
RUNNER_SRC="$SCRIPT_DIR/run-trigger.sh"
RUNNER_DEST="$HOME/Library/Application Support/shaw-availability/run-trigger.sh"

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  status    Show whether the agent is loaded and its last run state
  install   Copy the plist into ~/Library/LaunchAgents and load it
  update    Re-copy the plist (picks up any edits) and reload it
  stop      Unload the agent (won't run again until 'resume' or 'install')
  resume    Load the agent again after 'stop' (must already be installed)
EOF
}

cmd_status() {
  if launchctl print "$TARGET" >/dev/null 2>&1; then
    echo "Loaded: $TARGET"
    launchctl print "$TARGET" | grep -E "state = |last exit code = |path = "
  else
    echo "Not loaded: $TARGET"
    if [[ -f "$DEST" ]]; then
      echo "(installed at $DEST but not loaded — run '$(basename "$0") resume')"
    else
      echo "(not installed — run '$(basename "$0") install')"
    fi
  fi

  echo
  if [[ -f "$LOG_FILE" ]]; then
    echo "Last $LOG_LINES log lines ($LOG_FILE):"
    tail -n "$LOG_LINES" "$LOG_FILE"
  else
    echo "No log file yet at $LOG_FILE"
  fi
}

install_runner() {
  mkdir -p "$(dirname "$RUNNER_DEST")"
  cp "$RUNNER_SRC" "$RUNNER_DEST"
  chmod +x "$RUNNER_DEST"
}

cmd_install() {
  install_runner
  mkdir -p "$HOME/Library/LaunchAgents"
  cp "$PLIST_SRC" "$DEST"
  launchctl bootstrap "$DOMAIN" "$DEST"
  echo "Installed and started $LABEL"
}

cmd_update() {
  if [[ ! -f "$DEST" ]]; then
    echo "Not installed yet — installing instead" >&2
    cmd_install
    return
  fi
  install_runner
  cp "$PLIST_SRC" "$DEST"
  launchctl bootout "$TARGET" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$DEST"
  echo "Updated and reloaded $LABEL"
}

cmd_stop() {
  if launchctl bootout "$TARGET" 2>/dev/null; then
    echo "Stopped $LABEL"
  else
    echo "Already stopped (or not installed): $LABEL"
  fi
}

cmd_resume() {
  if [[ ! -f "$DEST" ]]; then
    echo "Not installed — run '$(basename "$0") install' first" >&2
    exit 1
  fi
  launchctl bootstrap "$DOMAIN" "$DEST"
  echo "Resumed $LABEL"
}

case "${1:-}" in
  status) cmd_status ;;
  install) cmd_install ;;
  update) cmd_update ;;
  stop) cmd_stop ;;
  resume) cmd_resume ;;
  *) usage; exit 1 ;;
esac
