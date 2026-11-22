"""Configuración central del backend.

Todo valor ajustable sale de variables de entorno (o del .env en desarrollo).
Los secretos van como SecretStr para que nunca aparezcan en logs ni en repr.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "CarGO API"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = False

    # --- persistencia
    database_url: str = "postgresql+asyncpg://cargo:cargo@localhost:5432/cargo"
    database_echo: bool = False
    database_pool_size: int = 10

    # --- autenticación
    jwt_secret: SecretStr = SecretStr("development-only-secret-change-me-0123456789")
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "cargo-api"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=3600)
    cookie_secure: bool = False
    login_max_failed_attempts: int = Field(default=5, ge=1)
    login_lockout_seconds: int = Field(default=900, ge=30)
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- broker MQTT IoT (frontera externa)
    mqtt_iot_host: str = "localhost"
    mqtt_iot_port: int = 1883
    mqtt_iot_username: str | None = None
    mqtt_iot_password: SecretStr | None = None
    mqtt_iot_tls: bool = False
    mqtt_iot_ca_file: str | None = None

    # --- broker MQTT interno (red privada)
    mqtt_internal_host: str = "localhost"
    mqtt_internal_port: int = 1884
    mqtt_internal_username: str | None = None
    mqtt_internal_password: SecretStr | None = None

    # --- proveedores externos
    mapbox_token: SecretStr | None = None
    mapbox_api_base: str = "https://api.mapbox.com"
    # CarGO no planifica rutas (un viaje es origen + destino); los mapas solo se usan
    # para buscar direcciones al crear el viaje.
    # Búsqueda de direcciones: mapbox (con token) | photon (datos de OpenStreetMap).
    geocoding_provider: Literal["mapbox", "photon"] = "mapbox"
    photon_base_url: str = "https://photon.komoot.io"
    # Los resultados cerca de este punto salen primero (por defecto, Lima).
    geocoding_bias_latitude: float | None = -12.0464
    geocoding_bias_longitude: float | None = -77.0428
    external_user_agent: str = "CarGO/2.0"
    telegram_bot_token: SecretStr | None = None
    telegram_api_base: str = "https://api.telegram.org"
    http_timeout_seconds: float = 8.0

    # --- políticas de monitoreo
    live_tolerance_seconds: int = Field(default=60, ge=1)
    max_future_skew_seconds: int = Field(default=120, ge=0)
    device_online_window_seconds: int = Field(default=180, ge=10)
    trip_reannounce_interval_seconds: int = Field(default=60, ge=5)
    notification_max_attempts: int = Field(default=3, ge=1, le=10)
    notification_retry_base_seconds: float = Field(default=2.0, ge=0)
    # Hora local que ve la gente en las notificaciones (en BD todo se guarda en UTC).
    display_timezone: str = "America/Lima"

    # --- workers de la API (relay del outbox, puente de tiempo real, reanuncio de viajes).
    # Se apagan en los tests de API que corren sin brokers.
    run_background_workers: bool = True

    # --- runtime CEP (solo para el health check; las reglas viven en Siddhi)
    siddhi_host: str = "localhost"
    siddhi_port: int = 9090

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _reject_insecure_production(self) -> Settings:
        if self.environment == "production":
            secret = self.jwt_secret.get_secret_value()
            if len(secret) < 32 or secret.startswith("development-only"):
                raise ValueError("JWT_SECRET must be a strong (>=32 chars) secret in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (HTTPS only)")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
