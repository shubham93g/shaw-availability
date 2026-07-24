from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from shaw_availability import config, persistence
from shaw_availability.models import DayAggregate, FailedCall, ScanResult, ShowStats


class SaveLoadScanResultRoundTripTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._original_artifacts_dir = config.ARTIFACTS_DIR
        config.ARTIFACTS_DIR = Path(self._tmpdir.name)
        self.addCleanup(setattr, config, "ARTIFACTS_DIR", self._original_artifacts_dir)

    def test_load_reconstructs_saved_scan_result(self):
        original = ScanResult(
            scan_started_at=1784995554,
            scan_ended_at=1784995567,
            dates_scanned=["2026-07-23"],
            stop_reason="reached scan limit",
            shows=[
                ShowStats(
                    performance_id=513005,
                    movie_title="Test Movie",
                    display_date="2026-07-23",
                    display_time="9:15 AM",
                    venue_name="Lido IMAX",
                    api_seating_status="AV",
                    total_seats=413,
                    available=135,
                    sold=268,
                    blocked=10,
                    on_hold=0,
                    unknown=0,
                    unknown_codes={},
                    availability_pct=32.68,
                    best_seats_available=[],
                )
            ],
            day_aggregates=[
                DayAggregate(
                    date="2026-07-23",
                    show_count=20,
                    total_seats=4660,
                    total_available=1454,
                    total_sold=3069,
                    total_blocked=134,
                    total_on_hold=3,
                    total_unknown=0,
                    avg_availability_pct=34.07,
                    sold_out_show_count=0,
                )
            ],
            failed_calls=[
                FailedCall(
                    kind="layouts",
                    identifier="123",
                    error="timeout",
                    timestamp=1784995560,
                )
            ],
        )

        persistence.save_scan_result_json(original)
        loaded = persistence.load_scan_result_json()

        self.assertEqual(loaded, original)


if __name__ == "__main__":
    unittest.main()
