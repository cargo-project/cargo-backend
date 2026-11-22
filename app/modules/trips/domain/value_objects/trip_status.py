from __future__ import annotations

from enum import StrEnum


class TripStatus(StrEnum):
    CONFIGURED = "configured"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (TripStatus.COMPLETED, TripStatus.CANCELLED)

    def can_transition_to(self, target: TripStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS[self]


_ALLOWED_TRANSITIONS: dict[TripStatus, frozenset[TripStatus]] = {
    TripStatus.CONFIGURED: frozenset({TripStatus.ONGOING, TripStatus.CANCELLED}),
    TripStatus.ONGOING: frozenset({TripStatus.COMPLETED, TripStatus.CANCELLED}),
    TripStatus.COMPLETED: frozenset(),
    TripStatus.CANCELLED: frozenset(),
}
