from __future__ import annotations

from datetime import datetime

from app.modules.administration.application.admin_dto import ACTIVITY_CATEGORIES, ActivityEntry, AdminOverview
from app.modules.administration.application.ports import AdminReadModel
from app.shared.application.clock import Clock
from app.shared.domain.errors import BusinessRuleViolationError

MAX_ACTIVITY_PAGE = 200


class UnknownActivityCategoryError(BusinessRuleViolationError):
    code = "unknown_activity_category"


class GetAdminOverviewUseCase:
    def __init__(self, read_model: AdminReadModel, clock: Clock, online_window_seconds: int) -> None:
        self._read_model = read_model
        self._clock = clock
        self._online_window_seconds = online_window_seconds

    async def execute(self) -> AdminOverview:
        return await self._read_model.overview(now=self._clock.now(), online_window_seconds=self._online_window_seconds)


class ListActivityUseCase:
    """Bitácora de auditoría, de la más reciente a la más antigua, paginada con 'before'."""

    def __init__(self, read_model: AdminReadModel) -> None:
        self._read_model = read_model

    async def execute(
        self, *, category: str = "all", before: datetime | None = None, limit: int = 50
    ) -> list[ActivityEntry]:
        if category != "all" and category not in ACTIVITY_CATEGORIES:
            raise UnknownActivityCategoryError(f"Categoría desconocida: {category}")
        prefixes = None if category == "all" else ACTIVITY_CATEGORIES[category]
        return await self._read_model.activity(
            action_prefixes=prefixes, before=before, limit=max(1, min(limit, MAX_ACTIVITY_PAGE))
        )
