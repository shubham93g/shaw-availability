from datetime import timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))

BASE_URL = "https://shaw.sg/internal"
SHOW_TIMES_PATH = "/get_show_times"
LAYOUTS_PATH = "/get_layouts"

FIXED_SHOW_TIME_PARAMS = {
    "movieId": 0,
    "locationId": 0,
    "promotionId": 0,
    "locationBrand": 2,
}

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://shaw.sg/IMAX",
    "X-Api-Forward-To": "internal",
    "X-App": "PWSM",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
}

REQUEST_TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 2

SCAN_DAYS_DEFAULT = 14

KNOWN_SEATING_STATUSES = {"AV", "SF", "SO"}
KNOWN_SEAT_STATUSES = {"AV", "SO", "BL", "OH"}

SEATING_STATUS_LABELS = {
    "AV": "Available",
    "SF": "Selling Fast",
    "SO": "Sold Out",
}

OUTPUT_DIR = Path("output")
