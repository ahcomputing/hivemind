from datetime import UTC, datetime, timedelta
from pathlib import Path

from hivemind.main import expiry_for
from hivemind.models import ReportInput


def bootstrap(client):
    response = client.post("/api/session/bootstrap")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def post_report(client, csrf, **overrides):
    payload = {
        "content": "Coffee line is short",
        "category": "coffee",
        "expiration": "1h",
    } | overrides
    return client.post("/api/reports", json=payload, headers={"X-CSRF-Token": csrf})


def test_create_and_list_shared_report(client):
    csrf = bootstrap(client)
    created = post_report(client, csrf)
    assert created.status_code == 201
    feed = client.get("/api/reports").json()["reports"]
    assert feed[0]["content"] == "Coffee line is short"
    assert "session_id" not in feed[0]


def test_home_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'class="hm-topbar"' in response.text
    assert "/static/ui/topbar.css" in response.text
    assert "/static/ui/topbar.js" in response.text
    assert "Opportunities nearby" in response.text
    assert "Summarize opportunities in the next 30 minutes" in response.text
    assert 'href="/share"' in response.text
    assert 'href="/reports"' in response.text


def test_opportunity_card_spans_the_report_grid_when_it_has_no_avatar(client):
    stylesheet = client.get("/static/app.css")
    assert stylesheet.status_code == 200
    assert ".report > :only-child { grid-column:1 / -1; min-width:0; }" in stylesheet.text


def test_validation_and_past_custom_expiration(client):
    csrf = bootstrap(client)
    assert post_report(client, csrf, content=" ").status_code == 422
    response = post_report(
        client,
        csrf,
        expiration="custom",
        custom_expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )
    assert response.status_code == 422


def test_extended_expiry_and_scheduled_start(client):
    csrf = bootstrap(client)
    start = datetime.now(UTC) + timedelta(minutes=20)
    created = post_report(client, csrf, expiration="90m", starts_at=start.isoformat())
    assert created.status_code == 201
    report = created.json()["report"]
    assert datetime.fromisoformat(report["expires_at"]) - datetime.fromisoformat(report["starts_at"]) == timedelta(minutes=90)
    bad = post_report(
        client,
        csrf,
        expiration="custom",
        starts_at=start.isoformat(),
        custom_expires_at=(start - timedelta(minutes=1)).isoformat(),
    )
    assert bad.status_code == 422
    assert post_report(
        client, csrf, expiration="15m", starts_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()
    ).status_code == 422
    assert post_report(
        client, csrf, starts_at=(datetime.now(UTC) + timedelta(days=8)).isoformat()
    ).status_code == 422


def test_relative_expirations_reject_past_scheduled_starts(client):
    csrf = bootstrap(client)
    start = datetime.now(UTC) - timedelta(days=1)
    for expiration in ("15m", "end_of_day"):
        response = post_report(client, csrf, expiration=expiration, starts_at=start.isoformat())
        assert response.status_code == 422


def test_custom_expiry_is_resolved_in_mountain_time_with_dst():
    now = datetime(2026, 6, 1, 12, tzinfo=UTC)
    result = expiry_for(
        ReportInput(content="test", expiration="custom", custom_expires_at="2026-06-01T12:00"),
        now,
    )
    assert result == datetime(2026, 6, 1, 18, tzinfo=UTC)


def test_cookie_ownership_and_csrf_rejection(client):
    csrf = bootstrap(client)
    assert post_report(client, "wrong-token").status_code == 403
    client.cookies.clear()
    assert post_report(client, csrf).status_code == 401


def test_rate_limit(client, settings):
    csrf = bootstrap(client)
    for number in range(settings.report_rate_limit_count):
        assert post_report(client, csrf, content=f"report {number}").status_code == 201
    assert post_report(client, csrf, content="one too many").status_code == 429


def test_expired_and_category_filtered_server_side(client):
    csrf = bootstrap(client)
    report = post_report(client, csrf).json()["report"]
    repository = client.app.state.repository
    repository.reports[report["id"]]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/reports").json()["reports"] == []
    assert post_report(client, csrf, content="need a charger", category="help").status_code == 201
    assert len(client.get("/api/reports?category=coffee").json()["reports"]) == 0
    assert len(client.get("/api/reports?category=help").json()["reports"]) == 1


def test_user_content_is_client_escaped(client):
    csrf = bootstrap(client)
    assert post_report(client, csrf, content="<img src=x onerror=alert(1)>").status_code == 201
    script = Path("hivemind/static/app.js").read_text()
    assert "escapeHtml(r.content)" in script


def test_readiness_reflects_database_availability(client):
    assert client.get("/healthz").status_code == 200
    client.app.state.repository.available = False
    assert client.get("/readyz").status_code == 503
    assert client.get("/api/reports").status_code == 503


def test_pages_and_source_first_opportunity_endpoint(client):
    for route in ("/", "/share", "/reports"):
        assert client.get(route).status_code == 200
    csrf = bootstrap(client)
    assert client.post("/api/opportunities/summary", json={"window_minutes": 30}).status_code == 403
    response = client.post(
        "/api/opportunities/summary",
        json={"window_minutes": 30},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generation_status"] == "unavailable"
    assert body["official_events"] == []
