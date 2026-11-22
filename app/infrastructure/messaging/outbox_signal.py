"""Señal en memoria para despertar al relay del outbox cuando hay un commit nuevo."""

from __future__ import annotations

import asyncio
from typing import Final

OUTBOX_DIRTY_KEY: Final = "cargo_outbox_dirty"


class OutboxSignal:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def notify(self) -> None:
        self._event.set()

    async def wait(self, max_wait_seconds: float) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), max_wait_seconds)
        except TimeoutError:
            pass
        finally:
            self._event.clear()
