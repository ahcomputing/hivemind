from decimal import Decimal
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
    # Generation remains opt-in.  A model and its current prices must be set
    # together before this becomes true; a key alone must never spend money.
    openai_summary_enabled: bool = False
    openai_summary_model: str | None = None
    openai_input_usd_per_million_tokens: Decimal | None = None
    openai_output_usd_per_million_tokens: Decimal | None = None
    openai_monthly_cap_usd: Decimal = Decimal("50")
    openai_summary_max_input_tokens: int = 12_000
    openai_summary_max_output_tokens: int = 600
    openai_summary_timeout_seconds: int = 30
    summary_rate_limit_count: int = 3
    summary_rate_limit_seconds: int = 60
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
        if self.openai_summary_enabled:
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when summaries are enabled")
            if not self.openai_summary_model:
                raise ValueError("OPENAI_SUMMARY_MODEL must be explicitly configured")
            if not all(
                value is not None and value > 0
                for value in (
                    self.openai_input_usd_per_million_tokens,
                    self.openai_output_usd_per_million_tokens,
                )
            ):
                raise ValueError("verified OpenAI input/output pricing is required")
            if self.openai_monthly_cap_usd != Decimal("50"):
                raise ValueError("HiveMind's OpenAI monthly cap must be exactly 50 USD")
            if self.openai_summary_timeout_seconds != 30:
                raise ValueError("OpenAI summary requests must time out after 30 seconds")
            if self.openai_summary_max_input_tokens <= 0 or self.openai_summary_max_output_tokens <= 0:
                raise ValueError("OpenAI summary token limits must be positive")
        return self

    @property
    def sessions_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_sessions"

    @property
    def reports_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_reports"

    @property
    def official_events_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_official_events"

    @property
    def event_state_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_event_state"

    @property
    def opportunity_cache_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_opportunity_cache"

    @property
    def usage_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_usage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
