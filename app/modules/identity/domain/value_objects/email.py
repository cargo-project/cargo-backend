from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.identity.domain.exceptions.identity_errors import InvalidEmailError

_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


@dataclass(frozen=True, slots=True)
class Email:
    """Correo normalizado (minúsculas, sin espacios); es el usuario para iniciar sesión."""

    value: str

    def __post_init__(self) -> None:
        normalised = self.value.strip().lower()
        if len(normalised) > 254 or not _EMAIL_PATTERN.match(normalised):
            raise InvalidEmailError("El correo electrónico no es válido.")
        object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value
