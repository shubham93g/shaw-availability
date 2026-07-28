from __future__ import annotations

import unittest

from shaw_availability.history import merge_snapshot
from shaw_availability.models import (
    FailedCall,
    History,
    HistorySnapshot,
    PerformanceHistory,
    ScanResult,
    ShowStats,
)


def _show(performance_id: int, availability_pct: float) -> ShowStats:
    return ShowStats(
        performance_id=performance_id,
        movie_title="Test Movie",
        display_date="2026-07-23",
        display_time="9:15 AM",
        venue_name="Lido IMAX",
        api_seating_status="AV",
        total_seats=413,
        available=100,
        sold=300,
        blocked=10,
        on_hold=3,
        unknown=0,
        unknown_codes={},
        availability_pct=availability_pct,
        best_seats_available=[],
    )


def _result(shows: list[ShowStats], scan_ended_at: int = 1784995567) -> ScanResult:
    return ScanResult(
        scan_started_at=1784995554,
        scan_ended_at=scan_ended_at,
        dates_scanned=["2026-07-23"],
        stop_reason="reached scan limit",
        shows=shows,
    )


class MergeSnapshotTest(unittest.TestCase):
    def test_merge_appends_new_snapshot_to_existing_performance_history(self):
        history = History(
            performances=[
                PerformanceHistory(
                    performance_id=513005,
                    snapshots=[HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0)],
                )
            ]
        )
        result = _result([_show(513005, 40.0)], scan_ended_at=1784995567)

        merged = merge_snapshot(history, result)

        self.assertEqual(len(merged.performances), 1)
        self.assertEqual(
            merged.performances[0].snapshots,
            [
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
            ],
        )

    def test_merge_adds_new_performance_not_previously_in_history(self):
        history = History(performances=[])
        result = _result([_show(513005, 40.0)])

        merged = merge_snapshot(history, result)

        self.assertEqual(len(merged.performances), 1)
        self.assertEqual(merged.performances[0].performance_id, 513005)
        self.assertEqual(len(merged.performances[0].snapshots), 1)

    def test_merge_prunes_performance_ids_not_present_in_latest_scan_result(self):
        history = History(
            performances=[
                PerformanceHistory(
                    performance_id=513005,
                    snapshots=[HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0)],
                ),
                PerformanceHistory(
                    performance_id=999999,
                    snapshots=[HistorySnapshot(scan_ended_at=1784995000, availability_pct=10.0)],
                ),
            ]
        )
        # 999999 has screened / dropped out of scope and is absent from this scan.
        result = _result([_show(513005, 40.0)])

        merged = merge_snapshot(history, result)

        self.assertEqual([p.performance_id for p in merged.performances], [513005])

    def test_merge_against_empty_history_and_empty_scan_result_returns_empty_history(self):
        merged = merge_snapshot(History(), _result([]))

        self.assertEqual(merged, History())

    def test_merge_keeps_previously_tracked_performance_absent_from_a_scan_with_failed_calls(self):
        history = History(
            performances=[
                PerformanceHistory(
                    performance_id=999999,
                    snapshots=[HistorySnapshot(scan_ended_at=1784995000, availability_pct=10.0)],
                )
            ]
        )
        # 999999's layout fetch (or its day's show_times call) failed this
        # cycle rather than it genuinely screening/falling out of scope, so
        # it should be kept rather than pruned.
        result = _result([_show(513005, 40.0)])
        result.failed_calls = [
            FailedCall(kind="layouts", identifier="999999", error="timeout", timestamp=1784995567)
        ]

        merged = merge_snapshot(history, result)

        ids = {p.performance_id for p in merged.performances}
        self.assertIn(999999, ids)
        self.assertIn(513005, ids)
        # The kept-but-unobserved performance's history is untouched, not
        # given a fabricated snapshot for data we don't actually have.
        kept = next(p for p in merged.performances if p.performance_id == 999999)
        self.assertEqual(len(kept.snapshots), 1)


if __name__ == "__main__":
    unittest.main()
