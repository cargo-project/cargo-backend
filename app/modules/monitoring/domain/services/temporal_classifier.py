from __future__ import annotations

from datetime import datetime, timedelta

from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification


class TemporalClassifier:
    """Separa la telemetría en tiempo real de la histórica (store-and-forward).

    Ejemplo: generada 10:05, recibida 10:31 -> DELAYED. Se guarda y se ve en el
    historial del viaje, pero CEP no saca alertas "actuales" con ella.
    """

    def __init__(self, live_tolerance: timedelta) -> None:
        self._live_tolerance = live_tolerance

    def classify(self, *, event_time: datetime, received_at: datetime, trip_is_ongoing: bool) -> TemporalClassification:
        if not trip_is_ongoing:
            return TemporalClassification.DELAYED
        if received_at - event_time <= self._live_tolerance:
            return TemporalClassification.LIVE
        return TemporalClassification.DELAYED
