"""Identidad de las entidades: dos entidades son iguales si tienen el mismo id."""

from __future__ import annotations

from uuid import UUID


class Entity:
    id: UUID

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other.id == self.id

    def __hash__(self) -> int:
        return hash((type(self), self.id))
