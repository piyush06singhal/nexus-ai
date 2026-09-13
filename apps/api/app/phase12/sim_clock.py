"""Simulation clock — deterministic accelerated time for simulations.

The clock ticks by a configurable resolution (day/hour/week), supports pause,
seek, and deterministic scheduling so a simulation is reproducible from a seed.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class EventSchedule:
    """A recurring or one-shot event scheduled on the clock."""

    tick: int
    kind: str
    entity_ref: str | None = None
    payload: dict | None = None
    recurring_every: int | None = None  # ticks between repeats

    def fire_at(self, tick: int) -> bool:
        return tick == self.tick


@dataclass
class SimulationClock:
    """Monotonic tick-based clock inside a simulation."""

    resolution: str = "day"  # day | hour | week
    start: datetime = field(default_factory=lambda: datetime.utcnow().replace(tzinfo=None))
    _tick: int = 0
    _paused: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _schedule: list[EventSchedule] = field(default_factory=list)

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def current_time(self) -> datetime:
        step = {"day": 1, "hour": 1, "week": 7}.get(self.resolution, 1)
        return self.start + timedelta(days=step * self._tick)

    def tick_forward(self, steps: int = 1) -> int:
        with self._lock:
            if self._paused:
                return self._tick
            self._tick += max(0, steps)
            return self._tick

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def seek(self, tick: int) -> None:
        with self._lock:
            self._tick = max(0, tick)

    def schedule(
        self,
        kind: str,
        at_tick: int,
        *,
        entity_ref: str | None = None,
        payload: dict | None = None,
        recurring_every: int | None = None,
    ) -> EventSchedule:
        ev = EventSchedule(at_tick, kind, entity_ref, payload, recurring_every)
        with self._lock:
            self._schedule.append(ev)
            self._schedule.sort(key=lambda e: e.tick)
        return ev

    def due(self, tick: int) -> list[EventSchedule]:
        """Events due at this tick; recurring events re-arm for the next tick."""
        with self._lock:
            due: list[EventSchedule] = []
            remaining: list[EventSchedule] = []
            for ev in self._schedule:
                if ev.fire_at(tick):
                    due.append(ev)
                    if ev.recurring_every:
                        ev.tick += ev.recurring_every
                        remaining.append(ev)
                else:
                    remaining.append(ev)
            self._schedule = remaining
            self._schedule.sort(key=lambda e: e.tick)
            return due

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "resolution": self.resolution,
                "start": self.start.isoformat(),
                "tick": self._tick,
                "paused": self._paused,
                "schedule": [
                    {
                        "tick": e.tick,
                        "kind": e.kind,
                        "entity_ref": e.entity_ref,
                        "payload": e.payload,
                        "recurring_every": e.recurring_every,
                    }
                    for e in self._schedule
                ],
            }
