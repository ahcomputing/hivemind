import logging
from datetime import UTC, datetime
from typing import Any

from elasticsearch import AsyncElasticsearch, BadRequestError, NotFoundError

from .config import Settings

logger = logging.getLogger(__name__)

SESSION_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "secret_hash": {"type": "keyword", "index": False},
        "csrf_hash": {"type": "keyword", "index": False},
        "avatar_seed": {"type": "keyword"},
        "created_at": {"type": "date"},
        "rate_window": {"type": "long"},
        "rate_count": {"type": "integer"},
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
        "starts_at": {"type": "date"},
        "status": {"type": "keyword"},
        "session_id": {"type": "keyword", "index": False},
        "avatar_seed": {"type": "keyword"},
    },
}
OFFICIAL_EVENT_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "snapshot_id": {"type": "keyword"},
        "source_id": {"type": "keyword"},
        "title": {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
        "description": {"type": "text", "index": False},
        "speaker_names": {"type": "keyword", "ignore_above": 256},
        "location": {"type": "keyword", "ignore_above": 256},
        "starts_at": {"type": "date"},
        "ends_at": {"type": "date"},
        "source_url": {"type": "keyword", "index": False},
        "fetched_at": {"type": "date"},
    },
}
EVENT_STATE_MAPPING = {
    "dynamic": "strict",
    "properties": {"snapshot_id": {"type": "keyword"}, "fetched_at": {"type": "date"}, "count": {"type": "integer"}},
}
CACHE_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "evidence_hash": {"type": "keyword"}, "window_minutes": {"type": "integer"},
        "created_at": {"type": "date"}, "expires_at": {"type": "date"}, "summary": {"type": "object", "enabled": False},
    },
}
USAGE_MAPPING = {
    "dynamic": "strict",
    "properties": {"reserved_microusd": {"type": "long"}, "actual_microusd": {"type": "long"}, "updated_at": {"type": "date"}},
}


class ElasticsearchRepository:
    def __init__(self, settings: Settings):
        auth = (settings.elasticsearch_username, settings.elasticsearch_password)
        self.client = AsyncElasticsearch(
            settings.elasticsearch_url, basic_auth=auth if all(auth) else None
        )
        self.settings = settings
        self._initialized = False

    async def close(self) -> None:
        await self.client.close()

    async def initialize(self) -> None:
        if self._initialized:
            return
        for index, mapping in (
            (self.settings.sessions_index, SESSION_MAPPING),
            (self.settings.reports_index, REPORT_MAPPING),
            (self.settings.official_events_index, OFFICIAL_EVENT_MAPPING),
            (self.settings.event_state_index, EVENT_STATE_MAPPING),
            (self.settings.opportunity_cache_index, CACHE_MAPPING),
            (self.settings.usage_index, USAGE_MAPPING),
        ):
            if not await self.client.indices.exists(index=index):
                try:
                    await self.client.indices.create(index=index, mappings=mapping)
                except BadRequestError:
                    if not await self.client.indices.exists(index=index):
                        raise
            else:
                # Existing production reports are retained.  Adding a mapped field is
                # compatible with Elasticsearch's strict mapping, unlike re-creating
                # the index would be.
                await self.client.indices.put_mapping(index=index, properties=mapping["properties"])
        self._initialized = True

    async def ready(self) -> bool:
        try:
            if not await self.client.ping():
                return False
            await self.initialize()
            return True
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

    async def consume_report_slot(self, session_id: str, window: int, limit: int) -> bool:
        result = await self.client.update(
            index=self.settings.sessions_index,
            id=session_id,
            refresh="wait_for",
            script={
                "lang": "painless",
                "source": """
                    if (ctx._source.rate_window != params.window) {
                      ctx._source.rate_window = params.window;
                      ctx._source.rate_count = 1;
                    } else if (ctx._source.rate_count >= params.limit) {
                      ctx.op = 'none';
                    } else {
                      ctx._source.rate_count += 1;
                    }
                """,
                "params": {"window": window, "limit": limit},
            },
        )
        return result["result"] != "noop"

    async def create_report(self, report_id: str, document: dict[str, Any]) -> None:
        await self.client.index(
            index=self.settings.reports_index, id=report_id, document=document, refresh="wait_for"
        )

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

    async def publish_official_event_snapshot(
        self, snapshot_id: str, events: list[dict[str, Any]], fetched_at: datetime
    ) -> None:
        """Write all validated candidates before switching the one reader pointer.

        The state document is intentionally changed last.  If an importer crashes
        while bulk indexing, public queries continue to use the prior snapshot.
        """
        if not events:
            raise ValueError("an official event snapshot must not be empty")
        operations: list[dict[str, Any]] = []
        for event in events:
            operations.extend(
                [
                    {"index": {"_index": self.settings.official_events_index, "_id": f"{snapshot_id}:{event['source_id']}"}},
                    {"snapshot_id": snapshot_id, **event, "fetched_at": fetched_at},
                ]
            )
        result = await self.client.bulk(operations=operations, refresh="wait_for")
        if result.get("errors"):
            raise RuntimeError("official-event snapshot indexing failed")
        await self.client.index(
            index=self.settings.event_state_index,
            id="current",
            document={"snapshot_id": snapshot_id, "fetched_at": fetched_at, "count": len(events)},
            refresh="wait_for",
        )

    async def official_event_freshness(self) -> dict[str, Any] | None:
        try:
            result = await self.client.get(index=self.settings.event_state_index, id="current")
        except NotFoundError:
            return None
        return result["_source"]

    async def list_official_events_overlapping(
        self, window_start: datetime, window_end: datetime, limit: int = 40
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        state = await self.official_event_freshness()
        if not state:
            return [], None
        result = await self.client.search(
            index=self.settings.official_events_index,
            query={"bool": {"filter": [
                {"term": {"snapshot_id": state["snapshot_id"]}},
                {"range": {"starts_at": {"lt": window_end.isoformat()}}},
                {"range": {"ends_at": {"gt": window_start.isoformat()}}},
            ]}},
            sort=[{"starts_at": {"order": "asc"}}, {"source_id": {"order": "asc"}}],
            size=limit,
        )
        return ([{"id": hit["_source"]["source_id"], **hit["_source"]} for hit in result["hits"]["hits"]], state)

    async def list_reports_for_opportunities(
        self, window_end: datetime, limit: int = 40
    ) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = [
            {"term": {"status": "active"}},
            {"range": {"expires_at": {"gt": datetime.now(UTC).isoformat()}}},
            {"bool": {
                "should": [
                    {"range": {"starts_at": {"lt": window_end.isoformat()}}},
                    {"bool": {"filter": [
                        {"bool": {"must_not": {"exists": {"field": "starts_at"}}}},
                        {"range": {"created_at": {"lt": window_end.isoformat()}}},
                    ]}},
                ],
                "minimum_should_match": 1,
            }},
        ]
        result = await self.client.search(
            index=self.settings.reports_index,
            query={"bool": {"filter": filters}},
            sort=[{"starts_at": {"order": "asc"}}, {"created_at": {"order": "desc"}}],
            size=limit,
        )
        return [{"id": hit["_id"], **hit["_source"]} for hit in result["hits"]["hits"]]
