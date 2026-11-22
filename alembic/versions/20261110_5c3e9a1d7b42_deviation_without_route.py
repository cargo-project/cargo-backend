"""desviación sin ruta planificada: un viaje es solo origen + destino

* telemetry_events: moving_away_m (cuánto se pasó del punto más cercano al destino)
  reemplaza a distance_to_route_m y route_progress.
* Se elimina planned_routes: CarGO nunca propone ni guarda una ruta.
* Las configuraciones guardadas pierden route_deviation_corridor_m y
  route_deviation_min_increase_m pasa a ser el umbral de la desviación.

Revision ID: 5c3e9a1d7b42
Revises: ea2f1c6f6924
Create Date: 2026-11-10 23:30:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "5c3e9a1d7b42"
down_revision: str | None = "ea2f1c6f6924"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_MIN_INCREASE_M = 300

# Saca el corredor y deja el umbral de alejamiento dentro de los nuevos límites (>= 50 m).
_MIGRATE_CONFIG = """
UPDATE {table} SET {column} = jsonb_set(
    {column} - 'route_deviation_corridor_m',
    '{{route_deviation_min_increase_m}}',
    to_jsonb(CASE WHEN COALESCE(({column} ->> 'route_deviation_min_increase_m')::float, 0) < 50
                  THEN {default} ELSE ({column} ->> 'route_deviation_min_increase_m')::float END))
"""


def upgrade() -> None:
    op.add_column("telemetry_events", sa.Column("moving_away_m", sa.Float(), nullable=True))
    op.drop_column("telemetry_events", "distance_to_route_m")
    op.drop_column("telemetry_events", "route_progress")
    op.drop_geospatial_index(
        "idx_planned_routes_geometry", table_name="planned_routes", postgresql_using="gist", column_name="geometry"
    )
    op.drop_geospatial_table("planned_routes")
    op.execute(
        _MIGRATE_CONFIG.format(table="trips", column="monitoring_configuration", default=_DEFAULT_MIN_INCREASE_M)
    )
    op.execute(
        _MIGRATE_CONFIG.format(table="monitoring_defaults", column="configuration", default=_DEFAULT_MIN_INCREASE_M)
    )


def downgrade() -> None:
    # Las rutas planificadas no se pueden recuperar (no se guardaron); la tabla vuelve vacía.
    op.create_geospatial_table(
        "planned_routes",
        sa.Column("trip_id", sa.UUID(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(geometry_type="LINESTRING", srid=4326, dimension=2, spatial_index=False, nullable=False),
            nullable=False,
        ),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_planned_routes_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("trip_id", name=op.f("pk_planned_routes")),
    )
    op.create_geospatial_index(
        "idx_planned_routes_geometry", "planned_routes", ["geometry"], unique=False, postgresql_using="gist"
    )
    op.add_column("telemetry_events", sa.Column("route_progress", sa.Float(), nullable=True))
    op.add_column("telemetry_events", sa.Column("distance_to_route_m", sa.Float(), nullable=True))
    op.drop_column("telemetry_events", "moving_away_m")
    for table, column in (("trips", "monitoring_configuration"), ("monitoring_defaults", "configuration")):
        op.execute(f"UPDATE {table} SET {column} = {column} || '{{\"route_deviation_corridor_m\": 200.0}}'::jsonb")
