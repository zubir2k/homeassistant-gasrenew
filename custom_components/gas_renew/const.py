"""Constants for Gas Renew."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "gas_renew"

# Config entry data
CONF_CYLINDER_KG: Final = "cylinder_kg"
CONF_DURATION: Final = "duration"
CONF_LAST_CHANGE: Final = "last_change"
CONF_PREVIOUS_CHANGE: Final = "previous_change"

# Options
CONF_THRESHOLD_MEDIUM: Final = "threshold_medium"
CONF_THRESHOLD_LOW: Final = "threshold_low"
CONF_THRESHOLD_CRITICAL: Final = "threshold_critical"
CONF_M3_PER_KG: Final = "m3_per_kg"
CONF_AUTO_LEARN: Final = "auto_learn"
CONF_LEARN_SAMPLES: Final = "learn_samples"

DEFAULT_NAME: Final = "LPG Cylinder"
DEFAULT_CYLINDER_KG: Final = 14.0
DEFAULT_DURATION: Final = 70
DEFAULT_THRESHOLD_MEDIUM: Final = 60  # % at or below -> Medium
DEFAULT_THRESHOLD_LOW: Final = 30  # % at or below -> Low
DEFAULT_THRESHOLD_CRITICAL: Final = 5  # % at or below -> Critical
# 1 kg of LPG vapour is roughly 0.54 m3 for propane; butane-rich blends give less.
DEFAULT_M3_PER_KG: Final = 0.54
DEFAULT_AUTO_LEARN: Final = True
DEFAULT_LEARN_SAMPLES: Final = 3

MIN_DURATION: Final = 1
MAX_DURATION: Final = 365
# A renew pressed sooner than this after the last one is not counted as a real refill.
MIN_LEARN_DAYS: Final = 7
HISTORY_MAX: Final = 12
CYLINDERS_MAX: Final = 100  # calendar history

LEVEL_FULL: Final = "full"
LEVEL_MEDIUM: Final = "medium"
LEVEL_LOW: Final = "low"
LEVEL_CRITICAL: Final = "critical"
LEVELS: Final = [LEVEL_FULL, LEVEL_MEDIUM, LEVEL_LOW, LEVEL_CRITICAL]

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "gas_renew.{entry_id}"

CARD_FILENAME: Final = "gas-renew-card.js"
CARD_URL: Final = f"/{DOMAIN}/{CARD_FILENAME}"

SERVICE_RENEW: Final = "renew"
ATTR_DATE: Final = "date"
