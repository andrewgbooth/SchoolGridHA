"""Constants for the SchoolGrid integration."""
from datetime import timedelta

DOMAIN = "schoolgrid"
BASE_URL = "https://app.schoolgrid.co.uk"

SCAN_INTERVAL = timedelta(minutes=30)
MANUAL_REFRESH_COOLDOWN = timedelta(minutes=1)

STATUS_ORDERED = "ordered"
STATUS_NOT_ORDERED = "not_ordered"
STATUS_HOLIDAY = "holiday"  # weekend, school holiday or no lunch service
STATUS_NO_MENU = "no_menu"

# If SchoolGrid can't be reached, keep showing the last good data (same day only) for this long.
STALE_DATA_MAX_AGE = timedelta(hours=6)
