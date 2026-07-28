from __future__ import annotations

from .models import History, HistorySnapshot, PerformanceHistory, ScanResult


def merge_snapshot(history: History, result: ScanResult) -> History:
    # Prune-by-construction: only performance_ids present in result.shows
    # are iterated, so anything that dropped out of the latest scan
    # (screened, or scrolled past the scan window) is dropped.
    existing_by_id = {p.performance_id: p for p in history.performances}
    seen_ids = {show.performance_id for show in result.shows}

    merged: list[PerformanceHistory] = []
    for show in result.shows:
        existing = existing_by_id.get(show.performance_id)
        snapshots = list(existing.snapshots) if existing else []
        snapshots.append(
            HistorySnapshot(
                scan_ended_at=result.scan_ended_at,
                availability_pct=show.availability_pct,
            )
        )
        merged.append(
            PerformanceHistory(performance_id=show.performance_id, snapshots=snapshots)
        )

    if result.failed_calls:
        # A scan with any failed calls — a whole day's show_times listing,
        # or one performance's layout fetch — can't tell "this performance
        # genuinely screened or fell out of scope" apart from "we just
        # failed to observe it this cycle" for whatever's missing from
        # result.shows. Keep those rather than pruning them, and let a
        # later clean scan prune them instead: losing a show's entire trend
        # history to one transient API hiccup is worse than it lingering a
        # cycle longer than the eager-prune rule intends.
        for performance_id, existing in existing_by_id.items():
            if performance_id not in seen_ids:
                merged.append(existing)

    return History(performances=merged)
