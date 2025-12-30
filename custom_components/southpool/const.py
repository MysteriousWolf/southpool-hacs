"""Constants for southpool."""

from datetime import timedelta, timezone
from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "southpool"
ATTRIBUTION = "Data provided by Southpool (labs.hupx.hu)"
CONF_REGION = "region"

# CET timezone constant - always UTC+1 (literal CET)
CET_TZ = timezone(timedelta(hours=1))

# Available regions for Southpool power grid
REGIONS = [
    {"value": "HU", "label": "Hungary"},
    {"value": "RS", "label": "Serbia"},
    {"value": "SI", "label": "Slovenia"},
]
