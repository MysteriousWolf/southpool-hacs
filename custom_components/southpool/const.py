"""
Constants for southpool integration.

This module contains all shared constants used throughout the integration to
ensure consistency and avoid duplication of magic numbers and strings.
"""

from datetime import timedelta, timezone
from logging import Logger, getLogger
from zoneinfo import ZoneInfo

LOGGER: Logger = getLogger(__package__)

# Integration metadata
DOMAIN = "southpool"
ATTRIBUTION = "Data provided by Southpool (labs.hupx.hu)"
CONF_REGION = "region"
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 15  # minutes
VALID_UPDATE_INTERVALS = [5, 10, 15, 30, 60]

# Interval type identifiers (used in options, sensor prefixing, etc.)
INTERVAL_15MIN = "15min"
INTERVAL_HOURLY = "hourly"

# Sensor enable/disable options
CONF_INTERVALS = "intervals"
DEFAULT_INTERVALS = [INTERVAL_15MIN, INTERVAL_HOURLY]
VALID_INTERVALS = [
    {"value": INTERVAL_15MIN, "label": "15-minute"},
    {"value": INTERVAL_HOURLY, "label": "Hourly"},
]

# Timezone handling
# The HUPX/Southpool API "Delivery day" / "Hour" columns follow
# Europe/Budapest local time (CET in winter, CEST in summer). Every record
# is converted to a UTC start datetime at fetch time (see api.py) and all
# internal lookups operate in UTC.
SOURCE_TZ = ZoneInfo("Europe/Budapest")

# Fixed UTC+1 timezone (CET without DST), used when DST correction is
# disabled and the source timestamps should be treated as standard time
# regardless of summer/winter transitions.
FIXED_CET = timezone(timedelta(hours=1))

# DST correction and time offset options
CONF_DST_CORRECTION = "dst_correction"
CONF_TIME_OFFSET = "time_offset"
DEFAULT_DST_CORRECTION = True
DEFAULT_TIME_OFFSET = 0

# Available regions for Southpool power grid
REGIONS = [
    {"value": "HU", "label": "Hungary"},
    {"value": "RS", "label": "Serbia"},
    {"value": "SI", "label": "Slovenia"},
]

# Time interval constants
MINUTES_PER_QUARTER_HOUR = 15
FORECAST_HOURS = 48

# CSV field names returned by the HUPX API
FIELD_DELIVERY_DAY = "Delivery day"
FIELD_PRICE = "Price"
FIELD_TRADED_VOLUME = "Traded volume"
FIELD_BASELOAD_PRICE = "Baseload price"
FIELD_STATUS = "Status"
FIELD_HOUR = "Hour"
FIELD_QUARTER_HOUR = "Quarter hour"

# Time offset limits
TIME_OFFSET_MIN = -12
TIME_OFFSET_MAX = 12

# API endpoint constants
API_BASE_URL = "https://labs.hupx.hu/csv/v1"
API_ENDPOINT_15MIN = f"{API_BASE_URL}/dam_aggregated_trading_data_15min/csv"
API_ENDPOINT_HOURLY = f"{API_BASE_URL}/dam_aggregated_trading_data/csv"
