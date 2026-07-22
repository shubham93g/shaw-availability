from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .models import ScanResult


def save_scan_result_json(result: ScanResult) -> Path:
    path = Path("scan_result.json")
    with path.open("w") as f:
        json.dump(dataclasses.asdict(result), f, indent=2)
    return path


