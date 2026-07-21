from __future__ import annotations

import csv
import dataclasses
import json
from datetime import datetime
from pathlib import Path

from .models import ScanResult


def make_run_dir(base_dir: Path, timestamp: datetime) -> Path:
    run_dir = base_dir / timestamp.strftime("%Y%m%dT%H%M%S+0800")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_scan_result_json(result: ScanResult, run_dir: Path) -> Path:
    path = run_dir / "scan_result.json"
    with path.open("w") as f:
        json.dump(dataclasses.asdict(result), f, indent=2)
    return path


def save_shows_csv(result: ScanResult, run_dir: Path) -> Path:
    path = run_dir / "shows.csv"
    _write_dataclass_csv(path, result.shows)
    return path


def save_days_csv(result: ScanResult, run_dir: Path) -> Path:
    path = run_dir / "days.csv"
    _write_dataclass_csv(path, result.day_aggregates)
    return path


def append_history_csv(result: ScanResult, base_dir: Path) -> Path:
    path = base_dir / "history_shows.csv"
    is_new_file = not path.exists()

    rows = []
    for show in result.shows:
        row = dataclasses.asdict(show)
        row["unknown_codes"] = json.dumps(row["unknown_codes"])
        row["best_seats_available"] = json.dumps(row["best_seats_available"])
        row["scanned_at"] = result.scan_started_at
        rows.append(row)

    if not rows:
        return path

    fieldnames = list(rows[0].keys())
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new_file:
            writer.writeheader()
        writer.writerows(rows)
    return path


def _write_dataclass_csv(path: Path, items: list) -> None:
    if not items:
        path.write_text("")
        return

    rows = []
    for item in items:
        row = dataclasses.asdict(item)
        if "unknown_codes" in row:
            row["unknown_codes"] = json.dumps(row["unknown_codes"])
        if "best_seats_available" in row:
            row["best_seats_available"] = json.dumps(row["best_seats_available"])
        rows.append(row)

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
