# HiveMind

HiveMind is an attendee-powered, mobile-first conference signal board. Visitors can view a source-first opportunities briefing, share short expiring reports, and see active attendee reports in other browsers. Reports are unverified observations and are always labelled separately from official-event data.

## What works now

- Three purple, keyboard-accessible pages: the click-only opportunities briefing, Share an update, and the 15-second-polling User reports feed with a Coffee filter.
- Reports of up to 500 characters, optional location/category/start time, and 15–120-minute, end-of-day, or future custom expiry. Storage is UTC; the browser displays America/Denver time. Relative expiry runs from the selected start time.
- An operator-run official-event importer for the public Sessionize endpoint, with a separate reviewed Monday hackathon dataset. It validates the complete response before atomically switching the public reader to a new snapshot, retaining the last-good schedule on failure. Run `uv run python scripts/import_official_events.py --include-monday-hackathon`; it never runs automatically.
- Avatar-only reporter identity: no username, handle, or display name is created. An HttpOnly session cookie contains a private random identifier plus secret; only SHA-256 hashes of secrets live in Elasticsearch. A separate public random avatar seed is sent to HiveMind's own self-hosted RoboHash instance. Failed avatar images fall back to a local robot glyph.
- CSRF checks, ownership checks, server-side validation, escaped client rendering, query-time active/expiration filtering, and a persistent per-session anonymous write limit.
- Optional Dash0-compatible OpenTelemetry tracing, shipped disabled. It uses the standard OTLP/HTTP exporter, so no Dash0 SDK is coupled into the request path.
- Elasticsearch is the only primary application store. The mapped indices include `hivemind_sessions`, `hivemind_reports`, and `hivemind_official_events` by default; set `ELASTICSEARCH_INDEX_PREFIX` to isolate an environment.

## Architecture

```text
browser -- HTTPS --> mailserver Nginx --> Traefik Ingress --> FastAPI replicas --> internal Elasticsearch StatefulSet
                        |                    |              |
                        |                    |              +-- Jinja + minimal JavaScript, 15 s polling
                        |                    +-- private-LAN HTTP only
                        +-- public Let's Encrypt certificate
```

The browser never talks to Elasticsearch. Session identifiers, session secret hashes, CSRF hashes, and public avatar seeds are separate fields. A report stores the owning session identifier privately and only returns its public attributes to the feed. Expiration and status are filters in every public report query rather than a browser-only convention.

## Local setup

1. Copy `.env.example` to `.env`, then replace every `CHANGE_ME` value. The local `.env` is ignored. Development may use `COOKIE_SECURE=false`; production cannot.
2. Install dependencies with `uv sync --all-groups`.
3. Start authenticated Elasticsearch and the app: `docker compose up --build`.
4. Open `http://localhost:8080`. The app liveness endpoint is `/healthz`; `/readyz` returns 503 until Elasticsearch is reachable.

Run checks with:

```bash
uv run ruff check hivemind tests
uv run pytest -q
```

The real-Elasticsearch integration test is opt-in and never silently substitutes an in-memory database:

```bash
ELASTICSEARCH_INTEGRATION_URL=http://localhost:9200 \
ELASTICSEARCH_USERNAME=elastic ELASTICSEARCH_PASSWORD='…' \
uv run pytest -m integration -q
```

After local Compose is healthy, `scripts/verify-elasticsearch-restart.sh` writes a proof record, restarts Elasticsearch, and reads it back. It is an explicit operator check, not an unrun claim.

## Configuration and secrets

`.env.example` documents every setting. Startup rejects placeholder secrets, a too-short `APP_SECRET`, production without secure cookies or Elasticsearch/admin credentials, and any attempt to enable evolution. No setting values are logged. Kubernetes refers to an out-of-band `hivemind-secrets` Secret; `k8s/secrets.example.yaml` is intentionally unusable.

`OPENAI_API_KEY`, an admin account, and evolution settings are configuration placeholders only. The opportunities endpoint provides safe source cards while AI is disabled. Paid summaries require `OPENAI_SUMMARY_ENABLED=true`, an explicit model, verified current input/output prices, and the fixed $50 UTC-month cap; startup rejects an incomplete or altered paid configuration. When enabled, HiveMind makes one 30-second/no-retry Responses API call only after an Elasticsearch-backed maximum-cost reservation. It settles known usage, conservatively retains uncertain reservations, limits a browser to three paid generations a minute, and caches a validated evidence/window result for 60 seconds across replicas. Model output must use the retrieved source IDs; unsupported or expired citations are never displayed. The code intentionally does not infer a model or activate spending from an API key.

### Dash0 telemetry

