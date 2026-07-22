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


def _time_sort_key(time_str: str) -> time:
    return datetime.strptime(time_str, "%I:%M %p").time()


@dataclass
class ReportSection:
    title: str
    lines: list[str]


@dataclass
class ReportData:
    generated_at: str
    dates_scanned: list[str]
    stop_reason: str
    overview_lines: list[str]
    day_sections: list[ReportSection] = field(default_factory=list)
    most_available_shows: list[ShowStats] = field(default_factory=list)
    least_available_shows: list[ShowStats] = field(default_factory=list)
    failed_calls: list[FailedCall] = field(default_factory=list)


def build_report(result: ScanResult) -> ReportData:
    summary = stats.summarize_scan(result.shows)

    overview_lines = [
        f"Scan window: {result.dates_scanned[0] if result.dates_scanned else 'n/a'} "
        f"to {result.dates_scanned[-1] if result.dates_scanned else 'n/a'} "
        f"({len(result.dates_scanned)} day(s) scanned, stopped: {result.stop_reason})",
        f"Total showtimes collected: {len(result.shows)}",
        f"Failed API calls: {len(result.failed_calls)}",
    ]

    venue_width = max((len(s.venue_name) for s in result.shows), default=1)
    movie_width = max((len(s.movie_title) for s in result.shows), default=1)

    day_sections = []
    for day in result.day_aggregates:
        if day.show_count == 0:
            continue
        lines = [
            f"{day.show_count} show(s), "
            f"avg availability {day.avg_availability_pct:5.1f}%",
        ]
        shows_that_day = [s for s in result.shows if s.display_date == day.date]
        for show in sorted(
            shows_that_day,
            key=lambda s: (s.venue_name, _time_sort_key(s.display_time)),
        ):
            unknown_suffix = f"UNK {show.unknown:3d}  " if show.unknown else "  "
            status_label = config.SHOW_STATUS_LABELS.get(
                show.api_seating_status, show.api_seating_status
            )
            best_seats_str = (
                ", ".join(show.best_seats_available)
                if show.best_seats_available
                else "-"
            )
            lines.append(
                f"  {show.movie_title:<{movie_width}} "
                f"{show.venue_name:<{venue_width}}  {show.display_time:>8}  "
                f"{show.availability_pct:5.1f}%  "
                f"({show.available:3d}/{show.total_seats:3d})  "
                f"{status_label:<12}  "
                f"{unknown_suffix}"
                + f"Best Seats: {best_seats_str}"
            )
        day_sections.append(ReportSection(title=_with_weekday(day.date), lines=lines))

    return ReportData(
        generated_at=result.scan_ended_at,
        dates_scanned=result.dates_scanned,
        stop_reason=result.stop_reason,
        overview_lines=overview_lines,
        day_sections=day_sections,
        most_available_shows=summary["most_available_shows"],
        least_available_shows=summary["least_available_shows"],
        failed_calls=result.failed_calls,
    )


def render_report_text(report: ReportData) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("Shaw IMAX Availability Report")
    lines.append(f"Generated: {report.generated_at}")
    lines.append("=" * 70)
    lines.extend(report.overview_lines)
    lines.append("")

    for section in report.day_sections:
        lines.append(f"-- {section.title} --")
        lines.extend(section.lines)
        lines.append("")

    lines.append("-- Highlights --")
    lines.append(f"Top {len(report.most_available_shows)} most available:")
    for s in report.most_available_shows:
        lines.append(
            f"  {s.availability_pct:5.1f}%  {s.movie_title} @ {s.venue_name} "
            f"{_with_weekday(s.display_date)} {s.display_time}"
        )
    lines.append(f"Top {len(report.least_available_shows)} least available:")
    for s in report.least_available_shows:
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


def render_report_html(generated_at: str, report_text: str) -> str:
    # fromisoformat parses "+08:00" into its own generic offset tzinfo, which
    # doesn't carry config.SGT's "SGT" name — astimezone swaps in our named
    # tzinfo (same offset) so strftime("%Z") below prints "SGT" not "UTC+08:00".
    generated_at = datetime.fromisoformat(generated_at).astimezone(config.SGT)
    template = _jinja_env.get_template("index.html.j2")
    return template.render(
        generated_at_display=generated_at.strftime("%Y-%m-%d %H:%M %Z"),
        report_text=report_text,
    )
