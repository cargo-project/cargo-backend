"""Cálculos de las métricas del banco: percentiles, resumen estadístico y TP/FP/FN.

Son funciones puras (sin red ni Docker) para poder probarlas con tests unitarios.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def percentile(values: Iterable[float], p: float) -> float | None:
    """Percentil p (0..100) con interpolación lineal, el mismo método por defecto de numpy."""
    data = sorted(values)
    if not data:
        return None
    if len(data) == 1:
        return data[0]
    rank = (p / 100) * (len(data) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    return data[low] + (data[high] - data[low]) * (rank - low)


def summarize(values: Iterable[float]) -> dict[str, float | int | None]:
    """Cantidad, promedio, mediana, p95, p99, mínimo y máximo de una serie."""
    data = list(values)
    if not data:
        return {"count": 0, "mean": None, "median": None, "p95": None, "p99": None, "min": None, "max": None}
    return {
        "count": len(data),
        "mean": sum(data) / len(data),
        "median": percentile(data, 50),
        "p95": percentile(data, 95),
        "p99": percentile(data, 99),
        "min": min(data),
        "max": max(data),
    }


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, other: Confusion) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def confusion_by_type(expected: Mapping[str, int], detected: Mapping[str, int]) -> dict[str, Confusion]:
    """Compara lo que debía detectarse con lo que detectó el CEP, por tipo de evento.

    Por cada tipo: TP = mínimo entre esperados y detectados, FP = detectados de más,
    FN = esperados que no aparecieron. Un tipo detectado que no se esperaba es todo FP.
    """
    result: dict[str, Confusion] = {}
    for event_type in sorted(set(expected) | set(detected)):
        want, got = expected.get(event_type, 0), detected.get(event_type, 0)
        tp = min(want, got)
        result[event_type] = Confusion(tp=tp, fp=got - tp, fn=want - tp)
    return result
