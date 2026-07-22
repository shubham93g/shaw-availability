from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from . import config
from .models import ScanResult


def save_scan_result_json(result: ScanResult) -> Path:
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.ARTIFACTS_DIR / "scan_result.json"
    with path.open("w") as f:
        json.dump(dataclasses.asdict(result), f, indent=2)
    return path


