"""Dependencias de FastAPI que conectan con la raíz de composición."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from app.composition.resources import AppResources
from app.composition.scope import Scope, open_scope


def get_resources(request: Request) -> AppResources:
    resources: AppResources = request.app.state.resources
    return resources


async def get_scope(
    resources: Annotated[AppResources, Depends(get_resources)],
) -> AsyncIterator[Scope]:
    async with open_scope(resources) as scope:
        yield scope


ScopeDep = Annotated[Scope, Depends(get_scope)]
ResourcesDep = Annotated[AppResources, Depends(get_resources)]
