from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeatElement:
    row: str
    column: str
    status_code: str
    x: float
    y: float


@dataclass
class ShowTime:
    performance_id: int
    movie_title: str
    display_date: str
    display_time: str
    location_id: int
    location_venue_id: int
    location_venue_name: str
    seating_status: str


@dataclass
class ShowStats:
    performance_id: int
    movie_title: str
    display_date: str
    display_time: str
    venue_name: str
    api_seating_status: str
    total_seats: int
    available: int
    sold: int
    blocked: int
    on_hold: int
    unknown: int
    unknown_codes: dict[str, int]
    availability_pct: float
    best_seats_available: list[str]
    anomaly: str | None


@dataclass
class DayAggregate:
    date: str
    show_count: int
    total_seats: int
    total_available: int
    total_sold: int
    total_blocked: int
    total_on_hold: int
    total_unknown: int
    avg_availability_pct: float
    sold_out_show_count: int


@dataclass
class FailedCall:
    kind: str  # "show_times" | "layouts"
    identifier: str
    error: str
    timestamp: str


@dataclass
class ScanResult:
    scan_started_at: str
    scan_ended_at: str
    dates_scanned: list[str]
    stop_reason: str  # "reached_max_days" | "empty_date_hit"
    shows: list[ShowStats] = field(default_factory=list)
    day_aggregates: list[DayAggregate] = field(default_factory=list)
    failed_calls: list[FailedCall] = field(default_factory=list)
