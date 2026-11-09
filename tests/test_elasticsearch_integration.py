import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from hivemind.config import Settings
from hivemind.repository import ElasticsearchRepository


@pytest.mark.integration
async def test_real_elasticsearch_persists_across_client_restart():
    url = os.getenv("ELASTICSEARCH_INTEGRATION_URL")
    if not url:
        pytest.skip("set ELASTICSEARCH_INTEGRATION_URL to run against real Elasticsearch")
    prefix = f"hivemind_it_{uuid.uuid4().hex[:10]}"
    repository = ElasticsearchRepository(
        Settings(
            _env_file=None,
            app_secret="x" * 40,
            elasticsearch_url=url,
            elasticsearch_index_prefix=prefix,
            elasticsearch_username=os.getenv("ELASTICSEARCH_USERNAME"),
            elasticsearch_password=os.getenv("ELASTICSEARCH_PASSWORD"),
        )
    )
    await repository.initialize()
    now = datetime.now(UTC)
    await repository.create_report(
        "survives",
        {
            "content": "persistent report",
            "location": None,
            "category": "general",
            "expires_at": now + timedelta(hours=1),
            "created_at": now,
            "status": "active",
            "session_id": "private",
            "avatar_seed": "public",
        },
    )
    await repository.close()
    restarted = ElasticsearchRepository(repository.settings)
    assert [item["content"] for item in await restarted.list_active_reports()] == [
        "persistent report"
    ]
    await restarted.client.indices.delete(index=f"{prefix}_*")
    await restarted.close()


@pytest.mark.integration
async def test_real_elasticsearch_budget_reservation_is_atomic_across_callers():
    url = os.getenv("ELASTICSEARCH_INTEGRATION_URL")
    if not url:
        pytest.skip("set ELASTICSEARCH_INTEGRATION_URL to run against real Elasticsearch")
    prefix = f"hivemind_it_{uuid.uuid4().hex[:10]}"
    repository = ElasticsearchRepository(
        Settings(
            _env_file=None,
            app_secret="x" * 40,
            elasticsearch_url=url,
            elasticsearch_index_prefix=prefix,
            elasticsearch_username=os.getenv("ELASTICSEARCH_USERNAME"),
            elasticsearch_password=os.getenv("ELASTICSEARCH_PASSWORD"),
        )
    )
    await repository.initialize()
    now = datetime.now(UTC)
    results = await asyncio.gather(
        *[repository.reserve_openai_budget("2026-11", 10, 100, now) for _ in range(20)]
    )
    assert sum(results) == 10
    await repository.client.indices.delete(index=f"{prefix}_*")
    await repository.close()
