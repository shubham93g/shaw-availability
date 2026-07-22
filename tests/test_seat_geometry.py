from __future__ import annotations

import json
import unittest
from pathlib import Path

from shaw_availability.collector import parse_seat_elements
from shaw_availability.models import SeatElement
from shaw_availability.seat_geometry import (
    _compress_row,
    best_available_seat_ranges,
    classify_best_seats,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_elements(fixture_name: str):
    raw = json.loads((FIXTURES_DIR / fixture_name).read_text())
    return parse_seat_elements(raw)


class ClassifyBestSeatsTest(unittest.TestCase):
    """Exercises classify_best_seats against a real get_layouts response.

    Fixture is a trimmed capture of Jem IMAX (performanceId 504622): 192
    real SEAT elements with their live anchorCoordinateX/Y, row/column, and
    status at capture time. Row "A" is the physically back row (largest Y,
    farthest from the screen) despite being alphabetically first — this
    fixture is what confirmed that row-letter order can't be trusted, so
    the test pins that behavior down.
    """

    def setUp(self):
        self.elements = _load_elements("jem_layout_504622.json")

    def test_classifies_back_third_centered_seats(self):
        best = classify_best_seats(self.elements)
        self.assertEqual(len(best), 42)

    def test_best_seats_are_confined_to_the_back_rows(self):
        best = classify_best_seats(self.elements)
        rows = {e.row for e in best}
        # Rows E-L physically sit closer to the screen (lower Y) than A-D and
        # must not be classified as "best" even though row letters suggest
        # otherwise.
        self.assertEqual(rows, {"A", "B", "C", "D"})

    def test_best_seats_are_centered_within_each_back_row(self):
        best = classify_best_seats(self.elements)
        by_row = {
            row: sorted({e.column for e in best if e.row == row}, key=int)
            for row in {"B", "C", "D"}
        }
        for row, columns in by_row.items():
            self.assertEqual(
                columns,
                [str(c) for c in range(5, 16)],
                f"row {row} center band",
            )
        # Row A is narrower (missing seats 12-15, replaced by companion
        # seats H12/H13) but its qualifying columns still fall in the same
        # centered band.
        self.assertEqual(
            {e.column for e in best if e.row == "A"},
            {"5", "6", "7", "8", "9", "10", "11", "H12", "H13"},
        )

    def test_empty_input_returns_no_seats(self):
        self.assertEqual(classify_best_seats([]), [])

    def test_best_available_seat_ranges_matches_fixture_snapshot(self):
        # Only 2 of the 42 best seats are AV at capture time. Neither column
        # is numeric, so no compression applies here — see CompressRowTest
        # for that.
        self.assertEqual(best_available_seat_ranges(self.elements), ["AH12", "AH13"])


def _seat(row: str, column: str, status: str = "AV") -> SeatElement:
    return SeatElement(row=row, column=column, status_code=status, x=0.0, y=0.0)


class CompressRowTest(unittest.TestCase):
    """_compress_row is the core range-compression logic; exercised directly
    with synthetic data since the real fixture doesn't have a run of
    consecutive available numeric seats."""

    def test_compresses_a_consecutive_run(self):
        seats = [_seat("B", "5"), _seat("B", "6"), _seat("B", "7")]
        self.assertEqual(_compress_row("B", seats), ["B5-7"])

    def test_leaves_an_isolated_seat_uncompressed(self):
        self.assertEqual(_compress_row("B", [_seat("B", "9")]), ["B9"])

    def test_splits_non_consecutive_runs(self):
        seats = [_seat("B", "5"), _seat("B", "6"), _seat("B", "7"), _seat("B", "9")]
        self.assertEqual(_compress_row("B", seats), ["B5-7", "B9"])

    def test_non_numeric_columns_are_never_compressed(self):
        seats = [_seat("A", "H12"), _seat("A", "H13")]
        self.assertEqual(_compress_row("A", seats), ["AH12", "AH13"])


if __name__ == "__main__":
    unittest.main()
