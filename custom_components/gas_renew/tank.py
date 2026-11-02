"""Cylinder state: persistence, calculations and renew logic."""
from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
import logging
from statistics import mean, median_low
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, UnitOfMass
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import MassConverter

from .const import (
    CONF_AUTO_LEARN,
    CONF_CYLINDER_KG,
    CONF_DURATION,
    CONF_LAST_CHANGE,
    CONF_LEARN_SAMPLES,
    CONF_M3_PER_KG,
    CONF_PREVIOUS_CHANGE,
    CONF_RATE_KG_H,
    CONF_RUNTIME_ENTITY,
    CONF_RUNTIME_THRESHOLD,
    CONF_USAGE_SOURCE,
    DEFAULT_RATE_KG_H,
    DEFAULT_RUNTIME_THRESHOLD,
    DEFAULT_USAGE_SOURCE,
    MIN_LEARN_RUNTIME_H,
    SOURCE_RUNTIME,
    SOURCE_WEIGHT,
    AUTO_RENEW_FRACTION,
    AUTO_RENEW_HOLD_S,
    SWAP_MIN_KG,
    CONF_AUTO_RENEW,
    CONF_TARE_KG,
    CONF_WEIGHT_ENTITY,
    CONF_WEIGHT_METHOD,
    DEFAULT_AUTO_RENEW,
    DEFAULT_TARE_KG,
    DEFAULT_WEIGHT_METHOD,
    WEIGHT_ABSOLUTE,
    WEIGHT_MEDIAN_SAMPLES,
    WEIGHT_POINT_INTERVAL_S,
    WEIGHT_TREND_DAYS,
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
        # Runtime mode: hours the appliance ran on this cylinder, learned kg/h.
        self.cylinder_runtime_h: float = 0.0
        self.learned_rates: list[float] = []
        self.running: bool = False  # any runtime entity running
        self.active_count: int = 0  # how many are running (burners lit)
        self._unsub_runtime: CALLBACK_TYPE | None = None
        # Weight mode: scale reading (kg) when this cylinder was fitted,
        # last trusted reading, and hourly (timestamp, used_kg) trend points.
        self.gross_at_renew: float | None = None
        self.gross_kg: float | None = None
        self.weight_points: list[list[Any]] = []
        self.weight_stale: bool = False
        self._weight_samples: deque[float] = deque(maxlen=WEIGHT_MEDIAN_SAMPLES)
        self._jump_since: datetime | None = None
        self._off_scale: bool = False  # cylinder lifted off (swap in progress?)
        self._unsub_weight: CALLBACK_TYPE | None = None

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
            self.cylinder_runtime_h = float(stored.get("cylinder_runtime_h", 0.0))
            self.learned_rates = [float(r) for r in stored.get("learned_rates", [])]
            self.lifetime_kg = float(stored.get("lifetime_kg", 0.0))
            if stored.get("gross_at_renew") is not None:
                self.gross_at_renew = float(stored["gross_at_renew"])
            if stored.get("gross_kg") is not None:
                self.gross_kg = float(stored["gross_kg"])
            self.weight_points = list(stored.get("weight_points", []))
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
        # (Runtime mode cannot know what ran while HA was off, so it adds nothing.)
        if self.runtime_mode:
            self.last_accrual = dt_util.utcnow()
            self._count_running()
            self._unsub_runtime = async_track_state_change_event(
                self.hass, self.runtime_entities, self._handle_runtime_change
            )
        if self.weight_mode:
            self.last_accrual = dt_util.utcnow()
            self._unsub_weight = async_track_state_change_event(
                self.hass, [self.weight_entity], self._handle_weight_change
            )
            self._weight_reading(self.hass.states.get(self.weight_entity))
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
        for unsub in (self._unsub_runtime, self._unsub_weight):
            if unsub:
                unsub()
        self._unsub_midnight = self._unsub_accrual = None
        self._unsub_runtime = self._unsub_weight = None
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
            "cylinder_runtime_h": round(self.cylinder_runtime_h, 6),
            "learned_rates": self.learned_rates,
            "lifetime_kg": round(self.lifetime_kg, 6),
            "cylinder_used_kg": round(self.cylinder_used_kg, 6),
            "last_accrual": self.last_accrual.isoformat(),
            "gross_at_renew": self.gross_at_renew,
            "gross_kg": self.gross_kg,
            "weight_points": self.weight_points,
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
        if self.weight_mode:
            # HA drops repeated identical states, so a steady scale sends nothing.
            # Re-sample it on each tick so the median and the hold timer move on.
            self._weight_reading(self.hass.states.get(self.weight_entity))
            self._check_auto_renew()
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        self._notify()

    # ---------- runtime source ----------
    @property
    def runtime_mode(self) -> bool:
        return (
            self._opt(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE) == SOURCE_RUNTIME
            and bool(self.runtime_entities)
        )

    @property
    def runtime_entities(self) -> list[str]:
        """One or more entities, e.g. a hood sensor or one sensor per burner."""
        value = self._opt(CONF_RUNTIME_ENTITY, None)
        if not value:
            return []
        return [value] if isinstance(value, str) else list(value)

    def _count_running(self) -> None:
        self.active_count = sum(
            self._is_running(self.hass.states.get(e)) for e in self.runtime_entities
        )
        self.running = self.active_count > 0

    @property
    def rate_kg_h(self) -> float:
        """kg/h while running: learned from past cylinders when auto-learn is on."""
        if self.auto_learn and self.learned_rates:
            return mean(self.learned_rates[-self.learn_samples :])
        return float(self._opt(CONF_RATE_KG_H, DEFAULT_RATE_KG_H))

    def _is_running(self, state: Any) -> bool:
        """On/off entities use their state; numeric sensors use the threshold."""
        if state is None:
            return False
        try:
            return float(state.state) > float(
                self._opt(CONF_RUNTIME_THRESHOLD, DEFAULT_RUNTIME_THRESHOLD)
            )
        except (TypeError, ValueError):
            return state.state == STATE_ON

    @callback
    def _handle_runtime_change(self, event: Event[EventStateChangedData]) -> None:
        before = self.active_count
        self._accrue()  # bank the time spent at the previous count
        self._count_running()
        if self.active_count == before:
            return
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        self._notify()

    # ---------- weight source ----------
    @property
    def weight_mode(self) -> bool:
        return (
            self._opt(CONF_USAGE_SOURCE, DEFAULT_USAGE_SOURCE) == SOURCE_WEIGHT
            and bool(self.weight_entity)
        )

    @property
    def weight_entity(self) -> str | None:
        return self._opt(CONF_WEIGHT_ENTITY, None)

    @property
    def weight_method(self) -> str:
        return self._opt(CONF_WEIGHT_METHOD, DEFAULT_WEIGHT_METHOD)

    @property
    def measured_mode(self) -> bool:
        """Runtime and weight modes track used kg directly instead of by date."""
        return self.runtime_mode or self.weight_mode

    @staticmethod
    def _to_kg(state: Any) -> float | None:
        if state is None:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get("unit_of_measurement") or UnitOfMass.KILOGRAMS
        try:
            return MassConverter.convert(value, unit, UnitOfMass.KILOGRAMS)
        except Exception:  # noqa: BLE001 - unknown unit, assume kg
            return value

    @callback
    def _handle_weight_change(self, event: Event[EventStateChangedData]) -> None:
        if self._weight_reading(event.data["new_state"]):
            self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
        self._notify()

    @callback
    def _weight_reading(self, state: Any) -> bool:
        """Feed one scale reading. Returns True when the estimate changed."""
        raw = self._to_kg(state)
        if raw is None:
            self.weight_stale = True  # keep the last good value
            return False
        self.weight_stale = False
        self._weight_samples.append(raw)
        gross = median_low(self._weight_samples)

        if self.gross_at_renew is None:
            # First reading for this cylinder: anchor it to what we believe is used.
            self.gross_at_renew = gross + self.cylinder_used_kg
        ref = self.gross_kg if self.gross_kg is not None else gross
        jump = gross - ref
        if -jump >= self.cylinder_kg * AUTO_RENEW_FRACTION:
            # Too fast to be cooking: the cylinder is off the scale.
            self._off_scale = True
            self._jump_since = None
            return False
        if jump >= self._swap_threshold:
            # Probably a new cylinder; wait until it holds before renewing.
            self._jump_since = self._jump_since or dt_util.utcnow()
            self._check_auto_renew(gross)
            return False
        self._jump_since = None
        self._off_scale = False  # same cylinder back on (or never left)
        self.gross_kg = gross

        if self.weight_method == WEIGHT_ABSOLUTE:
            remaining = gross - float(self._opt(CONF_TARE_KG, DEFAULT_TARE_KG))
        else:
            remaining = self.cylinder_kg - (self.gross_at_renew - gross)
        used = min(self.cylinder_kg, max(0.0, self.cylinder_kg - remaining))
        # Gas only goes one way: ignore upward drift, count only new use.
        add = used - self.cylinder_used_kg
        if add <= 0:
            return False
        self.cylinder_used_kg = used
        self.lifetime_kg += add
        self._add_weight_point()
        return True

    @property
    def _swap_threshold(self) -> float:
        """Rise that means a new cylinder: small once the old one was lifted off."""
        if self._off_scale:
            return SWAP_MIN_KG
        return self.cylinder_kg * AUTO_RENEW_FRACTION

    @callback
    def _check_auto_renew(self, gross: float | None = None) -> None:
        if self._jump_since is None:
            return
        if (dt_util.utcnow() - self._jump_since).total_seconds() < AUTO_RENEW_HOLD_S:
            return
        if gross is None and self._weight_samples:
            gross = median_low(self._weight_samples)
        if gross is None or self.gross_kg is None:
            return
        if gross - self.gross_kg < self._swap_threshold:
            self._jump_since = None  # it came back down: something was set on the scale briefly
            return
        self._jump_since = None
        self._off_scale = False
        if not bool(self._opt(CONF_AUTO_RENEW, DEFAULT_AUTO_RENEW)):
            # No auto-renew: shift the baseline so the heavier scale isn't
            # read as "gas came back"; the user presses Renew themselves.
            if self.gross_at_renew is not None:
                self.gross_at_renew += gross - self.gross_kg
            self.gross_kg = gross
            return
        _LOGGER.info("Weight jumped %.1f kg; treating it as a new cylinder", gross - self.gross_kg)
        self.hass.async_create_task(self.async_renew(gross=gross))

    def _add_weight_point(self) -> None:
        now = dt_util.utcnow()
        if self.weight_points:
            last = dt_util.parse_datetime(self.weight_points[-1][0])
            if last and (now - last).total_seconds() < WEIGHT_POINT_INTERVAL_S:
                self.weight_points[-1] = [now.isoformat(), round(self.cylinder_used_kg, 4)]
                return
        self.weight_points.append([now.isoformat(), round(self.cylinder_used_kg, 4)])
        cutoff = now - timedelta(days=WEIGHT_TREND_DAYS)
        self.weight_points = [
            p for p in self.weight_points
            if (dt_util.parse_datetime(p[0]) or now) >= cutoff
        ]

    def _weight_trend_kg_day(self) -> float | None:
        """Least-squares slope of used kg over the recent window, in kg/day."""
        pts = [
            ((dt_util.parse_datetime(t) or dt_util.utcnow()).timestamp() / 86400, float(u))
            for t, u in self.weight_points
        ]
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 1:
            return None
        mx = mean(x for x, _ in pts)
        my = mean(y for _, y in pts)
        den = sum((x - mx) ** 2 for x, _ in pts)
        if den <= 0:
            return None
        slope = sum((x - mx) * (y - my) for x, y in pts) / den
        return slope if slope > 0 else None

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
        if self.weight_mode:
            add = 0.0  # the scale reports use directly
        elif self.runtime_mode:
            # Burner-hours: two burners lit for an hour use twice one burner.
            hours = elapsed_days * 24 * self.active_count
            self.cylinder_runtime_h += hours
            add = min(room, hours * self.rate_kg_h)
        else:
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
        if self.measured_mode:
            return min(1.0, self.cylinder_used_kg / max(self.cylinder_kg, 0.1))
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
    def avg_daily_kg(self) -> float:
        """Duration: the planned rate. Weight: recent trend. Runtime: this cylinder's average."""
        if self.weight_mode:
            trend = self._weight_trend_kg_day()
            if trend is not None:
                return trend
        if self.measured_mode and self.days_in_use >= 1 and self.cylinder_used_kg > 0:
            return self.cylinder_used_kg / self.days_in_use
        return self.daily_rate_kg

    @property
    def daily_rate_m3(self) -> float:
        return round(self.avg_daily_kg * self.m3_per_kg, 4)

    @property
    def days_left(self) -> int:
        if self.measured_mode:
            return max(0, round(self.remaining_kg / max(self.avg_daily_kg, 1e-6)))
        return max(0, self.duration - self.days_in_use)

    @property
    def expected_empty(self) -> datetime:
        if self.measured_mode:
            empty_day = self.today + timedelta(days=min(self.days_left, 3650))
        else:
            empty_day = self.last_change + timedelta(days=self.duration)
        return datetime.combine(empty_day, time.min, tzinfo=dt_util.get_default_time_zone())

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
    async def async_renew(self, on: date | None = None, gross: float | None = None) -> None:
        """A new cylinder was fitted (today unless a date is given)."""
        new_date = on or self.today
        # The old cylinder is empty now: count whatever the estimate had not
        # yet accrued, so the lifetime total equals cylinders actually used.
        self._accrue()
        actual = (new_date - self.last_change).days
        if actual >= 1 and not self.weight_mode:  # the scale already counted real use
            self.lifetime_kg += max(0.0, self.cylinder_kg - self.cylinder_used_kg)
        # Runtime mode: the whole cylinder went in this many running hours.
        if (
            self.runtime_mode
            and actual >= MIN_LEARN_DAYS
            and self.cylinder_runtime_h >= MIN_LEARN_RUNTIME_H
        ):
            rate = self.cylinder_kg / self.cylinder_runtime_h
            self.learned_rates = (self.learned_rates + [round(rate, 4)])[-HISTORY_MAX:]
        if actual >= 1:
            self.cylinder_runtime_h = 0.0
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
        backdated = (
            self._estimated_used_kg()
            if new_date < self.today and not self.measured_mode
            else 0.0
        )
        self.cylinder_used_kg = backdated
        self.lifetime_kg += backdated
        # Weight mode: the new cylinder's baseline is what the scale reads now.
        if gross is None and self._weight_samples:
            gross = median_low(self._weight_samples)
        self.gross_at_renew = gross
        self.gross_kg = gross
        self._weight_samples.clear()
        if gross is not None:
            self._weight_samples.append(gross)
        self._jump_since = None
        self._off_scale = False
        self.weight_points = []
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
        if self.measured_mode:  # used kg comes from the sensor, not the date
            await self.async_save()
            self._notify()
            return
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
