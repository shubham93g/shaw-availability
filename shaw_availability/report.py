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
    sold_out_shows: list[ShowStats] = field(default_factory=list)
    highest_availability_show: ShowStats | None = None
    lowest_availability_show: ShowStats | None = None
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
            f"avg availability {day.avg_availability_pct:.1f}%, "
            f"{day.sold_out_show_count} sold out",
        ]
        shows_that_day = [s for s in result.shows if s.display_date == day.date]
        for show in sorted(shows_that_day, key=lambda s: (s.venue_name, s.display_time)):
            lines.append(
                f"  {show.display_time:>8}  {show.venue_name:<20} {show.movie_title:<25} "
                f"avail {show.availability_pct:5.1f}%  "
                f"(AV {show.available} / SO {show.sold} / BL {show.blocked} / "
                f"OH {show.on_hold} / UNK {show.unknown})  api={show.api_seating_status}"
                + ("  [ANOMALY]" if show.anomaly else "")
            )
        day_sections.append(ReportSection(title=day.date, lines=lines))

    return ReportData(
        generated_at=result.scan_ended_at,
        dates_scanned=result.dates_scanned,
        stop_reason=result.stop_reason,
        overview_lines=overview_lines,
        day_sections=day_sections,
        sold_out_shows=summary["sold_out_shows"],
        highest_availability_show=summary["highest_availability_show"],
        lowest_availability_show=summary["lowest_availability_show"],
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
    if report.highest_availability_show:
        s = report.highest_availability_show
        lines.append(
            f"Highest availability: {s.movie_title} @ {s.venue_name} "
            f"{s.display_date} {s.display_time} — {s.availability_pct:.1f}%"
        )
    if report.lowest_availability_show:
        s = report.lowest_availability_show
        lines.append(
            f"Lowest availability:  {s.movie_title} @ {s.venue_name} "
            f"{s.display_date} {s.display_time} — {s.availability_pct:.1f}%"
        )
    lines.append(f"Sold-out shows: {len(report.sold_out_shows)}")
    for s in report.sold_out_shows:
        lines.append(f"  {s.movie_title} @ {s.venue_name} {s.display_date} {s.display_time}")

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
