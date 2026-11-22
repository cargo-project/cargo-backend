"""Lee las estadísticas nativas de Siddhi que imprime el reporter de consola (Carbon Metrics).

El CEP de pruebas se construye con CEP_STATISTICS=true y cada 5 s escribe en su log bloques así:

    io.siddhi.SiddhiApps.CargoMonitoring.Siddhi.Queries.deviation-detect.latency
                 count = 200
                  mean = 0.08 milliseconds
                   95% <= 0.06 milliseconds

Nos quedamos con el último bloque de cada métrica (son acumulados desde que arrancó Siddhi).
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

_PREFIX = "io.siddhi.SiddhiApps."
_VALUE = re.compile(r"^\s*([\w.%\- ]+?)\s*(?:<=|=)\s*([-\d.]+)")


def parse(log: str, app: str = "CargoMonitoring") -> dict[str, dict[str, float]]:
    """Último valor de cada métrica de la app: {nombre: {campo: valor}}."""
    metrics: dict[str, dict[str, float]] = {}
    current: dict[str, float] | None = None
    for line in log.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{_PREFIX}{app}."):
            name = stripped[len(f"{_PREFIX}{app}.Siddhi.") :] if ".Siddhi." in stripped else stripped
            current = {}
            metrics[name] = current
            continue
        if current is None:
            continue
        match = _VALUE.match(line)
        if match:
            key = match.group(1).replace("%", "p")
            current.setdefault(key, float(match.group(2)))  # "value" de memoria se repite: el 1º es el total
        elif not stripped:
            current = None
    return metrics


def rows(metrics: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Filas planas para CSV: componente, tipo (latency/throughput/memory) y sus valores."""
    result = []
    for name, values in sorted(metrics.items()):
        group, _, rest = name.partition(".")
        component, _, kind = rest.rpartition(".")
        result.append(
            {
                "group": group,  # Queries | Streams | Sources | Sinks | SourceMappers | SinkMappers
                "component": component,
                "kind": kind,  # latency | throughput | memory
                "count": values.get("count"),
                "mean_rate_per_s": values.get("mean rate") if kind == "throughput" else None,
                "mean_ms": values.get("mean") if kind == "latency" else None,
                "median_ms": values.get("median"),
                "p95_ms": values.get("95p"),
                "p99_ms": values.get("99p"),
                "p999_ms": values.get("99.9p"),
                "max_ms": values.get("max") if kind == "latency" else None,
                "memory_bytes": values.get("value") if kind == "memory" else None,
            }
        )
    return result


def collect(container: str, since: str | None = None) -> dict[str, dict[str, float]]:
    command = ["docker", "logs", container]
    if since:
        command[2:2] = ["--since", since]
    output = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    return parse(output.stdout + output.stderr)
