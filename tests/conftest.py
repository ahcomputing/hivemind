from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from hivemind.config import Settings
from hivemind.main import create_app


class FakeRepository:
    def __init__(self, _settings):
        self.sessions = {}
        self.reports = {}
        self.available = True
        self.official_events = []
        self.event_freshness = None
        self.opportunity_cache = {}
        self.usage = {}

    async def close(self):
        return None

    async def initialize(self):
        return None

    async def ready(self):
        return self.available

    async def create_session(self, session_id, document):
        self.sessions[session_id] = document

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def update_session(self, session_id, document):
        self.sessions[session_id] = document

    async def create_report(self, report_id, document):
        self.reports[report_id] = document

    async def consume_report_slot(self, session_id, window, limit):
        session = self.sessions[session_id]
        if session.get("rate_window") != window:
            session["rate_window"] = window
            session["rate_count"] = 1
            return True
        if session["rate_count"] >= limit:
            return False
        session["rate_count"] += 1
        return True

    async def consume_summary_slot(self, session_id, window, limit):
        session = self.sessions[session_id]
        if session.get("summary_rate_window") != window:
            session["summary_rate_window"] = window
            session["summary_rate_count"] = 1
            return True
        if session["summary_rate_count"] >= limit:
            return False
        session["summary_rate_count"] += 1
        return True

    async def list_active_reports(self, category=None):
        now = datetime.now(UTC)
        return [
            {"id": report_id, **report}
            for report_id, report in sorted(
                self.reports.items(), key=lambda item: item[1]["created_at"], reverse=True
            )
            if report["status"] == "active"
            and report["expires_at"] > now
            and (not category or category == "all" or report["category"] == category)
        ]

    async def list_official_events_overlapping(self, window_start, window_end, limit=40):
        rows = [
            row for row in self.official_events
            if row["starts_at"] < window_end and row["ends_at"] > window_start
        ][:limit]
        return rows, self.event_freshness

    async def list_reports_for_opportunities(self, window_end, limit=40):
        now = datetime.now(UTC)
        return [
            {"id": report_id, **row}
            for report_id, row in self.reports.items()
            if row["status"] == "active"
            and row["expires_at"] > now
            and row.get("starts_at", row["created_at"]) < window_end
        ][:limit]

    async def get_opportunity_cache(self, cache_id, now):
        row = self.opportunity_cache.get(cache_id)
        if not row or row["state"] != "complete" or row["expires_at"] <= now:
            return None
        return row

    async def claim_opportunity_generation(self, cache_id, evidence_hash, window_minutes, now, lock_expires_at):
        existing = self.opportunity_cache.get(cache_id)
        if existing and existing.get("lock_expires_at", now) > now:
            return False
        self.opportunity_cache[cache_id] = {
            "state": "generating", "evidence_hash": evidence_hash, "window_minutes": window_minutes,
            "created_at": now, "expires_at": lock_expires_at, "lock_expires_at": lock_expires_at,
        }
        return True

    async def complete_opportunity_generation(self, cache_id, evidence_hash, window_minutes, summary, now):
        self.opportunity_cache[cache_id] = {
            "state": "complete", "evidence_hash": evidence_hash, "window_minutes": window_minutes,
            "created_at": now, "expires_at": now + timedelta(seconds=60), "lock_expires_at": now, "summary": summary,
        }

    async def abandon_opportunity_generation(self, cache_id):
        self.opportunity_cache.pop(cache_id, None)

    async def reserve_openai_budget(self, month, reservation_microusd, cap_microusd, now):
        row = self.usage.setdefault(month, {"reserved": 0, "actual": 0})
        if row["reserved"] + row["actual"] + reservation_microusd > cap_microusd:
            return False
        row["reserved"] += reservation_microusd
        return True

    async def settle_openai_budget(self, month, reservation_microusd, actual_microusd, now):
        row = self.usage[month]
        row["reserved"] = max(0, row["reserved"] - reservation_microusd)
        row["actual"] += actual_microusd


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_secret="unit-test-secret-that-is-long-enough-000",
        elasticsearch_url="http://example.invalid",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, FakeRepository)) as test_client:
        yield test_client
