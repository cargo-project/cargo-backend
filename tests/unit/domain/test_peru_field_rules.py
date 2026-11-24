"""Formatos de Perú para placa, documento, licencia y celular."""

from __future__ import annotations

import pytest

from app.modules.fleet.domain.exceptions.fleet_errors import InvalidFleetDataError
from app.modules.fleet.domain.services.field_rules import (
    normalise_identity_document,
    normalise_license,
    normalise_mobile_phone,
    normalise_plate,
)


@pytest.mark.parametrize(("raw", "expected"), [("ABC-123", "ABC-123"), ("f5u842", "F5U-842"), (" c7k 519 ", "C7K-519")])
def test_plate_is_normalised(raw: str, expected: str) -> None:
    assert normalise_plate(raw) == expected


@pytest.mark.parametrize("raw", ["AB-123", "ABCD-123", "ABC-12A", "EGW-PE-90001", ""])
def test_plate_rejects_other_formats(raw: str) -> None:
    with pytest.raises(InvalidFleetDataError):
        normalise_plate(raw)


@pytest.mark.parametrize(
    ("raw", "expected"), [("45781236", "45781236"), ("45.781.236", "45781236"), ("001234567", "001234567")]
)
def test_identity_document_accepts_dni_and_foreign_ids(raw: str, expected: str) -> None:
    assert normalise_identity_document(raw) == expected


@pytest.mark.parametrize("raw", ["1234567", "ABC", "1234567890123"])
def test_identity_document_rejects_other_formats(raw: str) -> None:
    with pytest.raises(InvalidFleetDataError):
        normalise_identity_document(raw)


@pytest.mark.parametrize(("raw", "expected"), [("Q45781236", "Q45781236"), ("q-45781236", "Q45781236")])
def test_license_is_normalised(raw: str, expected: str) -> None:
    assert normalise_license(raw) == expected


@pytest.mark.parametrize("raw", ["Q-12345", "45781236", "QQ4578123"])
def test_license_rejects_other_formats(raw: str) -> None:
    with pytest.raises(InvalidFleetDataError):
        normalise_license(raw)


@pytest.mark.parametrize(
    ("raw", "expected"), [("987654321", "987654321"), ("+51 987 654 321", "987654321"), ("987-654-321", "987654321")]
)
def test_mobile_phone_is_normalised(raw: str, expected: str) -> None:
    assert normalise_mobile_phone(raw) == expected


@pytest.mark.parametrize("raw", ["87654321", "887654321", "9876543210", "abc"])
def test_mobile_phone_rejects_other_formats(raw: str) -> None:
    with pytest.raises(InvalidFleetDataError):
        normalise_mobile_phone(raw)
