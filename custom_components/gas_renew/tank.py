"""Cylinder state: persistence, calculations and renew logic."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
import logging
from statistics import mean
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_LEARN,
    CONF_CYLINDER_KG,
    CONF_DURATION,
    CONF_LAST_CHANGE,
    CONF_LEARN_SAMPLES,
    CONF_M3_PER_KG,
    CONF_PREVIOUS_CHANGE,
    CONF_THRESHOLD_CRITICAL,
    CONF_THRESHOLD_LOW,
    CONF_THRESHOLD_MEDIUM,
    DEFAULT_AUTO_LEARN,
    DEFAULT_CYLINDER_KG,
    DEFAULT_DURATION,
    DEFAULT_LEARN_SAMPLES,
    DEFAULT_M3_PER_KG,
    DEFAULT_THRESHOLD_CRITICAL,
    DEFAULT_THRESHOLD_LOW,
    DEFAULT_THRESHOLD_MEDIUM,
    CYLINDERS_MAX,
    HISTORY_MAX,
    LEVEL_CRITICAL,
    LEVEL_FULL,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    MAX_DURATION,
    MIN_DURATION,
    MIN_LEARN_DAYS,
    STORAGE_KEY,
    STORAGE_VERSION,
)

ACCRUAL_INTERVAL = timedelta(minutes=5)
SAVE_DELAY = 60  # seconds

_LOGGER = logging.getLogger(__name__)


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


class GasTank:
    """One LPG cylinder, estimated by days since it was last changed."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id)
        )
        self._listeners: list[Callable[[], None]] = []
        self._unsub_midnight: CALLBACK_TYPE | None = None

        self.last_change: date = dt_util.now().date()
        self.previous_change: date | None = None
        self.duration: int = DEFAULT_DURATION
        self.history: list[int] = []  # real durations (days) of past cylinders
        # Finished cylinders for the calendar: {"start": iso, "end": iso, "days": int}
        self.cylinders: list[dict[str, Any]] = []
        # Energy accounting (kg). lifetime_kg only ever goes up.
        self.lifetime_kg: float = 0.0
        self.cylinder_used_kg: float = 0.0
        self.last_accrual: datetime = dt_util.utcnow()
        self._unsub_accrual: CALLBACK_TYPE | None = None

    # ---------- lifecycle ----------
    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self.last_change = _parse_date(stored.get("last_change")) or self.last_change
            self.previous_change = _parse_date(stored.get("previous_change"))
            self.duration = int(stored.get("duration", DEFAULT_DURATION))
            self.history = [int(d) for d in stored.get("history", [])]
            self.cylinders = list(stored.get("cylinders", []))
            if "cylinders" not in stored:
                self._seed_cylinders()
            self.lifetime_kg = float(stored.get("lifetime_kg", 0.0))
            self.cylinder_used_kg = float(stored.get("cylinder_used_kg", 0.0))
            if stored.get("last_accrual"):
                self.last_accrual = dt_util.parse_datetime(stored["last_accrual"]) or self.last_accrual
            if "lifetime_kg" not in stored:  # first run on an older store
                self.cylinder_used_kg = self._estimated_used_kg()
                self.lifetime_kg = self.cylinder_used_kg
        else:
            data = self.entry.data
            self.last_change = _parse_date(data.get(CONF_LAST_CHANGE)) or self.last_change
            self.previous_change = _parse_date(data.get(CONF_PREVIOUS_CHANGE))
            self.duration = int(data.get(CONF_DURATION, DEFAULT_DURATION))
            # Seed history with the gap between previous and last change, if sensible.
            if self.previous_change:
                gap = (self.last_change - self.previous_change).days
                if gap >= MIN_LEARN_DAYS:
                    self.history = [gap]
            self._seed_cylinders()
            # Start the meter at what this cylinder has probably used so far.
            self.cylinder_used_kg = self._estimated_used_kg()
            self.lifetime_kg = self.cylinder_used_kg
            self.last_accrual = dt_util.utcnow()
            await self.async_save()

        # Catch up on time HA was off, then accrue in small steps.
        self._accrue()
        self._unsub_accrual = async_track_time_interval(
            self.hass, self._handle_accrual, ACCRUAL_INTERVAL
        )

        # Tick just after local midnight so day counts roll over.
        self._unsub_midnight = async_track_time_change(
            self.hass, self._handle_midnight, hour=0, minute=0, second=5
        )

    async def async_unload(self) -> None:
        for unsub in (self._unsub_midnight, self._unsub_accrual):
            if unsub:
                unsub()
        self._unsub_midnight = self._unsub_accrual = None
        self._accrue()
        await self.async_save()

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "last_change": self.last_change.isoformat(),
            "previous_change": self.previous_change.isoformat()
            if self.previous_change
            else None,
            "duration": self.duration,
            "history": self.history,
            "cylinders": self.cylinders,
            "lifetime_kg": round(self.lifetime_kg, 6),
                "cylinder_used_kg": round(self.cylinder_used_kg, 6),
                "last_accrual": self.last_accrual.isoformat(),
            }

    async def async_save(self) -> None:
        await self._store.async_save(self._data_to_save())

    def _seed_cylinders(self) -> None:
        """Known previous -> last change becomes the first finished cylinder."""
        if self.previous_change and self.previous_change < self.last_change:
            self.cylinders = [
                {
                    "start": self.previous_change.isoformat(),
                    "end": self.last_change.isoformat(),
                    "days": (self.last_change - self.previous_change).days,
                }
            ]

    # ---------- listeners ----------
    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            self._listeners.remove(update_callback)

        return remove

    @callback
    def _notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    @callback
    def _handle_midnight(self, _now: datetime) -> None:
        self._notify()

    @callback
    def _handle_accrual(self, _now: datetime) -> None:
        self._accrue()
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        self._notify()

    # ---------- energy accounting ----------
    @property
    def daily_rate_kg(self) -> float:
        """Average use: one cylinder spread evenly over the expected duration."""
        return self.cylinder_kg / max(self.duration, 1)

    def _estimated_used_kg(self) -> float:
        elapsed = (dt_util.now() - datetime.combine(
            self.last_change, time.min, tzinfo=dt_util.get_default_time_zone()
        )).total_seconds() / 86400
        return min(self.cylinder_kg, max(0.0, elapsed * self.daily_rate_kg))

    @callback
    def _accrue(self) -> None:
        """Add the average rate for the time since the last step.

        Stops once the estimate says the cylinder is used up, so a tank that
        outlasts its duration adds nothing until it is renewed.
        """
        now = dt_util.utcnow()
        elapsed_days = max(0.0, (now - self.last_accrual).total_seconds() / 86400)
        room = max(0.0, self.cylinder_kg - self.cylinder_used_kg)
        add = min(room, elapsed_days * self.daily_rate_kg)
        self.cylinder_used_kg += add
        self.lifetime_kg += add
        self.last_accrual = now

    # ---------- options ----------
    def _opt(self, key: str, default: Any) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def cylinder_kg(self) -> float:
        return float(self.entry.data.get(CONF_CYLINDER_KG, DEFAULT_CYLINDER_KG))

    @property
    def m3_per_kg(self) -> float:
        return float(self._opt(CONF_M3_PER_KG, DEFAULT_M3_PER_KG))

    @property
    def auto_learn(self) -> bool:
        return bool(self._opt(CONF_AUTO_LEARN, DEFAULT_AUTO_LEARN))

    @property
    def learn_samples(self) -> int:
        return int(self._opt(CONF_LEARN_SAMPLES, DEFAULT_LEARN_SAMPLES))

    # ---------- calculations ----------
    @property
    def today(self) -> date:
        return dt_util.now().date()

    @property
    def days_in_use(self) -> int:
        return max(0, (self.today - self.last_change).days)

    @property
    def used_fraction(self) -> float:
        return min(1.0, self.days_in_use / max(self.duration, 1))

    @property
    def percentage(self) -> int:
        return max(0, round(100 - self.used_fraction * 100))

    @property
    def remaining_kg(self) -> float:
        return round(self.cylinder_kg * (1 - self.used_fraction), 2)

    @property
    def used_kg(self) -> float:
        return round(self.cylinder_kg * self.used_fraction, 2)

    @property
    def consumption_m3(self) -> float:
        """Lifetime gas used, for the Energy dashboard. Never decreases."""
        return round(self.lifetime_kg * self.m3_per_kg, 4)

    @property
    def daily_rate_m3(self) -> float:
        return round(self.daily_rate_kg * self.m3_per_kg, 4)

    @property
    def expected_empty(self) -> datetime:
        empty_day = self.last_change + timedelta(days=self.duration)
        return datetime.combine(empty_day, time.min, tzinfo=dt_util.get_default_time_zone())

    @property
    def days_left(self) -> int:
        return max(0, self.duration - self.days_in_use)

    @property
    def level(self) -> str:
        pct = self.percentage
        if pct <= int(self._opt(CONF_THRESHOLD_CRITICAL, DEFAULT_THRESHOLD_CRITICAL)):
            return LEVEL_CRITICAL
        if pct <= int(self._opt(CONF_THRESHOLD_LOW, DEFAULT_THRESHOLD_LOW)):
            return LEVEL_LOW
        if pct <= int(self._opt(CONF_THRESHOLD_MEDIUM, DEFAULT_THRESHOLD_MEDIUM)):
            return LEVEL_MEDIUM
        return LEVEL_FULL

    @property
    def learned_duration(self) -> int | None:
        if not self.history:
            return None
        return round(mean(self.history[-self.learn_samples :]))

    # ---------- actions ----------
    async def async_renew(self, on: date | None = None) -> None:
        """A new cylinder was fitted (today unless a date is given)."""
        new_date = on or self.today
        # The old cylinder is empty now: count whatever the estimate had not
        # yet accrued, so the lifetime total equals cylinders actually used.
        self._accrue()
        actual = (new_date - self.last_change).days
        if actual >= 1:  # skip a same-day double press
            self.lifetime_kg += max(0.0, self.cylinder_kg - self.cylinder_used_kg)
        self.cylinder_used_kg = 0.0
        if actual >= MIN_LEARN_DAYS:
            self.history = (self.history + [actual])[-HISTORY_MAX:]
            if self.auto_learn:
                learned = self.learned_duration
                if learned:
                    self.duration = min(MAX_DURATION, max(MIN_DURATION, learned))
        else:
            _LOGGER.debug(
                "Renew %s days after last change; not counted for learning", actual
            )
        if actual >= 1:
            self.cylinders = (
                self.cylinders
                + [
                    {
                        "start": self.last_change.isoformat(),
                        "end": new_date.isoformat(),
                        "days": actual,
                    }
                ]
            )[-CYLINDERS_MAX:]
            self.previous_change = self.last_change
        self.last_change = new_date
        # A backdated renew starts the new cylinder part-used.
        backdated = self._estimated_used_kg() if new_date < self.today else 0.0
        self.cylinder_used_kg = backdated
        self.lifetime_kg += backdated
        await self.async_save()
        self._notify()

    async def async_set_duration(self, days: int) -> None:
        self._accrue()  # bank time at the old rate before changing it
        self.duration = min(MAX_DURATION, max(MIN_DURATION, int(days)))
        await self.async_save()
        self._notify()

    async def async_set_last_change(self, value: date) -> None:
        self._accrue()
        self.last_change = value
        # Re-estimate this cylinder; only ever add to the lifetime meter.
        estimated = self._estimated_used_kg()
        self.lifetime_kg += max(0.0, estimated - self.cylinder_used_kg)
        self.cylinder_used_kg = estimated
        await self.async_save()
        self._notify()

    async def async_set_previous_change(self, value: date) -> None:
        self.previous_change = value
        await self.async_save()
        self._notify()
