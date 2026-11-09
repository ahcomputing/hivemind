import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from hivemind.config import Settings
from hivemind.main import create_app
from hivemind.repository import as_datetime
from hivemind.summaries import OpenAISummarizer, OpportunitySummary, SummaryBullet, evidence_payload
from tests.conftest import FakeRepository


class RecordingSummarizer:
    def __init__(self, _settings, source_ids=None):
        self.calls = 0
        self.source_ids = source_ids
        self.interests = []

    async def close(self):
        return None

    async def generate(self, official, reports, interests=None):
        self.calls += 1
        self.interests.append(interests)
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


def test_ideal_talk_recommendations_are_cited_and_cached_per_interest_profile():
    summarizer = RecordingSummarizer(enabled_settings())
    with make_client(summarizer) as client:
        repository = client.app.state.repository
        repository.official_events = [official_event()]
        repository.reports["crowd"] = {
            "content": "Seats are filling up fast.", "location": "Room 1", "category": "general",
            "starts_at": datetime.now(UTC), "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "created_at": datetime.now(UTC), "status": "active", "session_id": "private", "avatar_seed": "private",
        }
        csrf = bootstrap(client)
        request = {"window_minutes": 30, "interests": "Kubernetes security and observability"}
        first = client.post("/api/opportunities/summary", json=request, headers={"X-CSRF-Token": csrf})
        assert first.status_code == 200
        assert first.json()["recommendation_mode"] is True
        assert first.json()["generation_status"] == "generated"
        assert summarizer.interests == ["Kubernetes security and observability"]
        second = client.post("/api/opportunities/summary", json=request, headers={"X-CSRF-Token": csrf})
        assert second.json()["generation_status"] == "cached"
        different = client.post(
            "/api/opportunities/summary",
            json={"window_minutes": 30, "interests": "cloud native networking"},
            headers={"X-CSRF-Token": csrf},
        )
        assert different.json()["generation_status"] == "generated"
        assert summarizer.interests == ["Kubernetes security and observability", "cloud native networking"]


def test_ideal_talk_recommendations_reject_report_only_citations():
    summarizer = RecordingSummarizer(enabled_settings(), ["report:crowd"])
    with make_client(summarizer) as client:
        repository = client.app.state.repository
        repository.official_events = [official_event()]
        repository.reports["crowd"] = {
            "content": "Seats are filling up fast.", "location": "Room 1", "category": "general",
            "starts_at": datetime.now(UTC), "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "created_at": datetime.now(UTC), "status": "active", "session_id": "private", "avatar_seed": "private",
        }
        csrf = bootstrap(client)
        response = client.post(
            "/api/opportunities/summary",
            json={"window_minutes": 30, "interests": "Kubernetes"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert response.json()["generation_status"] == "unavailable"
        assert response.json()["summary"] is None


def test_ideal_talk_interests_cannot_be_blank_and_home_has_a_progressive_form(client):
    csrf = bootstrap(client)
    response = client.post(
        "/api/opportunities/summary", json={"interests": "   "}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 422
    page = client.get("/").text
    assert 'id="find-ideal-talk"' in page
    assert 'id="ideal-talk-form"' in page
    assert 'id="interests"' in page


def test_bounded_recommendation_evidence_keeps_json_and_only_admits_sent_sources():
    events = [
        {**official_event(), "id": f"sessionize:{number}", "description": "x" * 900}
        for number in range(80)
    ]
    payload, eligible = evidence_payload(events, [], "Kubernetes security")
    rendered = payload["evidence"]
    assert len(rendered) <= 36_000
    assert "Kubernetes security" in rendered
    assert {row["id"] for row in json.loads(rendered)["evidence"]} == eligible


def test_budget_months_are_isolated():
    repository = FakeRepository(enabled_settings())
    assert asyncio.run(repository.reserve_openai_budget("2026-11", 100, 100, datetime.now(UTC)))
    assert not asyncio.run(repository.reserve_openai_budget("2026-11", 1, 100, datetime.now(UTC)))
    assert asyncio.run(repository.reserve_openai_budget("2026-12", 100, 100, datetime.now(UTC)))


def test_elasticsearch_iso_dates_are_normalized_before_cache_comparisons():
    assert as_datetime("2026-11-09T12:00:00Z") == datetime(2026, 11, 9, 12, tzinfo=UTC)


def test_openai_request_has_strict_schema_and_excludes_private_report_fields():
    class Response:
        status = "completed"
        output_text = '{"bullets":[{"text":"Official session soon.","source_ids":["official:sessionize:123"]}]}'

        class usage:
            input_tokens = 100
            output_tokens = 20

    class Responses:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return Response()

    class Client:
        def __init__(self):
            self.responses = Responses()

        async def close(self):
            return None

    summarizer = OpenAISummarizer(enabled_settings())
    fake_client = Client()
    summarizer.client = fake_client
    report = {
        "id": "report-1", "content": "Meet by the fountain", "location": "Atrium",
        "starts_at": datetime.now(UTC), "expires_at": datetime.now(UTC) + timedelta(hours=1),
        "created_at": datetime.now(UTC), "session_id": "private-session", "avatar_seed": "private-avatar",
    }
    summary, actual = asyncio.run(summarizer.generate([official_event()], [report], "Kubernetes security"))
    request = fake_client.responses.kwargs
    assert request["model"] == "gpt-6-luna"
    assert request["store"] is False
    assert request["text"]["format"]["strict"] is True
    assert "private-session" not in request["input"]
    assert "private-avatar" not in request["input"]
    assert "Kubernetes security" in request["input"]
    assert "Every recommendation must cite at least one" in request["instructions"]
    assert summary.bullets[0].source_ids == ["official:sessionize:123"]
    assert actual == 20
