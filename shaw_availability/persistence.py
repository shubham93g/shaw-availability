from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from . import config
from .models import ScanResult


def _artifact_path(filename: str) -> Path:
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return config.ARTIFACTS_DIR / filename


def save_scan_result_json(result: ScanResult) -> Path:
    path = _artifact_path("scan_result.json")
    with path.open("w") as f:
        json.dump(dataclasses.asdict(result), f, indent=2)
    return path


def save_report_txt(text: str) -> Path:
    path = _artifact_path("report.txt")
    path.write_text(text)
    return path


def save_report_html(html: str) -> Path:
    path = _artifact_path("index.html")
    path.write_text(html)
    return path

