from __future__ import annotations

from dataclasses import dataclass, field

from . import stats
from .models import FailedCall, ScanResult, ShowStats


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
    anomalies: list[ShowStats] = field(default_factory=list)
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

    day_sections = []
    for day in result.day_aggregates:
        if day.show_count == 0:
            continue
        lines = [
            f"{day.show_count} show(s), {day.total_seats} total seats, "
            f"avg availability {day.avg_availability_pct:5.1f}%",
        ]
        shows_that_day = [s for s in result.shows if s.display_date == day.date]
        for show in sorted(shows_that_day, key=lambda s: (s.venue_name, s.display_time)):
            lines.append(
                f"  {show.display_time:>8}  {show.venue_name:<20} {show.movie_title:<25} "
                f"avail {show.availability_pct:5.1f}%  "
                f"(AV {show.available:3d} / SO {show.sold:3d} / BL {show.blocked:3d} / "
                f"OH {show.on_hold:3d} / UNK {show.unknown:3d})  api={show.api_seating_status}"
                + ("  [ANOMALY]" if show.anomaly else "")
            )
        day_sections.append(ReportSection(title=day.date, lines=lines))

    return ReportData(
        generated_at=result.scan_ended_at,
        dates_scanned=result.dates_scanned,
        stop_reason=result.stop_reason,
        overview_lines=overview_lines,
        day_sections=day_sections,
        most_available_shows=summary["most_available_shows"],
        least_available_shows=summary["least_available_shows"],
        anomalies=summary["anomalies"],
        failed_calls=result.failed_calls,
    )


def render_report_text(report: ReportData) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("Shaw IMAX Seat-Availability Report")
    lines.append(f"Generated: {report.generated_at}")
    lines.append("=" * 70)
    lines.extend(report.overview_lines)
    lines.append("")

    for section in report.day_sections:
        lines.append(f"-- {section.title} --")
        lines.extend(section.lines)
        lines.append("")

    lines.append("-- Highlights --")
    lines.append("Top 5 most available:")
    for s in report.most_available_shows:
        lines.append(
            f"  {s.availability_pct:5.1f}%  {s.movie_title} @ {s.venue_name} "
            f"{s.display_date} {s.display_time}"
        )
    lines.append("Top 5 least available:")
    for s in report.least_available_shows:
        lines.append(
            f"  {s.availability_pct:5.1f}%  {s.movie_title} @ {s.venue_name} "
            f"{s.display_date} {s.display_time}"
        )

    if report.anomalies:
        lines.append("")
        lines.append("-- Anomalies --")
        for s in report.anomalies:
            lines.append(
                f"  {s.movie_title} @ {s.venue_name} {s.display_date} {s.display_time}: "
                f"{s.anomaly}"
            )

    if report.failed_calls:
        lines.append("")
        lines.append(f"-- Failed calls ({len(report.failed_calls)}) --")
        for f in report.failed_calls:
            lines.append(f"  [{f.kind}] {f.identifier}: {f.error}")

    lines.append("=" * 70)
    return "\n".join(lines)


def print_report(report: ReportData) -> None:
    print(render_report_text(report))
