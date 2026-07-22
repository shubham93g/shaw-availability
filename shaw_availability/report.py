from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

import jinja2

from . import config, stats
from .models import FailedCall, ScanResult, ShowStats

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    autoescape=True,  # explicit, rather than relying on select_autoescape's
                      # filename-extension sniffing (which wouldn't match "*.j2")
)


def _with_weekday(date_str: str) -> str:
    weekday = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a")
    return f"{date_str} ({weekday})"


def _short_date_label(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.strftime('%a')}, {dt.day} {dt.strftime('%b')}"


def _time_sort_key(time_str: str) -> time:
    return datetime.strptime(time_str, "%I:%M %p").time()


def _status_label(code: str) -> str:
    return config.SHOW_STATUS_LABELS.get(code, code)


def _booking_url(performance_id: int) -> str:
    return config.BOOKING_URL_TEMPLATE.format(performance_id=performance_id)


def _availability_style(pct: float) -> str:
    # A soft green tint scaling with availability, not a saturated color:
    # alpha is capped well below 1 so even 100% availability stays a muted
    # tint over white rather than solid green.
    alpha = max(0.0, min(pct, 100.0)) / 100 * 0.28
    return f"background-color: rgba(46, 125, 50, {alpha:.2f})"


_jinja_env.globals["booking_url"] = _booking_url
_jinja_env.globals["status_label"] = _status_label
_jinja_env.globals["short_date"] = _short_date_label
_jinja_env.globals["availability_style"] = _availability_style


@dataclass
class DaySection:
    date: str
    shows: list[ShowStats]
    show_count: int
    avg_availability_pct: float


@dataclass
class ReportData:
    generated_at: str
    dates_scanned: list[str]
    stop_reason: str
    total_shows: int
    day_sections: list[DaySection] = field(default_factory=list)
    most_available_shows: list[ShowStats] = field(default_factory=list)
    failed_calls: list[FailedCall] = field(default_factory=list)


def build_report(result: ScanResult) -> ReportData:
    summary = stats.summarize_scan(result.shows)

    # total_shows is len(result.shows) directly, not a sum over day_sections:
    # collector.run_scan unions in any date a show's display_date points to,
    # but keeping this as a direct count (rather than relying on that
    # invariant) means the total stays right even if some future ScanResult
    # has a show without a matching day aggregate.
    day_sections = []
    for day in result.day_aggregates:
        if day.show_count == 0:
            continue
        shows_that_day = sorted(
            (s for s in result.shows if s.display_date == day.date),
            key=lambda s: (s.venue_name, _time_sort_key(s.display_time)),
        )
        day_sections.append(
            DaySection(
                date=day.date,
                shows=shows_that_day,
                show_count=day.show_count,
                avg_availability_pct=day.avg_availability_pct,
            )
        )

    return ReportData(
        generated_at=result.scan_ended_at,
        dates_scanned=result.dates_scanned,
        stop_reason=result.stop_reason,
        total_shows=len(result.shows),
        day_sections=day_sections,
        most_available_shows=summary["most_available_shows"],
        failed_calls=result.failed_calls,
    )


def _format_show_line(show: ShowStats, movie_width: int, venue_width: int) -> str:
    unknown_suffix = f"UNK {show.unknown:3d}  " if show.unknown else "  "
    best_seats_str = (
        ", ".join(show.best_seats_available) if show.best_seats_available else "-"
    )
    return (
        f"  {show.movie_title:<{movie_width}} "
        f"{show.venue_name:<{venue_width}}  {show.display_time:>8}  "
        f"{show.availability_pct:5.1f}%  "
        f"({show.available:3d}/{show.total_seats:3d})  "
        f"{_status_label(show.api_seating_status):<12}  "
        f"{unknown_suffix}"
        f"Best Seats: {best_seats_str}"
    )


def render_report_text(report: ReportData) -> str:
    all_shows = [s for section in report.day_sections for s in section.shows]
    venue_width = max((len(s.venue_name) for s in all_shows), default=1)
    movie_width = max((len(s.movie_title) for s in all_shows), default=1)

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("Shaw IMAX Availability Report")
    lines.append(f"Generated: {report.generated_at}")
    lines.append("=" * 70)
    lines.append(
        f"Scan window: {report.dates_scanned[0] if report.dates_scanned else 'n/a'} "
        f"to {report.dates_scanned[-1] if report.dates_scanned else 'n/a'} "
        f"({len(report.dates_scanned)} day(s) scanned, stopped: {report.stop_reason})"
    )
    lines.append(f"Total showtimes collected: {report.total_shows}")
    lines.append(f"Failed API calls: {len(report.failed_calls)}")
    lines.append("")

    for section in report.day_sections:
        lines.append(f"-- {_with_weekday(section.date)} --")
        lines.append(
            f"{section.show_count} show(s), "
            f"avg availability {section.avg_availability_pct:5.1f}%"
        )
        for show in section.shows:
            lines.append(_format_show_line(show, movie_width, venue_width))
        lines.append("")

    lines.append("-- Highlights --")
    lines.append(f"Top {len(report.most_available_shows)} most available:")
    for s in report.most_available_shows:
        lines.append(
            f"  {s.availability_pct:5.1f}%  {s.movie_title} @ {s.venue_name} "
            f"{_with_weekday(s.display_date)} {s.display_time}"
        )

    if report.failed_calls:
        lines.append("")
        lines.append(f"-- Failed calls ({len(report.failed_calls)}) --")
        for f in report.failed_calls:
            lines.append(f"  [{f.kind}] {f.identifier}: {f.error}")

    lines.append("=" * 70)
    return "\n".join(lines)


def render_report_html(report: ReportData) -> str:
    # fromisoformat parses "+08:00" into its own generic offset tzinfo, which
    # doesn't carry config.SGT's "SGT" name — astimezone swaps in our named
    # tzinfo (same offset) so strftime("%Z") below prints "SGT" not "UTC+08:00".
    generated_at = datetime.fromisoformat(report.generated_at).astimezone(config.SGT)
    template = _jinja_env.get_template("index.html.j2")
    return template.render(
        report=report,
        generated_at_display=generated_at.strftime("%Y-%m-%d %H:%M %Z"),
    )
