#!/usr/bin/env python3
"""Fetch, validate, and atomically publish the public official schedule."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from urllib.request import Request, urlopen

from hivemind.config import get_settings
from hivemind.events import SESSIONIZE_URL, monday_hackathon_events, sessionize_events, snapshot_id
from hivemind.repository import ElasticsearchRepository


def fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "HiveMind official schedule importer/0.1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed, public operator source
        return json.load(response)


async def run(include_hackathon: bool) -> None:
    fetched_at = datetime.now(UTC)
    events, counts = sessionize_events(fetch(SESSIONIZE_URL), fetched_at)
    if include_hackathon:
        events.extend(monday_hackathon_events())
    identifier = snapshot_id(events, fetched_at)
    repository = ElasticsearchRepository(get_settings())
    try:
        await repository.initialize()
        await repository.publish_official_event_snapshot(identifier, events, fetched_at)
    finally:
        await repository.close()
    print(json.dumps({**counts, "published": len(events), "snapshot_id": identifier}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-monday-hackathon", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.include_monday_hackathon))
