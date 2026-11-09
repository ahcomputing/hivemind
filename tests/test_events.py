from datetime import UTC, datetime

import pytest

from hivemind.events import monday_hackathon_events, sessionize_events


def test_sessionize_importer_uses_mountain_for_offset_free_times():
    payload = {
        "speakers": [{"id": "sp", "fullName": "Ada Lovelace"}],
        "rooms": [{"id": 7, "name": "Room Seven"}],
        "sessions": [{"id": "123", "title": "A session", "description": "Public text", "speakers": ["sp"], "roomId": 7, "startsAt": "2026-11-10T09:00:00", "endsAt": "2026-11-10T10:00:00"}],
    }
    events, counts = sessionize_events(payload, datetime(2026, 11, 1, tzinfo=UTC))
    assert counts == {"received": 1, "accepted": 1, "rejected": 0}
    assert events[0]["starts_at"] == datetime(2026, 11, 10, 16, tzinfo=UTC)
    assert events[0]["speaker_names"] == ["Ada Lovelace"]


def test_sessionize_rejects_unusable_times_and_hackathon_has_no_lunch():
    with pytest.raises(ValueError):
        sessionize_events({"sessions": [{"id": "bad", "title": "No time"}]}, datetime.now(UTC))
    assert all("lunch" not in event["title"].lower() for event in monday_hackathon_events())
