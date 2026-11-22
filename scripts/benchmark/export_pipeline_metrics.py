"""Exporta los tiempos de cada etapa del pipeline completo, evento por evento, desde la BD.

Etapas (todas con timestamps que ya guarda la plataforma):
* transmision_ms   = received_at - event_time de la lectura que disparó el evento (vehículo -> plataforma)
* procesamiento_ms = enriched_at - received_at (ingesta + PostGIS)
* cep_ms           = detected_at - enriched_at (outbox + MQTT + Siddhi)
* deteccion_ms     = detected_at - event_time del evento (KPI; en CONNECTION_LOSS el event_time es
                     última lectura + umbral, así que mide el retraso del trigger)
* registro_ms      = registered_at - detected_at (evento guardado y consultable por REST)
* web_ms           = llegada del aviso por WebSocket - detected_at (solo si se pasan los recibos)
* telegram_solicitud_ms = attempted_at - detected_at (cuándo se pidió el envío a Telegram)
* telegram_envio_ms     = sent_at - detected_at (Telegram confirmó)

    python -m scripts.benchmark.export_pipeline_metrics --since-minutes 60 --out benchmark-results/pipeline
    python -m scripts.benchmark.export_pipeline_metrics --trips TRP-261117-AB12,TRP-261117-CD34

Lee DATABASE_URL del entorno o del .env (en desarrollo PostgreSQL está en 127.0.0.1:5432).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from scripts.benchmark.metrics import summarize

STAGES = (
    "transmision_ms",
    "procesamiento_ms",
    "cep_ms",
    "deteccion_ms",
    "registro_ms",
    "web_ms",
    "telegram_solicitud_ms",
    "telegram_envio_ms",
)

_SQL = """
SELECT e.id::text AS event_id, t.code AS trip_code, e.event_type, e.event_time, e.detected_at, e.registered_at,
       te.event_time AS trigger_event_time, te.received_at, te.enriched_at, te.temporal_classification,
       n.created_at AS notification_created_at, n.attempted_at, n.sent_at, n.status AS notification_status
FROM monitoring_events e
JOIN trips t ON t.id = e.trip_id
LEFT JOIN LATERAL (
    SELECT te.* FROM monitoring_event_evidence ev JOIN telemetry_events te ON te.id = ev.telemetry_id
    WHERE ev.monitoring_event_id = e.id ORDER BY ev.sequence DESC LIMIT 1) te ON true
LEFT JOIN LATERAL (
    SELECT n.* FROM notifications n WHERE n.monitoring_event_id = e.id ORDER BY n.created_at LIMIT 1) n ON true
WHERE ($1::timestamptz IS NULL OR e.registered_at >= $1) AND ($2::text[] IS NULL OR t.code = ANY($2))
ORDER BY e.detected_at
"""


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    env_file = Path(".env")
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip()
    if not url:
        raise SystemExit("Falta DATABASE_URL (variable de entorno o .env)")
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _ms(later: datetime | None, earlier: datetime | None) -> float | None:
    return round((later - earlier).total_seconds() * 1000, 2) if later and earlier else None


def build_rows(records: list[dict[str, Any]], ws_receipts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    received_web = {r["event_id"]: r["received_ms"] for r in ws_receipts or []}
    rows = []
    for r in records:
        detected = r["detected_at"]
        web_ms = None
        if r["event_id"] in received_web:
            web_ms = round(received_web[r["event_id"]] - detected.timestamp() * 1000, 2)
        rows.append(
            {
                "event_id": r["event_id"],
                "trip_code": r["trip_code"],
                "event_type": r["event_type"],
                "temporal_classification": r["temporal_classification"],
                "event_time": r["event_time"].isoformat(),
                "detected_at": detected.isoformat(),
                "notification_status": r["notification_status"],
                "transmision_ms": _ms(r["received_at"], r["trigger_event_time"]),
                "procesamiento_ms": _ms(r["enriched_at"], r["received_at"]),
                # En la ausencia no hay lectura que dispare: detected - enriched sería el silencio entero.
                "cep_ms": None if r["event_type"] == "CONNECTION_LOSS" else _ms(detected, r["enriched_at"]),
                "deteccion_ms": _ms(detected, r["event_time"]),
                "registro_ms": _ms(r["registered_at"], detected),
                "web_ms": web_ms,
                "telegram_solicitud_ms": _ms(r["attempted_at"], detected),
                "telegram_envio_ms": _ms(r["sent_at"], detected),
            }
        )
    return rows


def stage_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = []
    for event_type in ["ALL", *sorted({r["event_type"] for r in rows})]:
        subset = [r for r in rows if event_type == "ALL" or r["event_type"] == event_type]
        for stage in STAGES:
            values = [r[stage] for r in subset if r[stage] is not None]
            stats = summarize(values)
            summary.append({"event_type": event_type, "stage": stage, **stats})
    return summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


async def export(
    out_dir: Path,
    *,
    since: datetime | None = None,
    trip_codes: list[str] | None = None,
    ws_receipts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    connection = await asyncpg.connect(_database_url())
    try:
        records = [dict(r) for r in await connection.fetch(_SQL, since, trip_codes)]
    finally:
        await connection.close()
    rows = build_rows(records, ws_receipts)
    out_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240 - archivos chicos, al final de la corrida
    _write_csv(out_dir / "pipeline_events.csv", rows)
    summary = stage_summary(rows)
    _write_csv(out_dir / "pipeline_summary.csv", summary)
    (out_dir / "pipeline_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Tiempos por etapa del pipeline completo (desde la BD).")
    parser.add_argument("--since-minutes", type=float, default=None, help="eventos registrados en los últimos N min")
    parser.add_argument("--trips", default="", help="códigos de viaje separados por coma")
    parser.add_argument("--ws-receipts", type=Path, default=None, help="ws_receipts.json de la prueba E2E")
    parser.add_argument("--out", type=Path, default=Path("benchmark-results") / "pipeline")
    args = parser.parse_args()
    since = datetime.now(UTC) - timedelta(minutes=args.since_minutes) if args.since_minutes else None
    receipts = json.loads(args.ws_receipts.read_text(encoding="utf-8")) if args.ws_receipts else None
    rows = asyncio.run(
        export(args.out, since=since, trip_codes=args.trips.split(",") if args.trips else None, ws_receipts=receipts)
    )
    print(f"{len(rows)} eventos exportados en {args.out}")  # noqa: T201 - reporte por consola


if __name__ == "__main__":
    main()
