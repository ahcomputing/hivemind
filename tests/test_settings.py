from decimal import Decimal

import pytest
from pydantic import ValidationError

from hivemind.config import Settings


def test_production_rejects_insecure_or_missing_configuration():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", app_secret="x" * 40)


def test_evolution_cannot_be_enabled():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret="x" * 40, evolution_enabled=True)
def test_enabled_luna_requires_complete_verified_paid_configuration():
    common = {
        "_env_file": None,
        "app_secret": "x" * 40,
        "openai_summary_enabled": True,
        "openai_api_key": "test-key-not-a-real-secret",
        "openai_summary_model": "gpt-6-luna",
        "openai_input_usd_per_million_tokens": Decimal("0.10"),
        "openai_output_usd_per_million_tokens": Decimal("0.50"),
    }
    assert Settings(**common).openai_summary_model == "gpt-6-luna"
    with pytest.raises(ValueError, match="exactly 50"):
        Settings(**(common | {"openai_monthly_cap_usd": Decimal("51")}))
