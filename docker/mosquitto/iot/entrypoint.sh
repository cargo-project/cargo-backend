#!/bin/sh
# Arma el archivo de contraseñas con las variables de entorno (los secretos nunca van en la imagen) y,
# solo para desarrollo, crea una CA autofirmada + certificado del server si no hay uno montado.
set -eu

CONFIG=/mosquitto/config
CERTS=/mosquitto/certs
mkdir -p "$CERTS"

: "${MQTT_IOT_INGESTION_PASSWORD:?MQTT_IOT_INGESTION_PASSWORD is required}"
: > "$CONFIG/passwords"
mosquitto_passwd -b "$CONFIG/passwords" cargo-ingestion "$MQTT_IOT_INGESTION_PASSWORD"

# MQTT_IOT_DEVICE_ACCOUNTS="DEV-GW-001:secret1,DEV-GW-002:secret2"
OLD_IFS=$IFS; IFS=','
for account in ${MQTT_IOT_DEVICE_ACCOUNTS:-}; do
  user=${account%%:*}; pass=${account#*:}
  [ -n "$user" ] && [ "$user" != "$pass" ] && mosquitto_passwd -b "$CONFIG/passwords" "$user" "$pass"
done
IFS=$OLD_IFS
chmod 0700 "$CONFIG/passwords"
chown mosquitto:mosquitto "$CONFIG/passwords"

if [ ! -f "$CERTS/server.crt" ]; then
  echo "[cargo] no TLS certificate mounted: generating a DEVELOPMENT CA and server certificate"
  # Las extensiones hacen falta para la verificación X.509 estricta (ej. contextos por defecto de Python >= 3.13).
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=CarGO Dev CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -addext "subjectKeyIdentifier=hash" \
    -keyout "$CERTS/ca.key" -out "$CERTS/ca.crt" 2>/dev/null
  openssl req -newkey rsa:2048 -nodes -subj "/CN=${MQTT_IOT_TLS_HOSTNAME:-mqtt-iot}" \
    -keyout "$CERTS/server.key" -out "$CERTS/server.csr" 2>/dev/null
  {
    echo "basicConstraints=CA:FALSE"
    echo "keyUsage=critical,digitalSignature,keyEncipherment"
    echo "extendedKeyUsage=serverAuth"
    echo "authorityKeyIdentifier=keyid"
    printf "subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1\n" "${MQTT_IOT_TLS_HOSTNAME:-mqtt-iot}"
  } > "$CERTS/san.ext"
  openssl x509 -req -in "$CERTS/server.csr" -CA "$CERTS/ca.crt" -CAkey "$CERTS/ca.key" -CAcreateserial \
    -days 825 -extfile "$CERTS/san.ext" -out "$CERTS/server.crt" 2>/dev/null
  rm -f "$CERTS/server.csr" "$CERTS/san.ext"
fi
chown -R mosquitto:mosquitto "$CERTS" /mosquitto/data
chmod 0644 "$CERTS/ca.crt" "$CERTS/server.crt"

exec /usr/sbin/mosquitto -c "$CONFIG/mosquitto.conf"
