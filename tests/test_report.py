from __future__ import annotations

import unittest

from shaw_availability.report import ReportData, _format_sgt_timestamp, render_report_html, render_report_text


class FormatSgtTimestampTest(unittest.TestCase):
    def test_known_epoch_formats_as_sgt_date_and_time(self):
        # 2026-07-23T01:35:54+08:00
        self.assertEqual(_format_sgt_timestamp(1784741754), "2026-07-23 01:35 SGT")


class RenderReportTextGeneratedAtTest(unittest.TestCase):
    def test_prints_plain_sgt_timestamp_with_no_ago_suffix(self):
        report = ReportData(
            generated_at=1784741754,
            dates_scanned=[],
            stop_reason="reached_max_days",
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
            stop_reason="reached_max_days",
            total_shows=0,
        )

        html = render_report_html(report)

        self.assertIn("Generated: 2026-07-23 01:35 SGT", html)
        self.assertIn('data-generated-at-ms="1784741754000"', html)


if __name__ == "__main__":
    unittest.main()
