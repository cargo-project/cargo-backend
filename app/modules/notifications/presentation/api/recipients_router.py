from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.composition import notifications_factory
from app.core.http.dependencies import ScopeDep
from app.core.http.envelope import ERROR_RESPONSES, DataEnvelope, wrap
from app.modules.identity.presentation.api.auth_dependencies import CurrentUser
from app.modules.notifications.presentation.schemas.recipient_schemas import (
    RecipientRequest,
    RecipientResponse,
)

notifications_router = APIRouter(prefix="/notification-recipients", tags=["notifications"], responses=ERROR_RESPONSES)


@notifications_router.get("", summary="List Telegram recipients")
async def list_recipients(_: CurrentUser, scope: ScopeDep) -> DataEnvelope[list[RecipientResponse]]:
    recipients = await notifications_factory.list_recipients(scope).execute()
    return wrap([RecipientResponse.from_entity(r) for r in recipients])


@notifications_router.post("", status_code=status.HTTP_201_CREATED, summary="Add a recipient (any signed-in user)")
async def create_recipient(
    body: RecipientRequest, user: CurrentUser, scope: ScopeDep
) -> DataEnvelope[RecipientResponse]:
    recipient = await notifications_factory.create_recipient(scope).execute(
        name=body.name, telegram_chat_id=body.telegram_chat_id, actor_id=user.id
    )
    return wrap(RecipientResponse.from_entity(recipient))


@notifications_router.delete(
    "/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a recipient (any signed-in user)"
)
async def delete_recipient(recipient_id: uuid.UUID, user: CurrentUser, scope: ScopeDep) -> Response:
    await notifications_factory.delete_recipient(scope).execute(recipient_id, actor_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
