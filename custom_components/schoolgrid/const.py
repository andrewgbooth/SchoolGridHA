"""Constants for the SchoolGrid integration."""
from datetime import timedelta

DOMAIN = "schoolgrid"
BASE_URL = "https://app.schoolgrid.co.uk"

CONF_WEEKS = "weeks"
DEFAULT_WEEKS = 2
SCAN_INTERVAL = timedelta(minutes=30)

SERVICE_PLACE_ORDER = "place_order"

STATUS_ORDERED = "ordered"
STATUS_NOT_ORDERED = "not_ordered"
STATUS_PAST = "past"
STATUS_HOLIDAY = "holiday"
STATUS_NO_MENU = "no_menu"
