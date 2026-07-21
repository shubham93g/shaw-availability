from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests

from . import api_client, config, stats
from .models import FailedCall, ScanResult, SeatElement, ShowStats, ShowTime

logger = logging.getLogger(__name__)

_logged_unknown_seating_statuses: set[str] = set()
_logged_unknown_seat_statuses: set[str] = set()


@dataclass
class DayFetchResult:
    shows: list[ShowTime]
    call_succeeded: bool


def parse_show_times(raw_movies: list[dict]) -> list[ShowTime]:
    shows: list[ShowTime] = []
    for movie in raw_movies:
        if not isinstance(movie, dict):
            logger.warning("skipping malformed movie entry: %r", movie)
            continue
        movie_title = movie.get("primaryTitle", "")
        for raw_show in movie.get("showTimes", []):
            if not isinstance(raw_show, dict):
                logger.warning("skipping malformed showtime entry: %r", raw_show)
                continue
            try:
                seating_status = raw_show.get("seatingStatus", "")
                if (
                    seating_status not in config.KNOWN_SEATING_STATUSES
                    and seating_status not in _logged_unknown_seating_statuses
                ):
                    _logged_unknown_seating_statuses.add(seating_status)
                    logger.warning("unknown seatingStatus encountered: %r", seating_status)

                shows.append(
                    ShowTime(
                        performance_id=raw_show["performanceId"],
                        movie_title=movie_title,
                        display_date=raw_show.get("displayDate", ""),
                        display_time=raw_show.get("displayTime", ""),
                        location_id=raw_show.get("locationId", -1),
                        location_venue_id=raw_show.get("locationVenueId", -1),
                        location_venue_name=raw_show.get("locationVenueName", ""),
                        seating_status=seating_status,
                    )
                )
            except KeyError as exc:
                logger.warning("skipping showtime missing required field %s: %r", exc, raw_show)
    return shows


def parse_seat_elements(raw_elements: list[dict]) -> list[SeatElement]:
    elements: list[SeatElement] = []
    for raw in raw_elements:
        if not isinstance(raw, dict):
            logger.warning("skipping malformed layout element: %r", raw)
            continue
        if raw.get("elementCategoryCode") != "SEAT":
            continue
        status_code = raw.get("elementStatusCodeCurrent", "")
        if (
            status_code not in config.KNOWN_SEAT_STATUSES
            and status_code not in _logged_unknown_seat_statuses
        ):
            _logged_unknown_seat_statuses.add(status_code)
            logger.warning("unknown elementStatusCodeCurrent encountered: %r", status_code)

        elements.append(
            SeatElement(
                row=raw.get("rowReference", ""),
                column=raw.get("columnReference", ""),
                status_code=status_code,
            )
        )
    return elements


def collect_day(
    session: requests.Session, day_str: str, failed_calls: list[FailedCall]
) -> DayFetchResult:
    try:
        raw = api_client.get_show_times(session, day_str)
    except api_client.ApiError as exc:
        failed_calls.append(
            FailedCall(
                kind="show_times",
                identifier=day_str,
                error=str(exc),
                timestamp=_now_iso(),
            )
        )
        return DayFetchResult(shows=[], call_succeeded=False)

    return DayFetchResult(shows=parse_show_times(raw), call_succeeded=True)


def collect_show_stats(
    session: requests.Session, show: ShowTime, failed_calls: list[FailedCall]
) -> ShowStats | None:
    try:
        raw = api_client.get_layouts(session, show.performance_id)
    except api_client.ApiError as exc:
        failed_calls.append(
            FailedCall(
                kind="layouts",
                identifier=str(show.performance_id),
                error=str(exc),
                timestamp=_now_iso(),
            )
        )
        return None

    elements = parse_seat_elements(raw)
    return stats.compute_show_stats(show, elements)


def run_scan(
    session: requests.Session,
    start_date: date,
    max_days: int = config.SCAN_DAYS_DEFAULT,
) -> ScanResult:
    scan_started_at = _now_iso()
    failed_calls: list[FailedCall] = []
    dates_scanned: list[str] = []
    shows: list[ShowStats] = []
    stop_reason = "reached_max_days"

    logger.info("Starting scan: %d day(s) from %s", max_days, start_date.isoformat())

    for offset in range(max_days):
        current_date = start_date + timedelta(days=offset)
        day_str = current_date.isoformat()

        logger.info("[%d/%d] %s: fetching showtimes...", offset + 1, max_days, day_str)
        fetch = collect_day(session, day_str, failed_calls)
        dates_scanned.append(day_str)

        if fetch.call_succeeded and not fetch.shows:
            logger.info("%s: no showtimes found — stopping scan", day_str)
            stop_reason = "empty_date_hit"
            break

        if not fetch.call_succeeded:
            continue

        logger.info("%s: %d showtime(s) found", day_str, len(fetch.shows))
        for i, show in enumerate(fetch.shows, start=1):
            logger.info(
                "  [%d/%d] fetching seat layout for performanceId=%s (%s %s)",
                i,
                len(fetch.shows),
                show.performance_id,
                show.location_venue_name,
                show.display_time,
            )
            show_stats = collect_show_stats(session, show, failed_calls)
            if show_stats is not None:
                shows.append(show_stats)

    logger.info(
        "Scan complete: %d showtime(s) collected, %d failed call(s)",
        len(shows),
        len(failed_calls),
    )

    day_aggregates = [
        stats.aggregate_day(d, [s for s in shows if s.display_date == d])
        for d in dates_scanned
    ]

    return ScanResult(
        scan_started_at=scan_started_at,
        scan_ended_at=_now_iso(),
        dates_scanned=dates_scanned,
        stop_reason=stop_reason,
        shows=shows,
        day_aggregates=day_aggregates,
        failed_calls=failed_calls,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
