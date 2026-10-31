"""Refill history calendar for Gas Renew."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GasRenewConfigEntry
from .entity import GasRenewEntity

TEXT = {
    "en": {
        "cylinder": "Cylinder #{n}: lasted {days} days",
        "cylinder_desc": "Fitted {start}, renewed {end}.",
        "in_use": "Cylinder #{n} in use",
        "in_use_desc": "Day {day} of {duration}, about {pct}% left.",
        "empty": "Gas expected to run out",
        "empty_desc": "Based on an expected duration of {duration} days from {start}.",
    },
    "ms": {
        "cylinder": "Tong #{n}: bertahan {days} hari",
        "cylinder_desc": "Dipasang {start}, ditukar {end}.",
        "in_use": "Tong #{n} sedang digunakan",
        "in_use_desc": "Hari {day} daripada {duration}, lebih kurang {pct}% lagi.",
        "empty": "Gas dijangka habis",
        "empty_desc": "Berdasarkan jangka hayat {duration} hari dari {start}.",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GasRenewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([GasRenewCalendar(entry.runtime_data, "refills")])


def _overlaps(ev: CalendarEvent, start: date, end: date) -> bool:
    return ev.start < end and ev.end > start


class GasRenewCalendar(GasRenewEntity, CalendarEntity):
    """Past cylinders as all-day spans, the current one, and the expected empty day.

    The entity's own event is "Gas expected to run out", so calendar triggers
    with a negative offset (e.g. -336:00:00 for 14 days) give an early reminder.
    """

    def _t(self) -> dict[str, str]:
        lang = (self.hass.config.language or "en")[:2]
        return TEXT.get(lang, TEXT["en"])

    def _uid(self, suffix: str) -> str:
        return f"{self.tank.entry.entry_id}-{suffix}"

    def _empty_event(self) -> CalendarEvent:
        t, tank = self._t(), self.tank
        day = tank.expected_empty.date()
        return CalendarEvent(
            start=day,
            end=day + timedelta(days=1),
            summary=t["empty"],
            description=t["empty_desc"].format(
                duration=tank.duration, start=tank.last_change.isoformat()
            ),
            uid=self._uid(f"empty-{tank.last_change.isoformat()}"),
        )

    def _all_events(self) -> list[CalendarEvent]:
        t, tank = self._t(), self.tank
        events: list[CalendarEvent] = []
        for n, cyl in enumerate(tank.cylinders, start=1):
            start = date.fromisoformat(cyl["start"])
            end = date.fromisoformat(cyl["end"])
            events.append(
                CalendarEvent(
                    start=start,
                    end=max(end, start + timedelta(days=1)),
                    summary=t["cylinder"].format(n=n, days=cyl["days"]),
                    description=t["cylinder_desc"].format(start=cyl["start"], end=cyl["end"]),
                    uid=self._uid(f"cyl-{cyl['start']}"),
                )
            )
        current_no = len(tank.cylinders) + 1
        events.append(
            CalendarEvent(
                start=tank.last_change,
                end=max(tank.today, tank.last_change) + timedelta(days=1),
                summary=t["in_use"].format(n=current_no),
                description=t["in_use_desc"].format(
                    day=tank.days_in_use, duration=tank.duration, pct=tank.percentage
                ),
                uid=self._uid(f"cyl-{tank.last_change.isoformat()}"),
            )
        )
        events.append(self._empty_event())
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """The next expected run-out day (stays put if it has passed un-renewed)."""
        return self._empty_event()

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start, end = start_date.date(), end_date.date() + timedelta(days=1)
        return [ev for ev in self._all_events() if _overlaps(ev, start, end)]
