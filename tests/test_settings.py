import pytest
from pydantic import ValidationError

from hivemind.config import Settings


def test_production_rejects_insecure_or_missing_configuration():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", app_secret="x" * 40)


def test_evolution_cannot_be_enabled():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_secret="x" * 40, evolution_enabled=True)
