from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from shaw_availability import collector


def _raw_movies(performance_id: int, display_date: str) -> list[dict]:
    return [
        {
            "primaryTitle": "Test Movie",
            "showTimes": [
                {
                    "performanceId": performance_id,
                    "displayDate": display_date,
                    "displayTime": "20:00",
                    "locationId": 1,
                    "locationVenueId": 1,
                    "locationVenueName": "Test Venue",
                    "seatingStatus": "AV",
                }
            ],
        }
    ]


class RunScanEarlyStopTest(unittest.TestCase):
    @patch("shaw_availability.collector.api_client.get_layouts")
    @patch("shaw_availability.collector.api_client.get_show_times")
    def test_empty_today_does_not_stop_scan_but_empty_day_after_tomorrow_does(
        self, mock_get_show_times, mock_get_layouts
    ):
        today = date(2026, 7, 21)
        tomorrow = today + timedelta(days=1)
        day_after = today + timedelta(days=2)

        def fake_get_show_times(session, day_str):
            if day_str == today.isoformat():
                return []  # today: already screened, API returns nothing
            if day_str == tomorrow.isoformat():
                return _raw_movies(999, tomorrow.isoformat())
            return []  # day_after: genuine edge of schedule

        mock_get_show_times.side_effect = fake_get_show_times
        mock_get_layouts.return_value = []

        result = collector.run_scan(session=MagicMock(), start_date=today, max_days=14)

        self.assertEqual(
            result.dates_scanned,
            [today.isoformat(), tomorrow.isoformat(), day_after.isoformat()],
        )
        self.assertEqual(result.stop_reason, "empty_date_hit")
        self.assertEqual(len(result.shows), 1)
        self.assertEqual(result.shows[0].performance_id, 999)
        self.assertEqual(result.shows[0].display_date, tomorrow.isoformat())

    @patch("shaw_availability.collector.api_client.get_layouts")
    @patch("shaw_availability.collector.api_client.get_show_times")
    def test_empty_today_alone_does_not_short_circuit_single_day_scan(
        self, mock_get_show_times, mock_get_layouts
    ):
        # Every day is empty (including today), but max_days=1 means there's
        # no day 1 to check — must not report "empty_date_hit" purely off
        # today's zero count.
        mock_get_show_times.return_value = []
        mock_get_layouts.return_value = []

        result = collector.run_scan(session=MagicMock(), start_date=date(2026, 7, 21), max_days=1)

        self.assertEqual(result.stop_reason, "reached_max_days")
        self.assertEqual(result.dates_scanned, ["2026-07-21"])


if __name__ == "__main__":
    unittest.main()
