from __future__ import annotations

import re

from app.modules.fleet.domain.exceptions.fleet_errors import InvalidFleetDataError

_CODE_PATTERN = re.compile(r"^[A-Z0-9-]{2,24}$")


def normalise_code(raw: str, *, label: str) -> str:
    """Los códigos públicos (TRK-003, DEV-GW-003) van en mayúsculas y sin caracteres raros para URL."""
    code = raw.strip().upper()
    if not _CODE_PATTERN.match(code):
        raise InvalidFleetDataError(f"El código de {label} debe tener 2-24 caracteres: letras, números o guiones.")
    return code


def require_text(value: str, *, label: str, min_length: int = 1, max_length: int = 120) -> str:
    cleaned = " ".join(value.split())
    if not min_length <= len(cleaned) <= max_length:
        raise InvalidFleetDataError(f"El campo {label} debe tener entre {min_length} y {max_length} caracteres.")
    return cleaned
