"""Banco de pruebas del CEP (Siddhi real) para la validación experimental.

Mide, contra el contenedor de Siddhi:
1. Exactitud por escenario y por regla: TP, FP, FN, precision, recall y F1.
2. Latencia de detección por evento (p50/p95/p99), además de las estadísticas nativas de Siddhi
   (latencia y memoria por consulta, throughput por stream) si el CEP se construyó con CEP_STATISTICS=true:
   * cep_ms : detected_at (reloj de Siddhi) - momento en que se publicó la lectura que cumplió la condición.
   * e2e_ms : momento en que el banco recibe events/detected - ese mismo envío (mismo reloj, incluye MQTT).
   * En CONNECTION_LOSS la condición se cumple en (última lectura + umbral); incluye el trigger de 5 s.
3. Throughput: ráfagas de lecturas a distintas tasas y cuántas detecciones por segundo salen.
4. CPU y RAM del contenedor de Siddhi (docker stats) por fase.

Todo queda en benchmark-results/<fecha>/ en CSV y JSON, junto con las entradas usadas
(scenarios.json) y el entorno (environment.json), para poder repetir y graficar.

Se corre SOLO contra la infraestructura de pruebas (scripts/run_test_infra.ps1, broker en
127.0.0.1:51884), nunca contra la plataforma: ahí las detecciones mandarían Telegram.

    python -m scripts.benchmark.benchmark_cep
    python -m scripts.benchmark.benchmark_cep --repeat 5 --rates 50,200,500,1000
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import subprocess
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiomqtt

from scripts.benchmark import environment, siddhi_stats
from scripts.benchmark.metrics import Confusion, confusion_by_type, summarize
from scripts.benchmark.scenarios import BASE_CONFIG, BASE_READING, catalog, expand

logger = logging.getLogger("cargo.benchmark")
RULES = ("ROUTE_DEVIATION", "PROLONGED_STOP", "DESTINATION_ARRIVAL", "CONNECTION_LOSS", "EMERGENCY")


def now_ms() -> float:
    return time.time() * 1000


# --------------------------------------------------------------------------- recolección de detecciones
@dataclass
class Detection:
    received_ms: float
    event: dict[str, Any]


@dataclass
class Collector:
    by_trip: dict[str, list[Detection]] = field(default_factory=lambda: defaultdict(list))
    batches: int = 0  # mensajes que traían varios eventos juntos (Siddhi publica una lista)

    async def run(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            received = now_ms()
            body = json.loads(message.payload)  # type: ignore[arg-type]
            items = body if isinstance(body, list) else [body]
            if len(items) > 1:
                self.batches += 1
            for item in items:
                event = item.get("event", item)
                self.by_trip[event["trip_id"]].append(Detection(received, event))


# --------------------------------------------------------------------------- CPU / RAM del contenedor
class ResourceSampler:
    """Muestrea docker stats del contenedor de Siddhi en un hilo aparte, con la fase actual."""

    def __init__(self, container: str) -> None:
        self.container = container
        self.phase = "idle"
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            raw = subprocess.run(  # noqa: S603
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", self.container],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            if raw:
                data = json.loads(raw)
                self.samples.append(
                    {
                        "timestamp_ms": round(now_ms()),
                        "phase": self.phase,
                        "cpu_percent": float(data["CPUPerc"].rstrip("%") or 0),
                        "memory_mib": _to_mib(data["MemUsage"].split("/")[0]),
                        "memory_percent": float(data["MemPerc"].rstrip("%") or 0),
                    }
                )


def _to_mib(text: str) -> float:
    value = text.strip()
    units = {"GiB": 1024, "MiB": 1, "KiB": 1 / 1024, "GB": 1000**3 / 1024**2, "MB": 1000**2 / 1024**2, "kB": 1 / 1024}
    for unit, factor in units.items():
        if value.endswith(unit):
            return round(float(value[: -len(unit)]) * factor, 2)
    return float(value.rstrip("B") or 0) / 1024**2


# --------------------------------------------------------------------------- utilidades MQTT
async def publish(client: aiomqtt.Client, topic: str, payload: dict[str, Any]) -> None:
    await client.publish(topic, json.dumps(payload), qos=1)


def trip_started(trip_id: str, code: str, config: dict[str, Any]) -> dict[str, Any]:
    return {"trip_id": trip_id, "trip_code": code, **config}


async def warm_up(client: aiomqtt.Client, collector: Collector) -> None:
    """Siddhi dice "deployed" antes de que todas sus fuentes MQTT estén suscritas: esperamos que respondan."""
    probe = str(uuid.uuid4())
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        types = {d.event["event_type"] for d in collector.by_trip.get(probe, [])}
        if {"CONNECTION_LOSS", "EMERGENCY"} <= types:
            await publish(client, "trip/ended", {"trip_id": probe})
            return
        await publish(client, "trip/started", trip_started(probe, "PROBE", {**BASE_CONFIG, "connection_loss_ms": 1000}))
        reading = {**BASE_READING, "trip_id": probe, "sequence": 0, "event_time_ms": int(now_ms())}
        await publish(client, "telemetry/enriched", {**reading, "kind": "EMERGENCY"})
        await asyncio.sleep(3)
    raise RuntimeError("Siddhi no respondió en 120 s: ¿está levantada la infraestructura de pruebas?")


# --------------------------------------------------------------------------- 1. exactitud + latencia
async def run_scenario(
    client: aiomqtt.Client, spec: dict[str, Any], sent: dict[tuple[str, int], float], ended_early: bool
) -> None:
    trip_id = spec["trip_id"]
    for step in spec["steps"]:
        if "pause_s" in step:
            await asyncio.sleep(step["pause_s"])
            continue
        reading = step["reading"]
        sent[(trip_id, reading["sequence"])] = now_ms()
        await publish(client, "telemetry/enriched", reading)
        await asyncio.sleep(0.02)  # mismo orden de llegada, sin saturar el broker
    await asyncio.sleep(1.5)  # deja que la última lectura se evalúe antes de cerrar el viaje
    if not ended_early:
        await publish(client, "trip/ended", {"trip_id": trip_id})


async def accuracy_round(
    client: aiomqtt.Client, collector: Collector, repetition: int, only: set[str] | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios = [s for s in catalog() if not only or s.id in only]
    start = int(now_ms())
    specs = [expand(s, str(uuid.uuid4()), start) for s in scenarios]
    for spec in specs:
        await publish(client, "trip/started", trip_started(spec["trip_id"], spec["id"], spec["config"]))
    await asyncio.sleep(2)
    for spec in specs:
        if spec["end_trip_first"]:
            await publish(client, "trip/ended", {"trip_id": spec["trip_id"]})
    await asyncio.sleep(1)

    sent: dict[tuple[str, int], float] = {}
    # Los de ausencia necesitan esperar en tiempo real: corren en paralelo. El resto va de a uno,
    # así la latencia medida no incluye la cola del cliente MQTT por publicar muchos a la vez.
    waiting = [spec for spec in specs if any("pause_s" in step for step in spec["steps"])]
    quick = [spec for spec in specs if spec not in waiting]

    async def one_by_one() -> None:
        for spec in quick:
            await run_scenario(client, spec, sent, spec["end_trip_first"])

    await asyncio.gather(one_by_one(), *(run_scenario(client, s, sent, s["end_trip_first"]) for s in waiting))
    await asyncio.sleep(8)  # detecciones tardías (p. ej. el trigger de ausencia)

    scenario_rows, detection_rows = [], []
    for spec in specs:
        detections = collector.by_trip.get(spec["trip_id"], [])
        detected = Counter(d.event["event_type"] for d in detections)
        matrix = confusion_by_type(spec["expected"], detected)
        totals = Confusion()
        for value in matrix.values():
            totals.add(value)
        scenario_rows.append(
            {
                "repetition": repetition,
                "scenario_id": spec["id"],
                "rule": spec["rule"],
                "category": spec["category"],
                "description": spec["description"],
                "expected": json.dumps(spec["expected"], sort_keys=True),
                "detected": json.dumps(dict(detected), sort_keys=True),
                "tp": totals.tp,
                "fp": totals.fp,
                "fn": totals.fn,
                "passed": totals.fp == 0 and totals.fn == 0,
            }
        )
        for d in detections:
            detection_rows.append(_detection_row(repetition, spec, d, sent))
    return scenario_rows, detection_rows, specs


def _detection_row(
    repetition: int, spec: dict[str, Any], d: Detection, sent: dict[tuple[str, int], float]
) -> dict[str, Any]:
    event, trip_id = d.event, spec["trip_id"]
    sequence = event.get("evidence_to_sequence")
    trigger_sent = sent.get((trip_id, sequence)) if sequence is not None else None
    if event["event_type"] == "CONNECTION_LOSS" and trigger_sent is not None:
        condition_ms = trigger_sent + spec["config"]["connection_loss_ms"]
    else:
        condition_ms = trigger_sent
    detected_at = float(event["detected_at_ms"])
    return {
        "repetition": repetition,
        "scenario_id": spec["id"],
        "event_type": event["event_type"],
        "expected": spec["expected"].get(event["event_type"], 0) > 0,
        "evidence_from_sequence": event.get("evidence_from_sequence"),
        "evidence_to_sequence": sequence,
        "metric_value": event.get("metric_value"),
        "delayed": event.get("delayed"),
        "condition_met_ms": round(condition_ms, 1) if condition_ms else None,
        "detected_at_ms": detected_at,
        "received_ms": round(d.received_ms, 1),
        "cep_ms": round(detected_at - condition_ms, 2) if condition_ms else None,
        "e2e_ms": round(d.received_ms - condition_ms, 2) if condition_ms else None,
    }


# --------------------------------------------------------------------------- 3. throughput
async def throughput_run(client: aiomqtt.Client, collector: Collector, rate: int, seconds: float) -> dict[str, Any]:
    """Manda lecturas EMERGENCY (cada una produce una detección) a la tasa pedida."""
    trip_id, total = str(uuid.uuid4()), max(1, int(rate * seconds))
    sent: dict[int, float] = {}
    base_event_ms = int(now_ms())
    start = time.perf_counter()
    for i in range(total):
        target = start + i / rate
        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        reading = {
            **BASE_READING,
            "trip_id": trip_id,
            "sequence": i + 1,
            "event_time_ms": base_event_ms + i,
            "kind": "EMERGENCY",
        }
        sent[i + 1] = now_ms()
        await publish(client, "telemetry/enriched", reading)
    send_seconds = time.perf_counter() - start
    wait_s = max(20.0, seconds * 4)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and len(collector.by_trip.get(trip_id, [])) < total:  # noqa: ASYNC110
        await asyncio.sleep(0.2)  # espera simple con tope: no hace falta un Event para un script de medición
    detections = collector.by_trip.get(trip_id, [])
    latencies = [d.received_ms - sent[d.event["evidence_to_sequence"]] for d in detections]
    span_ms = (max(d.received_ms for d in detections) - min(sent.values())) if detections else 0
    stats = summarize(latencies)
    return {
        "target_rate_per_s": rate,
        "sent": total,
        "received": len(detections),
        # No es pérdida comprobada: son detecciones que no llegaron dentro de la espera (seguían en cola).
        "not_received_within_wait": total - len(detections),
        "wait_s": wait_s,
        "achieved_input_rate_per_s": round(total / send_seconds, 1) if send_seconds else None,
        "output_rate_per_s": round(len(detections) / (span_ms / 1000), 1) if span_ms else None,
        **{f"latency_{k}_ms": (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()},
    }


# --------------------------------------------------------------------------- exportación
def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def rule_summary(scenario_rows: list[dict[str, Any]], detection_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_rule: dict[str, Confusion] = {rule: Confusion() for rule in RULES}
    for row in scenario_rows:
        matrix = confusion_by_type(json.loads(row["expected"]), json.loads(row["detected"]))
        for event_type, value in matrix.items():
            by_rule.setdefault(event_type, Confusion()).add(value)
    negatives = Counter()
    passed_negatives = Counter()
    for row in scenario_rows:
        if json.loads(row["expected"]).get(row["rule"], 0) == 0:
            negatives[row["rule"]] += 1
            passed_negatives[row["rule"]] += int(json.loads(row["detected"]).get(row["rule"], 0) == 0)
    rows = []
    for rule, matrix in by_rule.items():
        latencies = [r["cep_ms"] for r in detection_rows if r["event_type"] == rule and r["expected"] and r["cep_ms"]]
        e2e = [r["e2e_ms"] for r in detection_rows if r["event_type"] == rule and r["expected"] and r["e2e_ms"]]
        cep, end = summarize(latencies), summarize(e2e)
        rows.append(
            {
                "rule": rule,
                **matrix.as_dict(),
                "negative_scenarios": negatives[rule],
                "negative_scenarios_without_alert": passed_negatives[rule],
                "cep_latency_mean_ms": cep["mean"],
                "cep_latency_p50_ms": cep["median"],
                "cep_latency_p95_ms": cep["p95"],
                "cep_latency_p99_ms": cep["p99"],
                "e2e_latency_p50_ms": end["median"],
                "e2e_latency_p95_ms": end["p95"],
                "samples": cep["count"],
            }
        )
    return rows


def resource_summary(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for phase in dict.fromkeys(s["phase"] for s in samples):
        cpu = summarize(s["cpu_percent"] for s in samples if s["phase"] == phase)
        mem = summarize(s["memory_mib"] for s in samples if s["phase"] == phase)
        rows.append(
            {
                "phase": phase,
                "samples": cpu["count"],
                "cpu_mean_percent": cpu["mean"],
                "cpu_p95_percent": cpu["p95"],
                "cpu_max_percent": cpu["max"],
                "memory_mean_mib": mem["mean"],
                "memory_max_mib": mem["max"],
            }
        )
    return rows


# --------------------------------------------------------------------------- main
async def main(args: argparse.Namespace) -> int:
    run_dir = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    sampler = ResourceSampler(args.container)
    sampler.start()
    collector = Collector()
    only = set(args.scenarios.split(",")) if args.scenarios else None
    rates = [int(r) for r in args.rates.split(",") if r.strip()]

    async with aiomqtt.Client(args.host, args.port, identifier=f"cargo-bench-{uuid.uuid4().hex[:6]}") as client:
        await client.subscribe("events/detected", qos=1)
        listener = asyncio.create_task(collector.run(client))
        logger.info("esperando a que Siddhi responda (calentamiento)...")
        await warm_up(client, collector)
        await asyncio.sleep(args.idle_seconds)  # línea base de CPU/RAM en reposo

        scenario_rows, detection_rows, inputs = [], [], []
        for repetition in range(1, args.repeat + 1):
            sampler.phase = f"accuracy-{repetition}"
            logger.info("exactitud: repetición %s de %s", repetition, args.repeat)
            rows, detections, specs = await accuracy_round(client, collector, repetition, only)
            scenario_rows += rows
            detection_rows += detections
            inputs += [{"repetition": repetition, **spec} for spec in specs]

        throughput_rows = []
        for rate in rates:
            sampler.phase = f"throughput-{rate}"
            logger.info("throughput: %s lecturas/s durante %s s", rate, args.throughput_seconds)
            throughput_rows.append(await throughput_run(client, collector, rate, args.throughput_seconds))
            await asyncio.sleep(3)
        sampler.phase = "cooldown"
        await asyncio.sleep(3)
        listener.cancel()
    sampler.stop()

    await asyncio.sleep(6)  # un ciclo más del reporter de consola (cada 5 s) para tener los acumulados finales
    native = siddhi_stats.rows(siddhi_stats.collect(args.container))
    rules = rule_summary(scenario_rows, detection_rows)
    resources = resource_summary(sampler.samples)
    write_csv(run_dir / "siddhi_native_metrics.csv", native)
    write_csv(run_dir / "scenarios_results.csv", scenario_rows)
    write_csv(run_dir / "detections.csv", detection_rows)
    write_csv(run_dir / "rules_summary.csv", rules)
    write_csv(run_dir / "throughput.csv", throughput_rows)
    write_csv(run_dir / "resources.csv", sampler.samples)
    write_csv(run_dir / "resources_summary.csv", resources)
    (run_dir / "scenarios.json").write_text(json.dumps(inputs, indent=1, ensure_ascii=False), encoding="utf-8")
    (run_dir / "environment.json").write_text(
        json.dumps(
            environment.capture(
                args.container,
                {
                    "benchmark": {
                        "broker": f"{args.host}:{args.port}",
                        "repeat": args.repeat,
                        "rates": rates,
                        "throughput_seconds": args.throughput_seconds,
                        "base_config": BASE_CONFIG,
                    }
                },
            ),
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    passed = sum(row["passed"] for row in scenario_rows)
    summary = {
        "scenarios_run": len(scenario_rows),
        "scenarios_passed": passed,
        "rules": rules,
        "throughput": throughput_rows,
        "resources": resources,
        "siddhi_native_metrics": native,
        "batched_messages": collector.batches,
    }
    if not native:
        logger.warning("sin estadísticas nativas: ¿el CEP se construyó con CEP_STATISTICS=true?")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nResultados en {run_dir}")  # noqa: T201 - reporte por consola
    print(f"Escenarios: {passed}/{len(scenario_rows)} correctos")  # noqa: T201
    for row in rules:
        print(  # noqa: T201
            f"  {row['rule']:<20} TP={row['tp']} FP={row['fp']} FN={row['fn']} "
            f"F1={row['f1'] if row['f1'] is None else round(row['f1'], 3)} p95={row['cep_latency_p95_ms']}"
        )
    return 0 if passed == len(scenario_rows) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Banco de pruebas del CEP de CarGO (Siddhi real).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=51884, help="broker de la infraestructura de pruebas")
    parser.add_argument("--container", default="cargo-v2-cep-siddhi", help="contenedor de Siddhi para CPU/RAM")
    parser.add_argument("--repeat", type=int, default=3, help="repeticiones del catálogo de escenarios")
    parser.add_argument("--scenarios", default="", help="ids separados por coma (vacío = todos)")
    parser.add_argument("--rates", default="50,200,500,1000", help="tasas de throughput (lecturas/s); vacío = omitir")
    parser.add_argument("--throughput-seconds", type=float, default=5.0)
    parser.add_argument("--idle-seconds", type=float, default=5.0)
    parser.add_argument("--out", default="benchmark-results")
    return parser.parse_args()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # aiomqtt necesita add_reader()
    raise SystemExit(asyncio.run(main(parse_args())))
