import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError

from .config import Settings

logger = logging.getLogger(__name__)

SESSION_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "secret_hash": {"type": "keyword", "index": False},
        "csrf_hash": {"type": "keyword", "index": False},
        "avatar_seed": {"type": "keyword"},
        "created_at": {"type": "date"},
    },
}
REPORT_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "content": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
        },
        "location": {"type": "keyword", "ignore_above": 256},
        "category": {"type": "keyword"},
        "expires_at": {"type": "date"},
        "created_at": {"type": "date"},
        "status": {"type": "keyword"},
        "session_id": {"type": "keyword", "index": False},
        "avatar_seed": {"type": "keyword"},
    },
}


class ElasticsearchRepository:
    def __init__(self, settings: Settings):
        auth = (settings.elasticsearch_username, settings.elasticsearch_password)
        self.client = AsyncElasticsearch(
            settings.elasticsearch_url, basic_auth=auth if all(auth) else None
        )
        self.settings = settings

    async def close(self) -> None:
        await self.client.close()

    async def initialize(self) -> None:
        for index, mapping in (
            (self.settings.sessions_index, SESSION_MAPPING),
            (self.settings.reports_index, REPORT_MAPPING),
        ):
            if not await self.client.indices.exists(index=index):
                await self.client.indices.create(index=index, mappings=mapping)

    async def ready(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:  # health endpoint must not reveal connection details
            return False

    async def create_session(self, session_id: str, document: dict[str, Any]) -> None:
        await self.client.index(
            index=self.settings.sessions_index, id=session_id, document=document, refresh="wait_for"
        )

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        try:
            found = await self.client.get(index=self.settings.sessions_index, id=session_id)
        except NotFoundError:
            return None
        return found["_source"]

    async def update_session(self, session_id: str, document: dict[str, Any]) -> None:
        await self.client.index(
            index=self.settings.sessions_index, id=session_id, document=document, refresh="wait_for"
        )

    async def create_report(self, report_id: str, document: dict[str, Any]) -> None:
        await self.client.index(
            index=self.settings.reports_index, id=report_id, document=document, refresh="wait_for"
        )

    async def report_count_since(self, session_id: str, after: datetime) -> int:
        result = await self.client.count(
            index=self.settings.reports_index,
            query={
                "bool": {
                    "filter": [
                        {"term": {"session_id": session_id}},
                        {"range": {"created_at": {"gte": after.isoformat()}}},
                    ]
                }
            },
        )
        return int(result["count"])

    async def list_active_reports(self, category: str | None = None) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [
            {"term": {"status": "active"}},
            {"range": {"expires_at": {"gt": datetime.now(UTC).isoformat()}}},
        ]
        if category and category != "all":
            filters.append({"term": {"category": category}})
        result = await self.client.search(
            index=self.settings.reports_index,
            query={"bool": {"filter": filters}},
            sort=[{"created_at": {"order": "desc"}}],
            size=50,
        )
        return [{"id": hit["_id"], **hit["_source"]} for hit in result["hits"]["hits"]]
