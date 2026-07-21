from __future__ import annotations

from collections import Counter

from . import config
from .models import DayAggregate, SeatElement, ShowStats, ShowTime


def compute_show_stats(show: ShowTime, elements: list[SeatElement]) -> ShowStats:
    available = sum(1 for e in elements if e.status_code == "AV")
    sold = sum(1 for e in elements if e.status_code == "SO")
    blocked = sum(1 for e in elements if e.status_code == "BL")
    on_hold = sum(1 for e in elements if e.status_code == "OH")
    unknown_codes = Counter(
        e.status_code for e in elements if e.status_code not in config.KNOWN_SEAT_STATUSES
    )
    unknown = sum(unknown_codes.values())

    denom = available + sold + blocked + on_hold
    availability_pct = (available / denom * 100) if denom else 0.0

    anomaly = _detect_anomaly(show.seating_status, available, availability_pct)

    return ShowStats(
        performance_id=show.performance_id,
        movie_title=show.movie_title,
        display_date=show.display_date,
        display_time=show.display_time,
        venue_name=show.location_venue_name,
        api_seating_status=show.seating_status,
        total_seats=len(elements),
        available=available,
        sold=sold,
        blocked=blocked,
        on_hold=on_hold,
        unknown=unknown,
        unknown_codes=dict(unknown_codes),
        availability_pct=availability_pct,
        anomaly=anomaly,
    )


def aggregate_day(date: str, shows: list[ShowStats]) -> DayAggregate:
    if not shows:
        return DayAggregate(
            date=date,
            show_count=0,
            total_seats=0,
            total_available=0,
            total_sold=0,
            total_blocked=0,
            total_on_hold=0,
            total_unknown=0,
            avg_availability_pct=0.0,
            sold_out_show_count=0,
        )

    return DayAggregate(
        date=date,
        show_count=len(shows),
        total_seats=sum(s.total_seats for s in shows),
        total_available=sum(s.available for s in shows),
        total_sold=sum(s.sold for s in shows),
        total_blocked=sum(s.blocked for s in shows),
        total_on_hold=sum(s.on_hold for s in shows),
        total_unknown=sum(s.unknown for s in shows),
        avg_availability_pct=sum(s.availability_pct for s in shows) / len(shows),
        sold_out_show_count=sum(1 for s in shows if s.availability_pct == 0.0),
    )


def summarize_scan(shows: list[ShowStats]) -> dict:
    return {
        "sold_out_shows": [s for s in shows if s.availability_pct == 0.0],
        "highest_availability_show": max(
            shows, key=lambda s: s.availability_pct, default=None
        ),
        "lowest_availability_show": min(
            shows, key=lambda s: s.availability_pct, default=None
        ),
        "anomalies": [s for s in shows if s.anomaly],
    }


def _detect_anomaly(api_status: str, available: int, availability_pct: float) -> str | None:
    # Note: seatingStatus=SO + nonzero AV seats is NOT flagged here — that's
    # expected. SO appears to mean "practically sold out" (a venue-side
    # threshold), not "zero seats remain": a live sample showed SO with 21
    # AV seats, all confined to the least desirable front rows.
    if api_status == "AV" and availability_pct == 0:
        return "api seatingStatus=AV but computed availability is 0%"
    return None
