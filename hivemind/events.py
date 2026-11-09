"""Validated, operator-triggered imports of official public schedules."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

MOUNTAIN = ZoneInfo("America/Denver")
SESSIONIZE_URL = "https://sessionize.com/api/v2/svi82w6c/view/All"


def _as_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOUNTAIN)
    return parsed.astimezone(UTC)


def sessionize_events(payload: dict[str, Any], fetched_at: datetime) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Extract usable public events without guessing any absent schedule data."""
    speakers = {
        str(item["id"]): item.get("fullName") or " ".join(
            part for part in (item.get("firstName"), item.get("lastName")) if part
        )
        for item in payload.get("speakers", [])
        if item.get("id") is not None
    }
    rooms = {str(item["id"]): item.get("name") for item in payload.get("rooms", [])}
    events: list[dict[str, Any]] = []
    rejected = 0
    for session in payload.get("sessions", []):
        start, end = _as_utc(session.get("startsAt")), _as_utc(session.get("endsAt"))
        session_id, title = session.get("id"), (session.get("title") or "").strip()
        if not session_id or not title or not start or not end or end <= start:
            rejected += 1
            continue
        events.append(
            {
                "source_id": f"sessionize:{session_id}",
                "title": title,
                "description": (session.get("description") or "").strip(),
                "speaker_names": [speakers[str(key)] for key in session.get("speakers", []) if speakers.get(str(key))],
                "location": rooms.get(str(session.get("roomId"))) or "Unspecified location",
                "starts_at": start,
                "ends_at": end,
                "source_url": SESSIONIZE_URL,
            }
        )
    if not events:
        raise ValueError("the Sessionize response had no usable timed sessions")
    return events, {"received": len(payload.get("sessions", [])), "accepted": len(events), "rejected": rejected}


def monday_hackathon_events() -> list[dict[str, Any]]:
    """Facts reviewed separately from Sessionize; conflicting lunch is excluded."""
    source = "https://www.wemakedevs.org/hackathons/cnh/schedule"
    day = "2026-11-09"
    # Only endpoints established by the reviewed baseline are represented.
    items = [
        ("check-in", "Cloud Native Hackathon check-in", "09:00", "10:00"),
        ("kickoff", "Cloud Native Hackathon kickoff and talks", "10:00", "11:00"),
        ("building", "Cloud Native Hackathon building begins", "11:00", "17:30"),
        ("submissions", "Cloud Native Hackathon submission deadline", "17:30", "17:31"),
        ("presentations", "Cloud Native Hackathon presentations", "17:30", "18:30"),
        ("winners", "Cloud Native Hackathon winners", "18:30", "19:00"),
    ]
    return [
        {
            "source_id": f"hackathon:{slug}", "title": title,
            "description": "Confirmed Cloud Native Hackathon timing.", "speaker_names": [],
            "location": "The Shop Workspace, 350 E 400 S, Salt Lake City, Utah",
            "starts_at": _as_utc(f"{day}T{start}:00"), "ends_at": _as_utc(f"{day}T{end}:00"),
            "source_url": source,
        }
        for slug, title, start, end in items
    ]


def snapshot_id(events: list[dict[str, Any]], fetched_at: datetime) -> str:
    canonical = json.dumps(
        [{key: str(event[key]) for key in sorted(event)} for event in events], sort_keys=True, separators=(",", ":")
    )
    return f"{fetched_at:%Y%m%dT%H%M%SZ}-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"
