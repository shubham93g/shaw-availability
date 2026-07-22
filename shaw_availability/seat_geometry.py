from __future__ import annotations

from itertools import groupby

from . import config
from .models import SeatElement

BACK_FRACTION = 1 / 3
CENTER_FRACTION = 0.5


def classify_best_seats(elements: list[SeatElement]) -> list[SeatElement]:
    """Seats in the back third (by Y) and centered within the middle 50% (by X).

    Position is derived from each performance's own live anchorCoordinateX/Y
    rather than row/column labels: row letters don't reliably indicate
    front/back (row "A" is the back row in venues checked), and column
    references include non-numeric companion/handicap seats.
    """
    if not elements:
        return []

    ys = [e.y for e in elements]
    xs = [e.x for e in elements]
    y_min, y_max = min(ys), max(ys)
    x_min, x_max = min(xs), max(xs)

    if y_max == y_min or x_max == x_min:
        return []

    back_threshold = y_max - (y_max - y_min) * BACK_FRACTION
    center_x = (x_min + x_max) / 2
    half_width = (x_max - x_min) * CENTER_FRACTION / 2

    return [
        e
        for e in elements
        if e.y >= back_threshold and abs(e.x - center_x) <= half_width
    ]


def best_available_seat_ranges(elements: list[SeatElement]) -> list[str]:
    """Available best seats as row-grouped labels, e.g. ["B-5:7", "B-9", "A-H12"].

    Consecutive numeric columns within a row collapse into a "start:end"
    range. Non-numeric columns (companion/handicap seats like "H12") and
    isolated seats are listed individually.
    """
    available = [
        e for e in classify_best_seats(elements) if e.status_code == config.SEAT_STATUS_AVAILABLE
    ]
    available.sort(key=_seat_sort_key)

    labels: list[str] = []
    for row, row_seats in groupby(available, key=lambda e: e.row):
        labels.extend(_compress_row(row, list(row_seats)))
    return labels


def _compress_row(row: str, seats: list[SeatElement]) -> list[str]:
    labels: list[str] = []
    i = 0
    while i < len(seats):
        column = seats[i].column
        if not column.isdigit():
            labels.append(f"{row}-{column}")
            i += 1
            continue

        run_start = int(column)
        j = i
        while (
            j + 1 < len(seats)
            and seats[j + 1].column.isdigit()
            and int(seats[j + 1].column) == int(seats[j].column) + 1
        ):
            j += 1
        run_end = int(seats[j].column)

        labels.append(f"{row}-{run_start}:{run_end}" if j > i else f"{row}-{run_start}")
        i = j + 1
    return labels


def _seat_sort_key(e: SeatElement) -> tuple[str, tuple[int, object]]:
    try:
        column_key = (0, int(e.column))
    except ValueError:
        column_key = (1, e.column)
    return (e.row, column_key)
