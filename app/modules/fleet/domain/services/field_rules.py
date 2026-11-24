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


# --- Formatos de Perú -------------------------------------------------------------------
# Placa vigente: 3 letras o números + 3 dígitos (ABC-123, F5U-842). Se guarda con guion.
_PLATE = re.compile(r"^[A-Z0-9]{3}\d{3}$")
# DNI: 8 dígitos. Carné de extranjería o pasaporte: 9 a 12 letras o números.
_DNI = re.compile(r"^\d{8}$")
_FOREIGN_DOCUMENT = re.compile(r"^[A-Z0-9]{9,12}$")
# Licencia de conducir (MTC): una letra + 8 dígitos (Q + DNI).
_LICENSE = re.compile(r"^[A-Z]\d{8}$")
# Celular: 9 dígitos que empiezan con 9 (se acepta el prefijo +51).
_MOBILE = re.compile(r"^9\d{8}$")


def _compact(value: str, separators: str) -> str:
    return re.sub(rf"[\s{re.escape(separators)}]", "", value).upper()


def normalise_plate(raw: str) -> str:
    plate = _compact(raw, "-")
    if not _PLATE.match(plate):
        raise InvalidFleetDataError("La placa debe tener el formato peruano ABC-123 (3 letras o números y 3 dígitos).")
    return f"{plate[:3]}-{plate[3:]}"


def normalise_identity_document(raw: str) -> str:
    document = _compact(raw, ".-")
    if not (_DNI.match(document) or _FOREIGN_DOCUMENT.match(document)):
        raise InvalidFleetDataError(
            "El documento debe ser un DNI de 8 dígitos o un carné de extranjería/pasaporte de 9 a 12 caracteres."
        )
    return document


def normalise_license(raw: str) -> str:
    license_number = _compact(raw, "-")
    if not _LICENSE.match(license_number):
        raise InvalidFleetDataError("La licencia debe tener una letra y 8 dígitos (por ejemplo Q45781236).")
    return license_number


def normalise_mobile_phone(raw: str) -> str:
    phone = _compact(raw, "-().")
    if phone.startswith("+51"):
        phone = phone[3:]
    elif phone.startswith("0051"):
        phone = phone[4:]
    if not _MOBILE.match(phone):
        raise InvalidFleetDataError("El celular debe tener 9 dígitos y empezar con 9 (por ejemplo 987654321).")
    return phone
