from __future__ import annotations

from app.composition.scope import Scope
from app.modules.administration.application.admin_use_cases import GetAdminOverviewUseCase, ListActivityUseCase
from app.modules.administration.infrastructure.sql_admin_read_model import SqlAdminReadModel


def admin_overview(scope: Scope) -> GetAdminOverviewUseCase:
    return GetAdminOverviewUseCase(
        SqlAdminReadModel(scope.session),
        scope.resources.clock,
        scope.resources.settings.device_online_window_seconds,
    )


def list_activity(scope: Scope) -> ListActivityUseCase:
    return ListActivityUseCase(SqlAdminReadModel(scope.session))
