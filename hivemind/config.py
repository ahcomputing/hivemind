from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_secret: str = "development-only-change-me-please-32chars"
    cookie_secure: bool = False
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index_prefix: str = "hivemind"
    admin_username: str | None = None
    admin_password: str | None = None
    openai_api_key: str | None = None
    openai_monthly_cap_usd: int = 0
    evolution_enabled: bool = False
    evolution_schedule: str | None = None
    report_rate_limit_count: int = 5
    report_rate_limit_seconds: int = 60
    # Avatars are rendered by HiveMind's own RoboHash instance (k8s/robohash/),
    # so the browser makes no third-party request. Point this at robohash.org
    # to fall back to the public service; the privacy notice must then regain
    # its third-party caveat.
    avatar_base_url: str = "https://robohash.ahcomputing.com"

    @model_validator(mode="after")
    def validate_runtime_settings(self) -> "Settings":
        placeholders = ("CHANGE_ME", "PLACEHOLDER", "replace-me")
        protected = (self.app_secret, self.elasticsearch_password, self.admin_password)
        if any(value and any(token in value for token in placeholders) for value in protected):
            raise ValueError("replace configuration placeholders before starting HiveMind")
        if len(self.app_secret) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if not all((self.elasticsearch_username, self.elasticsearch_password)):
                raise ValueError("production requires Elasticsearch authentication")
            if not all((self.admin_username, self.admin_password)):
                raise ValueError("production requires admin authentication configuration")
        if self.evolution_enabled:
            raise ValueError("evolution is intentionally disabled in this increment")
        return self

    @property
    def sessions_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_sessions"

    @property
    def reports_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_reports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
