from __future__ import annotations

import uuid

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.domain.entities.monitoring_event import (
    MonitoringEvent,
    MonitoringEventEvidence,
    MonitoringEventStatus,
    MonitoringEventType,
    Severity,
)
from app.modules.monitoring.domain.entities.telemetry_event import TelemetryEvent, TelemetryKind
from app.modules.monitoring.domain.repositories.monitoring_repositories import DuplicateTelemetryError
from app.modules.monitoring.domain.value_objects.spatial_context import (
    UNKNOWN_DISPLACEMENT,
    SpatialContext,
)
from app.modules.monitoring.domain.value_objects.temporal_classification import TemporalClassification
from app.modules.monitoring.infrastructure.persistence.monitoring_models import (
    MonitoringEventEvidenceModel,
    MonitoringEventModel,
    TelemetryEventModel,
)
from app.shared.domain.geo_point import GeoPoint


def _point(point: GeoPoint) -> WKTElement:
    return WKTElement(f"POINT({point.longitude} {point.latitude})", srid=4326)


class PostgresTelemetryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_message(self, message_id: uuid.UUID) -> bool:
        query = select(exists().where(TelemetryEventModel.message_id == message_id))
        return bool(await self._session.scalar(query))

    async def exists_sequence(self, trip_id: uuid.UUID, sequence: int) -> bool:
        query = select(exists().where(TelemetryEventModel.trip_id == trip_id, TelemetryEventModel.sequence == sequence))
        return bool(await self._session.scalar(query))

    async def get(self, telemetry_id: uuid.UUID) -> TelemetryEvent | None:
        m = await self._session.get(TelemetryEventModel, telemetry_id)
        if m is None:
            return None
        context = None
        if m.enriched_at is not None:
            context = SpatialContext(
                distance_to_destination_m=m.distance_to_destination_m or 0.0,
                inside_destination=bool(m.inside_destination),
                moving_away_m=m.moving_away_m or 0.0,
                displacement_window_m=(
                    m.displacement_window_m if m.displacement_window_m is not None else UNKNOWN_DISPLACEMENT
                ),
                zone_codes=tuple(m.zone_codes or ()),
            )
        return TelemetryEvent(
            id=m.id,
            message_id=m.message_id,
            device_id=m.device_id,
            trip_id=m.trip_id,
            sequence=m.sequence,
            event_time=m.event_time,
            received_at=m.received_at,
            position=GeoPoint(m.latitude, m.longitude),
            speed_kmh=m.speed_kmh,
            kind=TelemetryKind(m.kind),
            temporal_classification=TemporalClassification(m.temporal_classification),
            spatial_context=context,
            enriched_at=m.enriched_at,
        )

    async def add(self, telemetry: TelemetryEvent) -> None:
        self._session.add(
            TelemetryEventModel(
                id=telemetry.id,
                message_id=telemetry.message_id,
                device_id=telemetry.device_id,
                trip_id=telemetry.trip_id,
                sequence=telemetry.sequence,
                event_time=telemetry.event_time,
                received_at=telemetry.received_at,
                position=_point(telemetry.position),
                latitude=telemetry.position.latitude,
                longitude=telemetry.position.longitude,
                speed_kmh=telemetry.speed_kmh,
                kind=telemetry.kind.value,
                temporal_classification=telemetry.temporal_classification.value,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise DuplicateTelemetryError(str(error.orig)) from error

    async def save_enrichment(self, telemetry: TelemetryEvent) -> None:
        model = await self._session.get(TelemetryEventModel, telemetry.id)
        context = telemetry.spatial_context
        if model is None or context is None:
            return
        model.distance_to_destination_m = context.distance_to_destination_m
        model.moving_away_m = context.moving_away_m
        model.inside_destination = context.inside_destination
        model.displacement_window_m = context.displacement_window_m
        model.zone_codes = list(context.zone_codes)
        model.enriched_at = telemetry.enriched_at
        await self._session.flush()

    async def evidence_between(
        self, trip_id: uuid.UUID, from_sequence: int, to_sequence: int, limit: int
    ) -> tuple[MonitoringEventEvidence, ...]:
        rows = await self._session.execute(
            select(TelemetryEventModel.id, TelemetryEventModel.sequence)
            .where(
                TelemetryEventModel.trip_id == trip_id,
                TelemetryEventModel.sequence.between(from_sequence, to_sequence),
            )
            .order_by(TelemetryEventModel.sequence.desc())
            .limit(limit)
        )
        return tuple(
            sorted(
                (MonitoringEventEvidence(telemetry_id=r.id, sequence=r.sequence) for r in rows),
                key=lambda item: item.sequence,
            )
        )


class PostgresMonitoringEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, event_id: uuid.UUID) -> MonitoringEvent | None:
        m = await self._session.get(MonitoringEventModel, event_id)
        if m is None:
            return None
        evidence_rows = await self._session.scalars(
            select(MonitoringEventEvidenceModel).where(MonitoringEventEvidenceModel.monitoring_event_id == event_id)
        )
        position = None
        if m.position is not None:
            shape = to_shape(m.position)
            position = GeoPoint(latitude=shape.y, longitude=shape.x)
        return MonitoringEvent(
            id=m.id,
            trip_id=m.trip_id,
            event_type=MonitoringEventType(m.event_type),
            severity=Severity(m.severity),
            status=MonitoringEventStatus(m.status),
            event_time=m.event_time,
            detected_at=m.detected_at,
            registered_at=m.registered_at,
            started_at=m.started_at,
            position=position,
            details=dict(m.details),
            evidence=tuple(MonitoringEventEvidence(r.telemetry_id, r.sequence) for r in evidence_rows),
            reviewed_by=m.reviewed_by,
            reviewed_at=m.reviewed_at,
        )

    async def add_if_absent(self, event: MonitoringEvent) -> bool:
        statement = (
            pg_insert(MonitoringEventModel)
            .values(
                id=event.id,
                trip_id=event.trip_id,
                event_type=event.event_type.value,
                severity=event.severity.value,
                status=event.status.value,
                started_at=event.started_at,
                event_time=event.event_time,
                detected_at=event.detected_at,
                registered_at=event.registered_at,
                position=_point(event.position) if event.position else None,
                details=event.details,
            )
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(MonitoringEventModel.id)
        )
        inserted = await self._session.scalar(statement)
        if inserted is None:
            return False
        if event.evidence:
            await self._session.execute(
                pg_insert(MonitoringEventEvidenceModel).on_conflict_do_nothing(),
                [
                    {"monitoring_event_id": event.id, "telemetry_id": e.telemetry_id, "sequence": e.sequence}
                    for e in event.evidence
                ],
            )
        return True

    async def save(self, event: MonitoringEvent) -> None:
        model = await self._session.get(MonitoringEventModel, event.id)
        if model is None:
            await self.add_if_absent(event)
            return
        model.status = event.status.value
        model.reviewed_by = event.reviewed_by
        model.reviewed_at = event.reviewed_at
        await self._session.flush()
