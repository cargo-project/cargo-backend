#!/bin/sh
set -eu
: "${MQTT_INTERNAL_PASSWORD:?MQTT_INTERNAL_PASSWORD is required}"
: > /mosquitto/config/passwords
mosquitto_passwd -b /mosquitto/config/passwords cargo-internal "$MQTT_INTERNAL_PASSWORD"
chmod 0700 /mosquitto/config/passwords
chown mosquitto:mosquitto /mosquitto/config/passwords
chown -R mosquitto:mosquitto /mosquitto/data
exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
