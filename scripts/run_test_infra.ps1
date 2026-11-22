# Levanta la infraestructura descartable que usan los tests de integracion, API y CEP.
#   PostGIS    -> 127.0.0.1:55432 (valor por defecto de TEST_DATABASE_URL)
#   Mosquitto  -> 127.0.0.1:51883 (valor por defecto de TEST_MQTT_PORT)
#   Siddhi CEP -> broker en 127.0.0.1:51884 (valor por defecto de TEST_CEP_MQTT_PORT)
# "Continue": docker escribe el progreso en stderr y PowerShell 5.1 lo tomaria como error que corta el script.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

docker rm -f cargo-v2-devdb cargo-v2-testmqtt cargo-v2-cep-mqtt cargo-v2-cep-siddhi 2>$null | Out-Null
docker network create cargo-v2-cep-test 2>$null | Out-Null

docker run -d --name cargo-v2-devdb -e POSTGRES_USER=cargo -e POSTGRES_PASSWORD=cargo -e POSTGRES_DB=cargo `
  -p 127.0.0.1:55432:5432 postgis/postgis:17-3.5 | Out-Null
docker run -d --name cargo-v2-testmqtt -p 127.0.0.1:51883:1883 eclipse-mosquitto:2.0.22 `
  sh -c "printf 'listener 1883\nallow_anonymous true\n' > /tmp/m.conf && exec mosquitto -c /tmp/m.conf" | Out-Null
docker run -d --name cargo-v2-cep-mqtt --network cargo-v2-cep-test -p 127.0.0.1:51884:1883 eclipse-mosquitto:2.0.22 `
  sh -c "printf 'listener 1883\nallow_anonymous true\n' > /tmp/m.conf && exec mosquitto -c /tmp/m.conf" | Out-Null
# El CEP de pruebas se construye con las estadisticas nativas de Siddhi activadas (banco de pruebas);
# las reglas son exactamente las mismas que en produccion.
docker build -q --build-arg CEP_STATISTICS=true -t cargo-v2-cep:test "$root\cep" | Out-Null
docker run -d --name cargo-v2-cep-siddhi --network cargo-v2-cep-test -e MQTT_URL=tcp://cargo-v2-cep-mqtt:1883 `
  -e MQTT_USERNAME= -e MQTT_PASSWORD= cargo-v2-cep:test | Out-Null

Write-Host "Waiting for PostGIS and Siddhi..."
for ($i = 0; $i -lt 60; $i++) {
  Start-Sleep -Seconds 3
  $db = docker exec cargo-v2-devdb pg_isready -h 127.0.0.1 -U cargo 2>$null
  $cep = docker logs cargo-v2-cep-siddhi 2>&1 | Select-String "deployed successfully"
  if ($LASTEXITCODE -eq 0 -and $cep) { break }
}
Write-Host "Test infrastructure ready. Run: pytest"
