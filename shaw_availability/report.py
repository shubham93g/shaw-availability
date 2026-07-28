from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time
from pathlib import Path

import jinja2
from markupsafe import Markup, escape

from . import config
from .models import FailedCall, History, HistorySnapshot, PerformanceHistory, ScanResult, ShowStats

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATES_DIR),
    autoescape=True,  # explicit, rather than relying on select_autoescape's
                      # filename-extension sniffing (which wouldn't match "*.j2")
)


def _with_weekday(date_str: str) -> str:
    weekday = datetime.strptime(date_str, config.DATE_FORMAT).strftime("%a")
    return f"{date_str} ({weekday})"


def _short_date_label(date_str: str) -> str:
    dt = datetime.strptime(date_str, config.DATE_FORMAT)
    return f"{dt.strftime('%a')}, {dt.day} {dt.strftime('%b')}"


def _time_sort_key(time_str: str) -> time:
    return datetime.strptime(time_str, "%I:%M %p").time()


def _format_sgt_timestamp(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=config.SGT).strftime(f"{config.DATE_FORMAT} %H:%M %Z")


def _short_hover_timestamp(epoch_seconds: int) -> str:
    # Same short day/date style as _short_date_label, plus a 24h time —
    # dropping the time would make every same-day hover point on the trend
    # chart show an identical label, defeating the point of scrubbing.
    dt = datetime.fromtimestamp(epoch_seconds, tz=config.SGT)
    return f"{dt.strftime('%a')}, {dt.day} {dt.strftime('%b')}, {dt.strftime('%H:%M')}"


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


def _downsample_snapshots(
    snapshots: list[HistorySnapshot], max_points: int
) -> list[HistorySnapshot]:
    # Evenly sample across the *entire* tracked history rather than just
    # taking the most recent max_points: at the real ~30-min scan cadence, a
    # performance can accumulate hundreds of snapshots over the ~14 days it's
    # in scope, so "last N" would only ever show the last few hours and hide
    # any longer-run trend. Always includes the first and last snapshot.
    n = len(snapshots)
    if n <= max_points:
        return snapshots

    indices = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return [snapshots[i] for i in indices]


def _axis_time_labels(
    sampled: list[HistorySnapshot], indices: list[int]
) -> list[tuple[int, str]]:
    # Full "24 Jul 05:52" for the first label, then just "07:32" for later
    # labels as long as the calendar date (SGT) hasn't changed, so three
    # same-day labels don't each repeat the date and crowd each other.
    labels = []
    previous_date = None
    for i in indices:
        dt = datetime.fromtimestamp(sampled[i].scan_ended_at, tz=config.SGT)
        date_str = dt.strftime("%d %b")
        time_str = dt.strftime("%H:%M")
        label = time_str if date_str == previous_date else f"{date_str} {time_str}"
        previous_date = date_str
        labels.append((i, label))
    return labels


def _catmull_rom_path(points: list[tuple[float, float]]) -> str:
    # A cubic-Bezier-per-segment Catmull-Rom spline: unlike a polyline, it
    # passes through every point with a continuous tangent instead of a
    # sharp corner at each one. Points are NOT guaranteed to be evenly
    # spaced along x (x_for places them by real elapsed time, and scan
    # cadence/downsampling can both skip unevenly), so tangents are scaled
    # by each segment's actual x-distance rather than assuming a uniform
    # parameterization — otherwise a short segment next to a long one would
    # get a tangent sized for the wrong interval, overshooting or
    # undershooting the curve. Boundary segments mirror the adjacent real
    # interval's *duration* (not just position) for the missing neighbor,
    # which is what makes this reduce to the exact same control points as
    # the old uniform-index formula when spacing happens to be even.
    if len(points) == 2:
        (x0, y0), (x1, y1) = points
        return f"M{x0:.1f},{y0:.1f} L{x1:.1f},{y1:.1f}"

    n = len(points)
    segments = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[i + 1]

        dt_cur = p2[0] - p1[0]
        dt_before = (p1[0] - p0[0]) if i > 0 else dt_cur
        dt_after = (p3[0] - p2[0]) if i + 2 < n else dt_cur

        m1_scale = dt_cur / (dt_before + dt_cur) / 3
        m2_scale = dt_cur / (dt_cur + dt_after) / 3
        c1x, c1y = p1[0] + (p2[0] - p0[0]) * m1_scale, p1[1] + (p2[1] - p0[1]) * m1_scale
        c2x, c2y = p2[0] - (p3[0] - p1[0]) * m2_scale, p2[1] - (p3[1] - p1[1]) * m2_scale
        segments.append(f"C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}")
    return " ".join(segments)


