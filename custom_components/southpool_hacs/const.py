"""Constants for southpool_hacs."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "southpool_hacs"
ATTRIBUTION = "Data provided by Southpool (labs.hupx.hu)"
CONF_REGION = "region"

# Available regions for Southpool power grid
REGIONS = [
    {"value": "HU", "label": "Hungary"},
    {"value": "RS", "label": "Serbia"},
    {"value": "SI", "label": "Slovenia"},
]
