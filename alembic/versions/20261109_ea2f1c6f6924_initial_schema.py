"""esquema inicial: identidad, flota, viajes, monitoreo, notificaciones, configuración y outbox

Revision ID: ea2f1c6f6924
Revises:
Create Date: 2026-11-09 20:37:02.854084
"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = 'ea2f1c6f6924'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostGIS da los tipos geométricos, los índices espaciales y las funciones ST_* (SRID 4326).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    # ### comandos generados por Alembic (revisados a mano) ###
    op.create_table('audit_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=40), nullable=False),
    sa.Column('entity_id', sa.String(length=80), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
    op.create_index(op.f('ix_audit_log_entity_id'), 'audit_log', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_log_occurred_at'), 'audit_log', ['occurred_at'], unique=False)
    op.create_table('clients',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('tax_id', sa.String(length=30), nullable=True),
    sa.Column('contact_email', sa.String(length=254), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clients'))
    )
    op.create_table('drivers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=24), nullable=False),
    sa.Column('first_name', sa.String(length=60), nullable=False),
    sa.Column('last_name', sa.String(length=60), nullable=False),
    sa.Column('document_number', sa.String(length=20), nullable=False),
    sa.Column('license_number', sa.String(length=20), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_drivers')),
    sa.UniqueConstraint('code', name=op.f('uq_drivers_code')),
    sa.UniqueConstraint('document_number', name=op.f('uq_drivers_document_number'))
    )
    op.create_index(op.f('ix_drivers_status'), 'drivers', ['status'], unique=False)
    op.create_table('integration_outbox',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('topic', sa.String(length=200), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('retain', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_integration_outbox'))
    )
    op.create_index(op.f('ix_integration_outbox_created_at'), 'integration_outbox', ['created_at'], unique=False)
    op.create_table('monitoring_defaults',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monitoring_defaults'))
    )
    op.create_table('notification_recipients',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('telegram_chat_id', sa.String(length=32), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_recipients'))
    )
    op.create_index(op.f('ix_notification_recipients_telegram_chat_id'), 'notification_recipients', ['telegram_chat_id'], unique=False)
    op.create_table('system_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_name', sa.String(length=120), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('distance_unit', sa.String(length=4), nullable=False),
    sa.Column('default_language', sa.String(length=4), nullable=False),
    sa.Column('telegram_enabled', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_system_settings'))
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('telegram_chat_id', sa.String(length=32), nullable=True),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('vehicles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=24), nullable=False),
    sa.Column('plate', sa.String(length=16), nullable=False),
    sa.Column('brand', sa.String(length=60), nullable=False),
    sa.Column('model', sa.String(length=60), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicles')),
    sa.UniqueConstraint('code', name=op.f('uq_vehicles_code')),
    sa.UniqueConstraint('plate', name=op.f('uq_vehicles_plate'))
    )
    op.create_index(op.f('ix_vehicles_status'), 'vehicles', ['status'], unique=False)
    op.create_table('iot_devices',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=24), nullable=False),
    sa.Column('device_type', sa.String(length=20), nullable=False),
    sa.Column('serial_number', sa.String(length=60), nullable=False),
    sa.Column('firmware_version', sa.String(length=30), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=True),
    sa.Column('last_connection_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name=op.f('fk_iot_devices_vehicle_id_vehicles'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_iot_devices')),
    sa.UniqueConstraint('code', name=op.f('uq_iot_devices_code'))
    )
    op.create_index(op.f('ix_iot_devices_vehicle_id'), 'iot_devices', ['vehicle_id'], unique=False)
    op.create_index('uq_iot_devices_one_gateway_per_vehicle', 'iot_devices', ['vehicle_id'], unique=True, postgresql_where=sa.text("device_type = 'edge_gateway' AND is_active AND vehicle_id IS NOT NULL"))
    op.create_table('refresh_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_sessions_token_hash'))
    )
    op.create_index(op.f('ix_refresh_sessions_family_id'), 'refresh_sessions', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_sessions_user_id'), 'refresh_sessions', ['user_id'], unique=False)
    op.create_geospatial_table('trips',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('driver_id', sa.UUID(), nullable=False),
    sa.Column('device_id', sa.UUID(), nullable=True),
    sa.Column('client_id', sa.UUID(), nullable=True),
    sa.Column('origin_label', sa.String(length=300), nullable=False),
    sa.Column('origin', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('destination_label', sa.String(length=300), nullable=False),
    sa.Column('destination', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('cargo_description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('monitoring_configuration', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('planned_start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_reason', sa.String(length=60), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_trips_client_id_clients')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_trips_created_by_users')),
    sa.ForeignKeyConstraint(['device_id'], ['iot_devices.id'], name=op.f('fk_trips_device_id_iot_devices')),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], name=op.f('fk_trips_driver_id_drivers')),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name=op.f('fk_trips_vehicle_id_vehicles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_trips')),
    sa.UniqueConstraint('code', name=op.f('uq_trips_code'))
    )
    op.create_geospatial_index('idx_trips_destination', 'trips', ['destination'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_geospatial_index('idx_trips_origin', 'trips', ['origin'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_trips_created_at'), 'trips', ['created_at'], unique=False)
    op.create_index(op.f('ix_trips_driver_id'), 'trips', ['driver_id'], unique=False)
    op.create_index(op.f('ix_trips_status'), 'trips', ['status'], unique=False)
    op.create_index(op.f('ix_trips_vehicle_id'), 'trips', ['vehicle_id'], unique=False)
    op.create_index('uq_trips_ongoing_driver', 'trips', ['driver_id'], unique=True, postgresql_where=sa.text("status = 'ongoing'"))
    op.create_index('uq_trips_ongoing_vehicle', 'trips', ['vehicle_id'], unique=True, postgresql_where=sa.text("status = 'ongoing'"))
    op.create_table('vehicle_device_assignments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['iot_devices.id'], name=op.f('fk_vehicle_device_assignments_device_id_iot_devices')),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name=op.f('fk_vehicle_device_assignments_vehicle_id_vehicles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_device_assignments'))
    )
    op.create_index(op.f('ix_vehicle_device_assignments_vehicle_id'), 'vehicle_device_assignments', ['vehicle_id'], unique=False)
    op.create_index('uq_vehicle_device_assignments_open_device', 'vehicle_device_assignments', ['device_id'], unique=True, postgresql_where=sa.text('released_at IS NULL'))
    op.create_geospatial_table('geofences',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=48), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=True),
    sa.Column('area', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_geofences_trip_id_trips'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_geofences')),
    sa.UniqueConstraint('code', name=op.f('uq_geofences_code'))
    )
    op.create_geospatial_index('idx_geofences_area', 'geofences', ['area'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('uq_geofences_destination_per_trip', 'geofences', ['trip_id'], unique=True, postgresql_where=sa.text("kind = 'destination'"))
    op.create_geospatial_table('monitoring_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('severity', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('position', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_monitoring_events_reviewed_by_users')),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_monitoring_events_trip_id_trips')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monitoring_events'))
    )
    op.create_geospatial_index('idx_monitoring_events_position', 'monitoring_events', ['position'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index(op.f('ix_monitoring_events_event_type'), 'monitoring_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_monitoring_events_status'), 'monitoring_events', ['status'], unique=False)
    op.create_index('ix_monitoring_events_trip_detected', 'monitoring_events', ['trip_id', 'detected_at'], unique=False)
    op.create_geospatial_table('planned_routes',
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('geometry', Geometry(geometry_type='LINESTRING', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('distance_m', sa.Float(), nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_planned_routes_trip_id_trips'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('trip_id', name=op.f('pk_planned_routes'))
    )
    op.create_geospatial_index('idx_planned_routes_geometry', 'planned_routes', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_geospatial_table('telemetry_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('message_id', sa.UUID(), nullable=False),
    sa.Column('device_id', sa.UUID(), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.BigInteger(), nullable=False),
    sa.Column('event_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('position', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('speed_kmh', sa.Float(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('temporal_classification', sa.String(length=10), nullable=False),
    sa.Column('distance_to_route_m', sa.Float(), nullable=True),
    sa.Column('distance_to_destination_m', sa.Float(), nullable=True),
    sa.Column('inside_destination', sa.Boolean(), nullable=True),
    sa.Column('displacement_window_m', sa.Float(), nullable=True),
    sa.Column('route_progress', sa.Float(), nullable=True),
    sa.Column('zone_codes', postgresql.ARRAY(sa.String(length=48)), nullable=True),
    sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['device_id'], ['iot_devices.id'], name=op.f('fk_telemetry_events_device_id_iot_devices')),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_telemetry_events_trip_id_trips')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_telemetry_events')),
    sa.UniqueConstraint('message_id', name=op.f('uq_telemetry_events_message_id')),
    sa.UniqueConstraint('trip_id', 'sequence', name='uq_telemetry_events_trip_sequence')
    )
    op.create_geospatial_index('idx_telemetry_events_position', 'telemetry_events', ['position'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_telemetry_events_trip_event_time', 'telemetry_events', ['trip_id', 'event_time'], unique=False)
    op.create_table('trip_notification_recipients',
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('recipient_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['recipient_id'], ['notification_recipients.id'], name=op.f('fk_trip_notification_recipients_recipient_id_notification_recipients')),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_trip_notification_recipients_trip_id_trips'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('trip_id', 'recipient_id', name=op.f('pk_trip_notification_recipients'))
    )
    op.create_table('vehicle_driver_assignments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('vehicle_id', sa.UUID(), nullable=False),
    sa.Column('driver_id', sa.UUID(), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['driver_id'], ['drivers.id'], name=op.f('fk_vehicle_driver_assignments_driver_id_drivers')),
    sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], name=op.f('fk_vehicle_driver_assignments_trip_id_trips')),
    sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], name=op.f('fk_vehicle_driver_assignments_vehicle_id_vehicles')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vehicle_driver_assignments'))
    )
    op.create_index(op.f('ix_vehicle_driver_assignments_driver_id'), 'vehicle_driver_assignments', ['driver_id'], unique=False)
    op.create_index(op.f('ix_vehicle_driver_assignments_trip_id'), 'vehicle_driver_assignments', ['trip_id'], unique=False)
    op.create_index(op.f('ix_vehicle_driver_assignments_vehicle_id'), 'vehicle_driver_assignments', ['vehicle_id'], unique=False)
    op.create_table('monitoring_event_evidence',
    sa.Column('monitoring_event_id', sa.UUID(), nullable=False),
    sa.Column('telemetry_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['monitoring_event_id'], ['monitoring_events.id'], name=op.f('fk_monitoring_event_evidence_monitoring_event_id_monitoring_events'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['telemetry_id'], ['telemetry_events.id'], name=op.f('fk_monitoring_event_evidence_telemetry_id_telemetry_events')),
    sa.PrimaryKeyConstraint('monitoring_event_id', 'telemetry_id', name=op.f('pk_monitoring_event_evidence'))
    )
    op.create_table('notifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('monitoring_event_id', sa.UUID(), nullable=False),
    sa.Column('recipient_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=20), nullable=False),
    sa.Column('destination', sa.String(length=64), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['monitoring_event_id'], ['monitoring_events.id'], name=op.f('fk_notifications_monitoring_event_id_monitoring_events'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_id'], ['notification_recipients.id'], name=op.f('fk_notifications_recipient_id_notification_recipients')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('monitoring_event_id', 'recipient_id', 'channel', name=op.f('uq_notifications_monitoring_event_id_recipient_id_channel'))
    )
    op.create_index(op.f('ix_notifications_monitoring_event_id'), 'notifications', ['monitoring_event_id'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    # ### fin de los comandos de Alembic ###


def downgrade() -> None:
    # ### comandos generados por Alembic (revisados a mano) ###
    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_monitoring_event_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('monitoring_event_evidence')
    op.drop_index(op.f('ix_vehicle_driver_assignments_vehicle_id'), table_name='vehicle_driver_assignments')
    op.drop_index(op.f('ix_vehicle_driver_assignments_trip_id'), table_name='vehicle_driver_assignments')
    op.drop_index(op.f('ix_vehicle_driver_assignments_driver_id'), table_name='vehicle_driver_assignments')
    op.drop_table('vehicle_driver_assignments')
    op.drop_table('trip_notification_recipients')
    op.drop_index('ix_telemetry_events_trip_event_time', table_name='telemetry_events')
    op.drop_geospatial_index('idx_telemetry_events_position', table_name='telemetry_events', postgresql_using='gist', column_name='position')
    op.drop_geospatial_table('telemetry_events')
    op.drop_geospatial_index('idx_planned_routes_geometry', table_name='planned_routes', postgresql_using='gist', column_name='geometry')
    op.drop_geospatial_table('planned_routes')
    op.drop_index('ix_monitoring_events_trip_detected', table_name='monitoring_events')
    op.drop_index(op.f('ix_monitoring_events_status'), table_name='monitoring_events')
    op.drop_index(op.f('ix_monitoring_events_event_type'), table_name='monitoring_events')
    op.drop_geospatial_index('idx_monitoring_events_position', table_name='monitoring_events', postgresql_using='gist', column_name='position')
    op.drop_geospatial_table('monitoring_events')
    op.drop_index('uq_geofences_destination_per_trip', table_name='geofences', postgresql_where=sa.text("kind = 'destination'"))
    op.drop_geospatial_index('idx_geofences_area', table_name='geofences', postgresql_using='gist', column_name='area')
    op.drop_geospatial_table('geofences')
    op.drop_index('uq_vehicle_device_assignments_open_device', table_name='vehicle_device_assignments', postgresql_where=sa.text('released_at IS NULL'))
    op.drop_index(op.f('ix_vehicle_device_assignments_vehicle_id'), table_name='vehicle_device_assignments')
    op.drop_table('vehicle_device_assignments')
    op.drop_index('uq_trips_ongoing_vehicle', table_name='trips', postgresql_where=sa.text("status = 'ongoing'"))
    op.drop_index('uq_trips_ongoing_driver', table_name='trips', postgresql_where=sa.text("status = 'ongoing'"))
    op.drop_index(op.f('ix_trips_vehicle_id'), table_name='trips')
    op.drop_index(op.f('ix_trips_status'), table_name='trips')
    op.drop_index(op.f('ix_trips_driver_id'), table_name='trips')
    op.drop_index(op.f('ix_trips_created_at'), table_name='trips')
    op.drop_geospatial_index('idx_trips_origin', table_name='trips', postgresql_using='gist', column_name='origin')
    op.drop_geospatial_index('idx_trips_destination', table_name='trips', postgresql_using='gist', column_name='destination')
    op.drop_geospatial_table('trips')
    op.drop_index(op.f('ix_refresh_sessions_user_id'), table_name='refresh_sessions')
    op.drop_index(op.f('ix_refresh_sessions_family_id'), table_name='refresh_sessions')
    op.drop_table('refresh_sessions')
    op.drop_index('uq_iot_devices_one_gateway_per_vehicle', table_name='iot_devices', postgresql_where=sa.text("device_type = 'edge_gateway' AND is_active AND vehicle_id IS NOT NULL"))
    op.drop_index(op.f('ix_iot_devices_vehicle_id'), table_name='iot_devices')
    op.drop_table('iot_devices')
    op.drop_index(op.f('ix_vehicles_status'), table_name='vehicles')
    op.drop_table('vehicles')
    op.drop_table('users')
    op.drop_table('system_settings')
    op.drop_index(op.f('ix_notification_recipients_telegram_chat_id'), table_name='notification_recipients')
    op.drop_table('notification_recipients')
    op.drop_table('monitoring_defaults')
    op.drop_index(op.f('ix_integration_outbox_created_at'), table_name='integration_outbox')
    op.drop_table('integration_outbox')
    op.drop_index(op.f('ix_drivers_status'), table_name='drivers')
    op.drop_table('drivers')
    op.drop_table('clients')
    op.drop_index(op.f('ix_audit_log_occurred_at'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_entity_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_action'), table_name='audit_log')
    op.drop_table('audit_log')
    # ### fin de los comandos de Alembic ###