def _trend_sparkline_svg(
    perf_history: PerformanceHistory | None, movie_title: str, venue_name: str, display_time: str
) -> Markup:
    snapshots = perf_history.snapshots if perf_history else []
    if len(snapshots) < 2:
        return Markup("")

    sampled = _downsample_snapshots(snapshots, config.TREND_SPARKLINE_MAX_POINTS)
    width, height = config.TREND_CHART_WIDTH, config.TREND_CHART_HEIGHT
    margin_left, margin_right = config.TREND_CHART_MARGIN_LEFT, config.TREND_CHART_MARGIN_RIGHT
    margin_top, margin_bottom = config.TREND_CHART_MARGIN_TOP, config.TREND_CHART_MARGIN_BOTTOM
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    plot_bottom = margin_top + plot_height
    n = len(sampled)
    timestamps = [s.scan_ended_at for s in sampled]
    time_span = timestamps[-1] - timestamps[0]

    def x_for(i: int) -> float:
        # By elapsed real time, not by index: snapshots aren't guaranteed to
        # be evenly spaced (scan cadence changes, downsampling picks
        # whichever indices land closest to an even split — see
        # _downsample_snapshots), so an index-based placement would visually
        # misrepresent the actual time gaps between points.
        if n == 1 or time_span == 0:
            return margin_left
        return margin_left + ((timestamps[i] - timestamps[0]) / time_span) * plot_width

    def y_for(pct: float) -> float:
        clamped = max(0.0, min(pct, 100.0))
        return margin_top + (1 - clamped / 100) * plot_height

    axis_color = "#d1d5db"
    text_color = "#6b7280"
    line_color = "#7fae87"
    accent_color = "#2e7d32"

    lines_parts = [
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{plot_bottom}" '
        f'stroke="{axis_color}" stroke-width="1" />',
        f'<line x1="{margin_left}" y1="{plot_bottom}" x2="{margin_left + plot_width}" y2="{plot_bottom}" '
        f'stroke="{axis_color}" stroke-width="1" />',
    ]

    text_parts = []
    for pct_tick in (0, 50, 100):
        ty = y_for(pct_tick)
        text_parts.append(
            f'<text x="{margin_left - 4}" y="{ty + 3:.1f}" text-anchor="end">{pct_tick}%</text>'
        )

    label_indices = sorted({0, n // 2, n - 1}) if n >= 3 else sorted({0, n - 1})
    for i, label in _axis_time_labels(sampled, label_indices):
        lx = x_for(i)
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        text_parts.append(
            f'<text x="{lx:.1f}" y="{plot_bottom + 12}" text-anchor="{anchor}">{escape(label)}</text>'
        )

    axis_parts = lines_parts + [
        f'<g font-family="system-ui, sans-serif" font-size="9" fill="{text_color}">'
        + "".join(text_parts)
        + "</g>"
    ]

    data_points = [(x_for(i), y_for(s.availability_pct)) for i, s in enumerate(sampled)]
    path_d = _catmull_rom_path(data_points)

    # Per-point payload for client-side hover/touch scrubbing (see the
    # trend-hover script in index.html.j2): top/bottom let the JS-drawn
    # crosshair span the same vertical extent as the axis line above without
    # duplicating margin math in JS.
    hover_points = [
        {
            "x": round(x, 1),
            "y": round(y, 1),
            "pct": round(s.availability_pct, 1),
            "t": _short_hover_timestamp(s.scan_ended_at),
        }
        for (x, y), s in zip(data_points, sampled)
    ]
    hover_payload = json.dumps(
        {"points": hover_points, "top": margin_top, "bottom": plot_bottom},
        separators=(",", ":"),
    )

    dot_parts = []
    for i, (cx, cy) in enumerate(data_points):
        is_latest = i == n - 1
        radius = 4 if is_latest else 3
        fill = accent_color if is_latest else line_color
        dot_parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius}" fill="{fill}" />')

    header = f"{movie_title} · {venue_name} · {display_time}"

    return Markup(
        '<details class="trend-toggle">'
        '<summary aria-label="Show availability trend">Trend</summary>'
        '<div class="trend-popup">'
        f'<div class="trend-popup-header">{escape(header)}</div>'
        '<div class="trend-hover-readout">'
        '<span class="trend-hover-placeholder">Hover or drag to see a value</span>'
        '<span class="trend-hover-pct"></span><span class="trend-hover-time"></span>'
        '</div>'
        f'<svg class="trend-sparkline" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'data-points="{escape(hover_payload)}">'
        + "".join(axis_parts)
        + f'<path d="{path_d}" fill="none" stroke="{line_color}" stroke-width="2" '
        'stroke-linejoin="round" stroke-linecap="round" />'
        + "".join(dot_parts)
        + "</svg>"
        "</div>"
        "</details>"
    )


_jinja_env.globals["booking_url"] = _booking_url
_jinja_env.globals["status_label"] = _status_label
_jinja_env.globals["short_date"] = _short_date_label
_jinja_env.globals["availability_style"] = _availability_style
_jinja_env.globals["most_available_count"] = config.MOST_AVAILABLE_COUNT
_jinja_env.globals["trend_sparkline"] = _trend_sparkline_svg


@dataclass
class DaySection:
    date: str
    shows: list[ShowStats]
    show_count: int
    avg_availability_pct: float


@dataclass
class ReportData:
    generated_at: int
    dates_scanned: list[str]
    stop_reason: str
    total_shows: int
    day_sections: list[DaySection] = field(default_factory=list)
    failed_calls: list[FailedCall] = field(default_factory=list)
    venues: list[str] = field(default_factory=list)
    history_by_performance_id: dict[int, PerformanceHistory] = field(default_factory=dict)


def build_report(result: ScanResult, history: History | None = None) -> ReportData:
    history = history or History()
    history_by_performance_id = {p.performance_id: p for p in history.performances}

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
        failed_calls=result.failed_calls,
        venues=sorted({s.venue_name for s in result.shows}),
        history_by_performance_id=history_by_performance_id,
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
    lines.append(f"Generated: {_format_sgt_timestamp(report.generated_at)}")
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

    if report.failed_calls:
        lines.append("")
        lines.append(f"-- Failed calls ({len(report.failed_calls)}) --")
        for f in report.failed_calls:
            lines.append(f"  [{f.kind}] {f.identifier}: {f.error}")

    lines.append("=" * 70)
    return "\n".join(lines)


def render_report_html(report: ReportData) -> str:
    template = _jinja_env.get_template("index.html.j2")
    return template.render(
        report=report,
        generated_at_display=_format_sgt_timestamp(report.generated_at),
        generated_at_epoch_ms=report.generated_at * 1000,
    )
