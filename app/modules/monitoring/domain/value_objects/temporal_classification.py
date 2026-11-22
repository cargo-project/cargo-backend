from __future__ import annotations

from enum import StrEnum


class TemporalClassification(StrEnum):
    """LIVE es telemetría del presente y alimenta las reglas CEP operativas.
    DELAYED (ráfagas de store-and-forward, llegadas tarde) es solo historial.
    """

    LIVE = "LIVE"
    DELAYED = "DELAYED"
