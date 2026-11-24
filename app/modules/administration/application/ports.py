from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.administration.application.admin_dto import ActivityEntry, AdminOverview


class AdminReadModel(Protocol):
    async def overview(self, *, now: datetime, online_window_seconds: int) -> AdminOverview: ...

    async def activity(
        self, *, action_prefixes: tuple[str, ...] | None, before: datetime | None, limit: int
    ) -> list[ActivityEntry]: ...
