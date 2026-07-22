from datetime import timedelta, timezone

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
    "X-Api-Forward-To": "internal",
}

REQUEST_TIMEOUT_SECONDS = 10
REQUEST_DELAY_SECONDS = 0.5
MAX_RETRIES = 2

SCAN_DAYS_DEFAULT = 14

HIGHLIGHT_SHOW_COUNT = 5

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
