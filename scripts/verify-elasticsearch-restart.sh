#!/usr/bin/env bash
set -euo pipefail
# Local-only proof after `docker compose up -d`; intentionally not run by CI.
curl -fsS -u "${ELASTICSEARCH_USERNAME:-elastic}:${ELASTICSEARCH_PASSWORD:?set password}" -X PUT localhost:9200/hivemind_restart_proof/_doc/persisted -H 'Content-Type: application/json' -d '{"message":"survives restart"}'
docker compose restart elasticsearch
until curl -fsS -u "${ELASTICSEARCH_USERNAME:-elastic}:${ELASTICSEARCH_PASSWORD}" localhost:9200/_cluster/health >/dev/null; do sleep 2; done
curl -fsS -u "${ELASTICSEARCH_USERNAME:-elastic}:${ELASTICSEARCH_PASSWORD}" localhost:9200/hivemind_restart_proof/_doc/persisted
