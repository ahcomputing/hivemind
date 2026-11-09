import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from hivemind.config import Settings
from hivemind.main import create_app
from hivemind.summaries import OpportunitySummary, SummaryBullet
from tests.conftest import FakeRepository


class RecordingSummarizer:
    def __init__(self, _settings, source_ids=None):
        self.calls = 0
        self.source_ids = source_ids

    async def close(self):
        return None

    async def generate(self, official, reports):
        self.calls += 1
        source_ids = self.source_ids or [f"official:{official[0]['id']}"]
        return OpportunitySummary(bullets=[SummaryBullet(text="A concise, cited opportunity.", source_ids=source_ids)]), 125


def enabled_settings():
    return Settings(
        _env_file=None,
        app_secret="unit-test-secret-that-is-long-enough-000",
        elasticsearch_url="http://example.invalid",
        openai_summary_enabled=True,
        openai_api_key="test-key-not-a-real-secret",
        openai_summary_model="gpt-6-luna",
        openai_input_usd_per_million_tokens=Decimal("0.10"),
        openai_output_usd_per_million_tokens=Decimal("0.50"),
    )


def make_client(summarizer):
    def factory(_settings):
        return summarizer

    return TestClient(create_app(enabled_settings(), FakeRepository, factory))


def bootstrap(client):
    return client.post("/api/session/bootstrap").json()["csrf_token"]


def official_event():
    now = datetime.now(UTC)
    return {
        "id": "sessionize:123", "title": "Official session", "description": "Public agenda", "speaker_names": ["Ada"],
        "location": "Room 1", "starts_at": now + timedelta(minutes=5), "ends_at": now + timedelta(minutes=45),
        "source_url": "https://example.test/schedule",
    }


def test_summary_reserves_then_caches_and_cites_only_evidence():
    summarizer = RecordingSummarizer(enabled_settings())
    with make_client(summarizer) as client:
        client.app.state.repository.official_events = [official_event()]
        csrf = bootstrap(client)
        response = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert response.json()["generation_status"] == "generated"
        assert response.json()["summary"]["bullets"][0]["source_ids"] == ["official:sessionize:123"]
        second = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert second.json()["generation_status"] == "cached"
        assert summarizer.calls == 1
        month = datetime.now(UTC).strftime("%Y-%m")
        assert client.app.state.repository.usage[month]["reserved"] == 0
        assert client.app.state.repository.usage[month]["actual"] == 125


def test_invalid_citations_are_never_published():
    summarizer = RecordingSummarizer(enabled_settings(), ["official:not-retrieved"])
    with make_client(summarizer) as client:
        client.app.state.repository.official_events = [official_event()]
        csrf = bootstrap(client)
        response = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert response.json()["generation_status"] == "unavailable"
        assert "not-retrieved" not in response.text


def test_budget_exhaustion_fails_before_call():
    summarizer = RecordingSummarizer(enabled_settings())
    with make_client(summarizer) as client:
        repository = client.app.state.repository
        repository.official_events = [official_event()]
        month = datetime.now(UTC).strftime("%Y-%m")
        repository.usage[month] = {"reserved": 50_000_000, "actual": 0}
        csrf = bootstrap(client)
        response = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert response.status_code == 200
        assert response.json()["generation_status"] == "budget_exhausted"
        assert summarizer.calls == 0


def test_changed_evidence_invalidates_cross_replica_cache():
    summarizer = RecordingSummarizer(enabled_settings())
    with make_client(summarizer) as client:
        repository = client.app.state.repository
        repository.official_events = [official_event()]
        csrf = bootstrap(client)
        first = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert first.json()["generation_status"] == "generated"
        repository.official_events[0]["title"] = "Changed official session"
        second = client.post("/api/opportunities/summary", json={"window_minutes": 30}, headers={"X-CSRF-Token": csrf})
        assert second.json()["generation_status"] == "generated"
        assert summarizer.calls == 2


def test_budget_months_are_isolated():
    repository = FakeRepository(enabled_settings())
    assert asyncio.run(repository.reserve_openai_budget("2026-11", 100, 100, datetime.now(UTC)))
    assert not asyncio.run(repository.reserve_openai_budget("2026-11", 1, 100, datetime.now(UTC)))
    assert asyncio.run(repository.reserve_openai_budget("2026-12", 100, 100, datetime.now(UTC)))
