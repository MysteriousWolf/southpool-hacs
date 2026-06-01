"""
Constants for southpool integration.

This module contains all shared constants used throughout the integration to
ensure consistency and avoid duplication of magic numbers and strings.
"""

from logging import Logger, getLogger
from zoneinfo import ZoneInfo

LOGGER: Logger = getLogger(__package__)

# Integration metadata
DOMAIN = "southpool"
ATTRIBUTION = "Data provided by Southpool (labs.hupx.hu)"
CONF_REGION = "region"

# Timezone handling
# The HUPX/Southpool API delivers data with "Delivery day" and "Hour" /
# "Quarter hour" fields expressed in local Central European time
# (CET in winter, CEST in summer). To avoid DST off-by-one bugs, every CSV
# record is converted to a UTC start datetime at fetch time (see api.py) and
# all internal lookups operate in UTC. SOURCE_TZ is the timezone used to
# interpret the raw "Delivery day" date plus the hour/quarter-hour offset.
SOURCE_TZ = ZoneInfo("Europe/Budapest")
# Kept as an alias for backwards compatibility with existing imports.
CET_TZ = SOURCE_TZ

# Available regions for Southpool power grid
REGIONS = [
    {"value": "HU", "label": "Hungary"},
    {"value": "RS", "label": "Serbia"},
    {"value": "SI", "label": "Slovenia"},
]

# Time interval constants
MINUTES_PER_QUARTER_HOUR = 15
QUARTER_HOURS_PER_DAY = 96
HOURS_PER_DAY = 24
FORECAST_HOURS = 48

# API endpoint constants
API_BASE_URL = "https://labs.hupx.hu/csv/v1"
API_ENDPOINT_15MIN = f"{API_BASE_URL}/dam_aggregated_trading_data_15min/csv"
API_ENDPOINT_HOURLY = f"{API_BASE_URL}/dam_aggregated_trading_data/csv"

# Update intervals
API_FETCH_INTERVAL_HOURS = 1

# Time calculation constants
SECONDS_PER_MINUTE = 60

# Recovery timing constants (in seconds)
QUARTER_HOUR_RECOVERY_THRESHOLD = -300  # 5 minutes past
API_FETCH_RECOVERY_THRESHOLD = -1800  # 30 minutes past
