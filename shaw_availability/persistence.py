from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from . import config
from .models import (
    DayAggregate,
    FailedCall,
    History,
    HistorySnapshot,
    PerformanceHistory,
    ScanResult,
    ShowStats,
)


def _artifact_path(filename: str) -> Path:
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return config.ARTIFACTS_DIR / filename


def save_scan_result_json(result: ScanResult) -> Path:
    path = _artifact_path(config.SCAN_RESULT_FILENAME)
    with path.open("w") as f:
        json.dump(dataclasses.asdict(result), f, indent=2)
    return path


def load_scan_result_json() -> ScanResult:
    path = _artifact_path(config.SCAN_RESULT_FILENAME)
    data = json.loads(path.read_text())
    return ScanResult(
        scan_started_at=data["scan_started_at"],
        scan_ended_at=data["scan_ended_at"],
        dates_scanned=data["dates_scanned"],
        stop_reason=data["stop_reason"],
        shows=[ShowStats(**s) for s in data["shows"]],
        day_aggregates=[DayAggregate(**d) for d in data["day_aggregates"]],
        failed_calls=[FailedCall(**f) for f in data["failed_calls"]],
    )


def save_history_json(history: History) -> Path:
    path = _artifact_path(config.HISTORY_FILENAME)
    with path.open("w") as f:
        json.dump(dataclasses.asdict(history), f, indent=2)
    return path


def load_history_json() -> History:
    path = _artifact_path(config.HISTORY_FILENAME)
    # Unlike load_scan_result_json, a missing file is expected here: the
    # very first scan ever run has no prior history.json to merge into.
    if not path.exists():
        return History()
    data = json.loads(path.read_text())
    return History(
        performances=[
            PerformanceHistory(
                performance_id=p["performance_id"],
                snapshots=[HistorySnapshot(**s) for s in p["snapshots"]],
            )
            for p in data["performances"]
        ]
    )


def save_report_html(html: str) -> Path:
    path = _artifact_path(config.REPORT_HTML_FILENAME)
    path.write_text(html)
    return path

