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

    async def report_count_since(self, session_id, after):
        return sum(
            1
            for report in self.reports.values()
            if report["session_id"] == session_id and report["created_at"] >= after
        )

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