The container starts through `opentelemetry-instrument`, with `OTEL_SDK_DISABLED=true` by default. To use Dash0 after approval, change that setting to `false`, put the Dash0 OTLP/HTTP base endpoint in `OTEL_EXPORTER_OTLP_ENDPOINT`, and store `OTEL_EXPORTER_OTLP_HEADERS` only in `hivemind-secrets` (for example `authorization=Bearer …,dash0-dataset=default`). The standard HTTP exporter appends signal paths such as `/v1/traces`; do not add them to the base endpoint. Do not set OpenTelemetry header/body capture options: HiveMind report text, cookie values, CSRF tokens, session identifiers, locations, and avatar seeds are intentionally excluded from telemetry. This follows Dash0’s OTLP endpoint/header configuration guidance. [Dash0 OpenTelemetry environment variables](https://www.dash0.com/guides/opentelemetry-environment-variables)

## Kubernetes and image delivery

`k8s/` contains namespace-scoped resources only:

- a Longhorn-backed, secured single Elasticsearch StatefulSet (10 GiB PVC), internal-only Service, and explicit resource limits;
- a two-replica FastAPI Deployment, Service, Traefik Ingress for `hivemind.ahcomputing.com`, and health probes;
- no production Secret values, DNS modification, cluster-wide resource, scheduler, or auto-promotion.

Before any apply, run `scripts/preflight-cluster.sh`. It only reads cluster state and host `vm.max_map_count`; Elasticsearch needs a value of at least 262144 on each possible node. Confirm Longhorn's current schedulable capacity and two-replica health too. Do not change a node kernel setting or a storage-class default implicitly. Public TLS terminates at the mailserver Nginx ingress; the namespace-scoped Traefik rule intentionally accepts only its private-LAN HTTP hop. DNS/public routing and deployment are approval gates.

After the app is healthy and `hivemind.ahcomputing.com` resolves to the mailserver's public address, copy `scripts/deploy_mailserver.py` to that host and run it there. It writes only the HiveMind virtual host, checks Nginx before each reload, keeps a timestamped backup of a prior script-managed version, verifies the private Traefik upstream, and invokes the mailserver's existing Certbot integration. Run with `--dry-run` first; supply `--email` only for a non-interactive first Certbot registration.

GitHub Actions runs Ruff and pytest, then publishes only an immutable `ghcr.io/ahcomputing/hivemind:<commit-sha>` image on a `main` push. Publishing does not edit a manifest or deploy. Promote a reviewed SHA separately, substituting the exact image into `k8s/app.yaml`; configure a scoped image-pull secret only if GHCR remains private.

## Privacy, security, and limitations

Avatars are rendered by a RoboHash instance HiveMind runs itself (`k8s/robohash/`), so no third party receives the request. The avatar request carries only the public random seed: no session IDs, session secrets, IP addresses from the app, or report text. If that instance is unreachable the browser shows a local glyph rather than falling back to the public service, so the avatar seed never leaves this infrastructure. The honest limitation runs the other way: avatars now depend on the cluster being up. Set `AVATAR_BASE_URL=https://robohash.org` to use the public service instead, which reinstates the third-party request. No Content-Security-Policy is set today; when one is added, `img-src` must cover the configured avatar origin. Clearing browser data gives that browser a new robot. Robots are the only public attribution, not accounts or proof of a unique person.

This release has no login, author edits, moderator UI, flags, questions/replies, official content import, search UI, provenance, backup automation, high availability, or accessibility certification. Elasticsearch is single-node and therefore not highly available. Longhorn protects the volume, not service availability. Mobile layout and keyboard controls are implemented and covered by source-level checks, but a real phone-on-cellular test remains a public-launch gate.

## Avatars and attribution

Avatars come from a RoboHash instance HiveMind runs on its own cluster rather than
from the public service. The manifests are in `k8s/robohash/`; it is a stateless
Deployment of upstream's published image pinned by digest, on its own host so other
projects can share it. Deploy it with `kubectl apply -k k8s/robohash/`, and point the
app at it with `AVATAR_BASE_URL`.

That bundle creates a `robohash` Namespace, which is a cluster-scoped object and
so an exception to the namespace-scoped rule in `.gitar/review/README.md`. The
approval for it, who gave it and the alternative that was rejected are recorded
in the header of `k8s/robohash/namespace.yaml`.

RoboHash's Python code is MIT. Its artwork is Creative Commons and per-set, so
self-hosting it means carrying the attribution ourselves:

- **set1, "classic robots" (in use): Zikri Kader, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).**
- set2 monsters: Hrvoje Novakovic, CC BY 3.0. set3 robot heads: Julian Peter Arias,
  CC BY 3.0. set4 cats: David Revoy, CC BY 4.0. set5 humans: Pablo Stanley. set6
  cosmic apes: OceanSlim, CC0.

If you change the `set=` parameter in `avatar()` in `hivemind/static/app.js`, update
the credit line in the page footer to match the artist for that set.

## AI assistance and review

This project was built with AI coding assistance. Human review is required for every deployment and for any future feature that processes reports, uses AI, or changes infrastructure. `.gitar/review/` supplies repository-specific review guidance for session privacy, accessibility, source claims, and the permanently-off evolution controls. Verify that Gitar's GitHub App has actually reviewed the final feature PR and rerun checks on its final head SHA; the repository does not claim that configuration is already complete.

## Next milestones

1. Approve and apply the preflighted namespace, secrets, image pull policy, ingress/DNS, then verify a phone on cellular and two independent browsers within one polling interval.
2. Add report ownership edits, questions/replies, two-session flags, authenticated moderation, and concurrency tests.
3. Configure a reviewed OpenAI model/pricing, then add structured cited summaries with the shared Elasticsearch budget ledger, cache coalescing, and failure-safe reconciliation.
4. Design the isolated, manually triggered evolution runner: sanitized aggregate usage, branch-only changes, Gitar review, CI, staging, manual promotion, rollback, and freeze tests. It must remain disabled until separately approved.
