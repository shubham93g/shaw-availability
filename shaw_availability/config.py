from datetime import timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8), "SGT")

# Canonical wire format for date strings (ShowStats.display_date,
# DayAggregate.date, ScanResult.dates_scanned, the --start-date CLI arg, and
# the day param sent to Shaw's API). Must stay zero-padded YYYY-MM-DD:
# collector.py's day-aggregate union/dedup sorts these strings
# lexicographically and relies on that matching chronological order.
DATE_FORMAT = "%Y-%m-%d"

BASE_URL = "https://shaw.sg/internal"
SHOW_TIMES_PATH = "/get_show_times"
LAYOUTS_PATH = "/get_layouts"

# locationBrand is a venue-format id, not a live bitmask: values are powers
# of two (1=DGTL, 2=IMAX, 4=PREM, 8=LUMR, 16=DREM, 32=PDREM, 128=LUMRG,
# 256=PREMLIDO, 512=PFSDREM), but combining them (e.g. 3 for DGTL+IMAX)
# returns no results — each id must be queried alone. 0 means unfiltered.
# See README.md's "APIs used" section for how this was determined.
LOCATION_BRAND_IMAX = 2

FIXED_SHOW_TIME_PARAMS = {
    "movieId": 0,
    "locationId": 0,
    "promotionId": 0,
    "locationBrand": LOCATION_BRAND_IMAX,
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "X-Api-Forward-To": "internal",
}

REQUEST_TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 2

SCAN_DAYS_DEFAULT = 14

MOST_AVAILABLE_COUNT = 10

SEAT_STATUS_AVAILABLE = "AV"
SEAT_STATUS_SOLD = "SO"
SEAT_STATUS_BLOCKED = "BL"
SEAT_STATUS_ON_HOLD = "OH"
KNOWN_SEAT_STATUSES = {
    SEAT_STATUS_AVAILABLE,
    SEAT_STATUS_SOLD,
    SEAT_STATUS_BLOCKED,
    SEAT_STATUS_ON_HOLD,
}

KNOWN_SHOW_STATUSES = {"AV", "SF", "SO"}
SHOW_STATUS_LABELS = {
    "AV": "Available",
    "SF": "Selling Fast",
    "SO": "Sold Out",
}

ARTIFACTS_DIR = Path("artifacts")
SCAN_RESULT_FILENAME = "scan_result.json"
REPORT_HTML_FILENAME = "index.html"

BOOKING_URL_TEMPLATE = "https://shaw.sg/showtimes/{performance_id}"
