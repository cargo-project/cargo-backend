# CarGO v2 · Backend

CarGO automatiza el **monitoreo en tiempo real de vehículos de carga pesada**. En lugar de que una persona observe un mapa todo el tiempo (supervisión continua), el sistema analiza la telemetría del vehículo y solo pide intervención humana cuando detecta una situación relevante (**supervisión por excepción**).

Un dispositivo Edge (Raspberry Pi 3 B+ con GNSS u-blox NEO-M8N y botón de emergencia) publica telemetría por MQTT/TLS. La plataforma la valida, deduplica, clasifica (LIVE/DELAYED), enriquece con PostGIS y la evalúa con **Siddhi CEP**. Las situaciones detectadas (`MonitoringEvent`) se persisten, se envían a la web por WebSocket y se notifican por Telegram.

> Este repositorio es el **backend**. El frontend (Next.js) está en el repositorio [`cargo-front`](https://github.com/cargo-project/cargo-front).

## Arquitectura

**Arquitectura distribuida orientada a eventos + backend monolito modular + Clean Architecture + DDD ligero.**

```
Raspberry Pi ─MQTT/TLS QoS1─▶ Broker IoT ─▶ Ingesta ──telemetry/normalized──▶ Broker interno
                 (telemetry/raw/{device})     (valida · deduplica · LIVE/DELAYED · persiste)
Broker interno ─▶ Geoespacial (PostGIS) ──telemetry/enriched──▶ Siddhi CEP ──events/detected──▶
     ├─▶ API FastAPI: registra el MonitoringEvent · WebSocket · cierre por llegada
     └─▶ Notificaciones: registra (idempotente) · Telegram con reintentos
API ──trip/started · trip/config-updated · trip/ended──▶ Broker interno ──▶ Siddhi CEP
Next.js ◀─REST /api/v1 (cookies + CSRF)─▶ FastAPI ──WebSocket /api/v1/ws──▶ Next.js
```

| Proceso | Código |
|---|---|
| API (REST + WebSocket + relay del outbox + puente de tiempo real) | `app/main.py` |
| Servicio de Ingesta | `app/entrypoints/ingestion_service.py` |
| Servicio Geoespacial | `app/entrypoints/geospatial_service.py` |
| Servicio de Notificaciones | `app/entrypoints/notification_service.py` |
| Motor CEP (Siddhi 5.1.2) | `cep/siddhi/CargoMonitoring.siddhi` |

Módulos de dominio (`app/modules/`): `identity`, `fleet`, `trips`, `monitoring`, `notifications`, `configuration`. Cada uno tiene las capas `domain → application → infrastructure / presentation`.

## Requisitos

* Docker Desktop / Docker Engine 24+ con Compose v2.
* Python 3.13+ (desarrollado y probado con 3.14) para ejecutar fuera de Docker y para los tests.
* Opcional: token de Mapbox (`MAPBOX_TOKEN`) y bot de Telegram (`TELEGRAM_BOT_TOKEN`).

## Variables de entorno

Copia `.env.example` a `.env` y cambia **todos** los secretos. `.env` está en `.gitignore`.

| Variable | Uso |
|---|---|
| `DATABASE_URL` | PostgreSQL+asyncpg (en Docker la compone `docker-compose.yml`) |
| `POSTGRES_USER/PASSWORD/DB` | credenciales del contenedor PostGIS |
| `JWT_SECRET` | firma de tokens de acceso (≥32 caracteres; se valida en producción) |
| `COOKIE_SECURE` | `true` en producción (solo HTTPS) |
| `CORS_ORIGINS` | orígenes permitidos (REST y WebSocket), separados por comas |
| `MQTT_IOT_*` | broker IoT (cuenta de ingesta, TLS) |
| `MQTT_IOT_DEVICE_ACCOUNTS` | `CÓDIGO:clave,...`: credenciales de cada dispositivo (usuario MQTT = código) |
| `MQTT_INTERNAL_*` | broker interno privado |
| `GEOCODING_PROVIDER` | búsqueda de direcciones al crear el viaje: `photon` (OpenStreetMap, por defecto) o `mapbox`. CarGO **no planifica rutas**: un viaje es origen + destino |
| `PHOTON_BASE_URL` | servidor OSM para la búsqueda de direcciones (público para desarrollo) |
| `TELEGRAM_BOT_TOKEN` | canal de notificaciones; vacío = notificaciones registradas como `skipped` |
| `LIVE_TOLERANCE_SECONDS` | retraso máximo para considerar una medición LIVE (por defecto 60 s) |
| `SEED_*` | usuarios de desarrollo creados por `scripts/seed_dev_data.py` |

## Levantar con Docker

```powershell
Copy-Item .env.example .env                       # y sustituye todos los change-me-…
docker compose --profile frontend build
docker compose --profile frontend up -d           # postgres, migrate, brokers, api, ingestion, geospatial,
                                                  # notifications, cep, nginx y el frontend (http://localhost)
docker compose run --rm api python -m scripts.seed_dev_data
.\.venv\Scripts\python.exe scripts\demo_trip.py --connection-loss 30   # viaje de demostración (requiere el venv)
```

* API: `http://localhost:8000/api/v1` (desarrollo) o `http://localhost/api/v1` (Nginx).
* OpenAPI: `http://localhost:8000/api/v1/docs`.
* Salud: `GET /health/live`, `GET /health/ready` (comprueba la base de datos y el broker interno de verdad).
* Broker IoT para dispositivos: `mqtts://<host>:8883`. El CA de desarrollo se genera en el volumen `mqtt-iot-certs`.

Perfil opcional:

```bash
docker compose --profile frontend up -d         # sirve el frontend Next.js detrás de Nginx (http://localhost)
```

El perfil `frontend` construye el frontend desde `FRONTEND_PATH` (por defecto `../cargo-front`).

Producción (sin puertos de depuración): `docker compose -f docker-compose.yml up -d`.

## Ejecutar sin Docker (desarrollo)

```bash
python -m venv .venv && .venv/Scripts/activate        # Windows (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
python -m app.entrypoints.ingestion_service           # en otra terminal (y geospatial / notification)
```

## Migraciones

Se usa **Alembic** (la herramienta oficial de migraciones de SQLAlchemy, compatible con async y GeoAlchemy2). El esquema nunca se crea con `create_all` al arrancar.

```bash
alembic upgrade head                                 # aplicar
alembic revision --autogenerate -m "descripcion"     # nueva migración (revísala siempre)
alembic check                                        # verifica que los modelos y las migraciones coincidan
```

En Docker, el servicio `migrate` ejecuta `alembic upgrade head` antes de que arranquen los demás procesos.

## Tests y calidad

```bash
ruff check . && ruff format --check .     # lint + formato
mypy                                       # tipado estricto
pytest tests/unit                          # dominio, casos de uso, reglas de arquitectura, adapters
pytest tests/integration tests/api         # requieren PostGIS (y Mosquitto para MQTT)
pytest tests/cep                           # requiere el contenedor Siddhi (ver scripts/run_test_infra.ps1)
pytest --cov=app --cov-report=term-missing
```

`scripts/run_test_infra.ps1` levanta PostGIS (`127.0.0.1:55432`), Mosquitto (`51883`) y Siddhi con su broker (`51884`) para la suite completa. `TEST_DATABASE_URL`, `TEST_MQTT_*` y `TEST_CEP_MQTT_*` permiten apuntar a otra infraestructura.

## Conexión con el frontend

El frontend ya consume esta API:

```
# cargo-front/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws
```

* Respuestas `{ "data": … }`, errores `{ "error": { code, message, details, requestId } }`.
* Sesión por cookies `HttpOnly` (`cargo_access`, `cargo_refresh`) y cookie legible `cargo_csrf`, que el cliente devuelve en `X-CSRF-Token`.
* `CORS_ORIGINS` debe incluir el origen del frontend (por ejemplo `http://localhost:3000`).
* El WebSocket emite `position.updated`, `monitoring.event_created`, `trip.status_changed`, `trip.config_updated` y `device.connection_changed`.

## Seguridad

Argon2id, JWT de vida corta en cookie `HttpOnly`, refresh rotativo con detección de reutilización, CSRF *double submit*, bloqueo por intentos fallidos, autorización por roles, validación estricta de entradas (HTTP y MQTT), MQTT/TLS con ACL por dispositivo, broker interno y PostgreSQL en redes Docker `internal`, secretos solo por entorno.
