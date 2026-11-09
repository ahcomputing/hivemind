from datetime import UTC, datetime

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
