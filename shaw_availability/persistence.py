from __future__ import annotations

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


