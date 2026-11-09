# HiveMind

HiveMind is an attendee-powered, mobile-first conference signal board. This first vertical slice lets anonymous visitors post short expiring reports and see active reports in other browsers. It is deliberately small and honest: reports are unverified attendee observations, while AI, official schedule ingestion, questions, moderation, and evolution are extension points—not shipped features.

## What works now

- A purple, keyboard-accessible report form and polling feed (15 seconds) with a Coffee filter.
- Reports of up to 500 characters, optional location and category, and 15-minute, one-hour, end-of-day, or future custom expiry. Storage is UTC; the browser displays America/Denver time.
- Pseudonymous per-browser identity: an HttpOnly session cookie contains a random identifier plus secret; only SHA-256 hashes of secrets live in Elasticsearch. A separate public random avatar seed is sent to RoboHash. Failed avatar images fall back to a local robot glyph.
- CSRF checks, ownership checks, server-side validation, escaped client rendering, query-time active/expiration filtering, and a persistent per-session anonymous write limit.
- Optional Dash0-compatible OpenTelemetry tracing, shipped disabled. It uses the standard OTLP/HTTP exporter, so no Dash0 SDK is coupled into the request path.
- Elasticsearch is the only primary application store. The mapped indices are `hivemind_sessions` and `hivemind_reports` by default; set `ELASTICSEARCH_INDEX_PREFIX` to isolate an environment.

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

`OPENAI_API_KEY`, an admin account, and evolution settings are configuration placeholders only. There are no AI calls, OpenAI SDK dependencies, scheduler, or evolution endpoint in this increment. Paid AI remains off until an explicit cap and approval exist.

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

RoboHash is a third-party request made by the browser using only the public avatar seed. It does not receive session IDs, session secrets, IP addresses from the app, or report text; a network observer at RoboHash still receives the browser request. Clearing browser data loses the pseudonymous identity. Robots are attribution, not accounts or proof of a unique person.

This release has no login, author edits, moderator UI, flags, questions/replies, official content import, search UI, provenance, backup automation, high availability, or accessibility certification. Elasticsearch is single-node and therefore not highly available. Longhorn protects the volume, not service availability. Mobile layout and keyboard controls are implemented and covered by source-level checks, but a real phone-on-cellular test remains a public-launch gate.

## AI assistance and review

This project was built with AI coding assistance. Human review is required for every deployment and for any future feature that processes reports, uses AI, or changes infrastructure. `.gitar/review/` supplies repository-specific review guidance for session privacy, accessibility, source claims, and the permanently-off evolution controls. Verify that Gitar's GitHub App has actually reviewed the final feature PR and rerun checks on its final head SHA; the repository does not claim that configuration is already complete.

## Next milestones

1. Approve and apply the preflighted namespace, secrets, image pull policy, ingress/DNS, then verify a phone on cellular and two independent browsers within one polling interval.
2. Add report ownership edits, questions/replies, two-session flags, authenticated moderation, and concurrency tests.
3. Import the official schedule with source timestamps and a last-good snapshot, then add keyword retrieval and sourced answers with explicit uncertainty.
4. Design the isolated, manually triggered evolution runner: sanitized aggregate usage, branch-only changes, Gitar review, CI, staging, manual promotion, rollback, and freeze tests. It must remain disabled until separately approved.
