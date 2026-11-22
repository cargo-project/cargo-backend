from __future__ import annotations

from app.composition.scope import Scope
from app.modules.configuration.infrastructure.settings_persistence import (
    PostgresSystemSettingsRepository,
    TelegramSwitchProvider,
)
from app.modules.notifications.application.notification_message_composer import NotificationMessageComposer
from app.modules.notifications.application.use_cases.dispatch_event_notifications import (
    DispatchEventNotificationsUseCase,
    RetryPolicy,
)
from app.modules.notifications.application.use_cases.recipient_use_cases import (
    CreateRecipientUseCase,
    DeleteRecipientUseCase,
    ListRecipientsUseCase,
)
from app.modules.notifications.infrastructure.persistence.postgres_notification_repositories import (
    PostgresNotificationRepository,
    PostgresRecipientRepository,
)


def list_recipients(scope: Scope) -> ListRecipientsUseCase:
    return ListRecipientsUseCase(PostgresRecipientRepository(scope.session))


def create_recipient(scope: Scope) -> CreateRecipientUseCase:
    return CreateRecipientUseCase(
        PostgresRecipientRepository(scope.session), scope.uow, scope.resources.clock, scope.audit
    )


def delete_recipient(scope: Scope) -> DeleteRecipientUseCase:
    return DeleteRecipientUseCase(
        PostgresRecipientRepository(scope.session), scope.uow, scope.resources.clock, scope.audit
    )


def dispatch_event_notifications(scope: Scope) -> DispatchEventNotificationsUseCase:
    settings = scope.resources.settings
    return DispatchEventNotificationsUseCase(
        recipients=PostgresRecipientRepository(scope.session),
        notifications=PostgresNotificationRepository(scope.session),
        gateway=scope.resources.notification_gateway,
        settings=TelegramSwitchProvider(PostgresSystemSettingsRepository(scope.session)),
        uow=scope.uow,
        clock=scope.resources.clock,
        retry_policy=RetryPolicy(
            max_attempts=settings.notification_max_attempts,
            base_delay_seconds=settings.notification_retry_base_seconds,
        ),
        composer=NotificationMessageComposer(settings.display_timezone),
    )
