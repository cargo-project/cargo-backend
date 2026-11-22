"""Puerto de reloj. Inyectarlo hace que las reglas que dependen del tiempo sean predecibles en los tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
