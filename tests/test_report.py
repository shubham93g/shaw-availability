from __future__ import annotations

import html
import json
import re
import unittest

from shaw_availability import config
from shaw_availability.models import History, HistorySnapshot, PerformanceHistory, ScanResult, ShowStats
from shaw_availability.report import (
    DaySection,
    ReportData,
    _catmull_rom_path,
    _downsample_snapshots,
    _format_sgt_timestamp,
    _trend_sparkline_svg,
    build_report,
    render_report_html,
    render_report_text,
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


class FormatSgtTimestampTest(unittest.TestCase):
    def test_known_epoch_formats_as_sgt_date_and_time(self):
        # 2026-07-23T01:35:54+08:00
        self.assertEqual(_format_sgt_timestamp(1784741754), "2026-07-23 01:35 SGT")


class RenderReportTextGeneratedAtTest(unittest.TestCase):
    def test_prints_plain_sgt_timestamp_with_no_ago_suffix(self):
        report = ReportData(
            generated_at=1784741754,
            dates_scanned=[],
            stop_reason="reached scan limit",
            total_shows=0,
        )

        text = render_report_text(report)

        self.assertIn("Generated: 2026-07-23 01:35 SGT\n", text)
        self.assertNotIn("ago", text)


class RenderReportHtmlGeneratedAtTest(unittest.TestCase):
    def test_embeds_display_string_and_epoch_milliseconds(self):
        report = ReportData(
            generated_at=1784741754,
            dates_scanned=[],
            stop_reason="reached scan limit",
            total_shows=0,
        )

        html = render_report_html(report)

        self.assertIn("Generated: 2026-07-23 01:35 SGT", html)
        self.assertIn('data-generated-at-ms="1784741754000"', html)


class DownsampleSnapshotsTest(unittest.TestCase):
    def test_returns_all_snapshots_unchanged_when_at_or_under_the_cap(self):
        snapshots = [HistorySnapshot(scan_ended_at=i, availability_pct=float(i)) for i in range(5)]

        self.assertEqual(_downsample_snapshots(snapshots, 20), snapshots)

    def test_downsamples_evenly_across_full_history_instead_of_taking_the_tail(self):
        # 200 snapshots one minute apart (~3.3 hours of raw data at real scan
        # cadence, but modelling a performance tracked over a much longer span).
        snapshots = [
            HistorySnapshot(scan_ended_at=i * 60, availability_pct=float(i)) for i in range(200)
        ]

        sampled = _downsample_snapshots(snapshots, 20)

        self.assertEqual(len(sampled), 20)
        self.assertEqual(sampled[0], snapshots[0])
        self.assertEqual(sampled[-1], snapshots[-1])
        # A "last 20" slice would have every gap equal to the raw 60s spacing;
        # downsampling across the full 200-point range spreads them out well
        # beyond that, proving it isn't just the tail.
        gaps = [b.scan_ended_at - a.scan_ended_at for a, b in zip(sampled, sampled[1:])]
        self.assertTrue(all(gap > 60 for gap in gaps))


class CatmullRomPathTest(unittest.TestCase):
    def test_two_points_draws_a_straight_line(self):
        path_d = _catmull_rom_path([(0.0, 0.0), (10.0, 5.0)])

        self.assertEqual(path_d, "M0.0,0.0 L10.0,5.0")

    def test_passes_exactly_through_every_point(self):
        points = [(0.0, 10.0), (5.0, 2.0), (10.0, 8.0), (15.0, 1.0)]

        path_d = _catmull_rom_path(points)

        tokens = path_d.split(" ")
        self.assertEqual(tokens[0], "M0.0,10.0")
        # Each cubic-Bezier "C" segment is 3 space-separated coordinate
        # pairs (control, control, endpoint); the 3rd of every group of 3
        # tokens after the initial M is that segment's endpoint, which a
        # Catmull-Rom spline places exactly on the original point.
        endpoints = tokens[3::3]
        expected = [f"{x:.1f},{y:.1f}" for x, y in points[1:]]
        self.assertEqual(endpoints, expected)


class TrendSparklineSvgTest(unittest.TestCase):
    def test_returns_nothing_for_fewer_than_two_snapshots(self):
        self.assertEqual(_trend_sparkline_svg(None, "Test Movie", "Lido IMAX", "9:15 AM"), "")

        one_snapshot = PerformanceHistory(
            performance_id=1,
            snapshots=[HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0)],
        )
        markup = _trend_sparkline_svg(one_snapshot, "Test Movie", "Lido IMAX", "9:15 AM")
        self.assertEqual(markup, "")

    def test_renders_smooth_path_with_one_segment_between_consecutive_points(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
                HistorySnapshot(scan_ended_at=1784996567, availability_pct=30.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        self.assertIn("<path", markup)
        path_d = re.search(r'<path d="([^"]+)"', markup).group(1)
        # One cubic-Bezier "C" segment per consecutive pair of points (a
        # Catmull-Rom spline through all of them, not straight polyline
        # segments), so 3 points means 2 segments after the initial M.
        self.assertEqual(path_d.count("C"), 2)

    def test_clamps_out_of_range_percentages_into_the_viewbox(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1, availability_pct=-10.0),
                HistorySnapshot(scan_ended_at=2, availability_pct=150.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        # The dot markers sit exactly at each (clamped) data point regardless
        # of how the connecting curve is drawn, so they're what to check here
        # rather than the path's control points (a Catmull-Rom spline's
        # control points can overshoot the data range slightly, by design).
        ys = [float(y) for y in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)"', markup)]
        plot_bottom = config.TREND_CHART_MARGIN_TOP + (
            config.TREND_CHART_HEIGHT - config.TREND_CHART_MARGIN_TOP - config.TREND_CHART_MARGIN_BOTTOM
        )
        self.assertEqual(len(ys), 2)
        for y in ys:
            self.assertGreaterEqual(y, config.TREND_CHART_MARGIN_TOP)
            self.assertLessEqual(y, plot_bottom)

    def test_places_dots_proportionally_to_elapsed_time_not_index(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=0, availability_pct=10.0),
                HistorySnapshot(scan_ended_at=100, availability_pct=20.0),
                HistorySnapshot(scan_ended_at=1000, availability_pct=30.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        xs = [float(x) for x in re.findall(r'<circle cx="([\d.]+)"', markup)]
        self.assertEqual(len(xs), 3)
        gap1 = xs[1] - xs[0]
        gap2 = xs[2] - xs[1]
        # Elapsed time between points is 100s then 900s (a 1:9 ratio); an
        # index-based layout would have made these two gaps equal instead.
        self.assertAlmostEqual(gap2 / gap1, 900 / 100, places=1)

    def test_renders_one_dot_marker_per_snapshot(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
                HistorySnapshot(scan_ended_at=1784996567, availability_pct=30.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        self.assertEqual(markup.count("<circle"), 3)

    def test_renders_axis_lines_and_percentage_tick_labels(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        self.assertEqual(markup.count("<line"), 2)
        self.assertIn(">0%</text>", markup)
        self.assertIn(">50%</text>", markup)
        self.assertIn(">100%</text>", markup)

    def test_wraps_output_in_a_details_element_so_trend_is_collapsed_by_default(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1, availability_pct=10.0),
                HistorySnapshot(scan_ended_at=2, availability_pct=20.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        self.assertIn('<details class="trend-toggle">', markup)

    def test_includes_venue_and_show_time_in_a_popup_header(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        self.assertIn('<div class="trend-popup-header">Test Movie · Lido IMAX · 9:15 AM</div>', markup)

    def test_exposes_per_point_data_for_client_side_hover(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
                HistorySnapshot(scan_ended_at=1784996567, availability_pct=30.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        match = re.search(r'data-points="([^"]*)"', markup)
        self.assertIsNotNone(match)
        # html.unescape mirrors what a browser does when parsing the
        # attribute (report.py HTML-entity-escapes the JSON so it survives
        # inside a double-quoted attribute).
        payload = json.loads(html.unescape(match.group(1)))
        self.assertEqual([p["pct"] for p in payload["points"]], [50.0, 40.0, 30.0])
        # Short "Day, D Mon, HH:MM" style (see _short_hover_timestamp), not
        # _format_sgt_timestamp's longer "YYYY-MM-DD HH:MM SGT" — a same-day
        # hover point still needs the time to stay distinguishable from
        # its neighbors, so only the date portion is shortened.
        self.assertEqual(payload["points"][0]["t"], "Sat, 25 Jul, 23:56")
        self.assertIn("top", payload)
        self.assertIn("bottom", payload)

    def test_renders_a_static_hover_readout_with_placeholder_and_empty_value_spans(self):
        perf_history = PerformanceHistory(
            performance_id=1,
            snapshots=[
                HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
            ],
        )

        markup = _trend_sparkline_svg(perf_history, "Test Movie", "Lido IMAX", "9:15 AM")

        # Rendered server-side (not created lazily by JS like the crosshair
        # and hover dot) so it's plain content in normal document flow —
        # this is what makes it immune to the off-screen-tooltip bug a
        # positioned/transformed element had on narrow viewports.
        self.assertIn('<div class="trend-hover-readout">', markup)
        self.assertIn('<span class="trend-hover-placeholder">', markup)
        self.assertIn('<span class="trend-hover-pct"></span><span class="trend-hover-time"></span>', markup)


class BuildReportHistoryWiringTest(unittest.TestCase):
    def test_build_report_populates_history_by_performance_id_keyed_by_performance_id(self):
        result = ScanResult(
            scan_started_at=1,
            scan_ended_at=2,
            dates_scanned=["2026-07-23"],
            stop_reason="reached scan limit",
            shows=[],
        )
        history = History(performances=[PerformanceHistory(performance_id=513005, snapshots=[])])

        report_data = build_report(result, history)

        self.assertIn(513005, report_data.history_by_performance_id)
        self.assertIs(report_data.history_by_performance_id[513005], history.performances[0])

    def test_build_report_defaults_to_empty_history_when_none_passed(self):
        result = ScanResult(
            scan_started_at=1,
            scan_ended_at=2,
            dates_scanned=["2026-07-23"],
            stop_reason="reached scan limit",
            shows=[],
        )

        report_data = build_report(result)

        self.assertEqual(report_data.history_by_performance_id, {})


class RenderReportHtmlTrendColumnTest(unittest.TestCase):
    def test_renders_unescaped_svg_sparkline_for_show_with_history(self):
        show = _show(513005, 40.0)
        report = ReportData(
            generated_at=1784741754,
            dates_scanned=["2026-07-23"],
            stop_reason="reached scan limit",
            total_shows=1,
            day_sections=[
                DaySection(date="2026-07-23", shows=[show], show_count=1, avg_availability_pct=40.0)
            ],
            history_by_performance_id={
                513005: PerformanceHistory(
                    performance_id=513005,
                    snapshots=[
                        HistorySnapshot(scan_ended_at=1784995000, availability_pct=50.0),
                        HistorySnapshot(scan_ended_at=1784995567, availability_pct=40.0),
                    ],
                )
            },
        )

        html = render_report_html(report)

        self.assertIn('<svg class="trend-sparkline"', html)
        self.assertNotIn("&lt;svg", html)


if __name__ == "__main__":
    unittest.main()
