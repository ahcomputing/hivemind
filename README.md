<p align="center">
  <img src="hivemind/static/ui/icons/favicon.svg" width="96" alt="HiveMind brain in a jar">
</p>

<h1 align="center">HiveMind</h1>

<p align="center"><strong>Live, source-aware conference signal—made by the people in the room.</strong></p>

<p align="center">
  <a href="https://hivemind.ahcomputing.com">Visit HiveMind</a>
  ·
  <a href="https://github.com/ahcomputing/hivemind/actions">Build status</a>
  ·
  <a href="https://github.com/ahcomputing/hivemind/pkgs/container/hivemind">Container images</a>
</p>

HiveMind is a mobile-first conference signal board. Visitors can find official
events, ask for a cited talk recommendation, share short-lived observations,
and see the current attendee feed from other browsers. Official schedule data
and attendee reports are deliberately presented as different kinds of evidence:
one is a source; the other is an observation from the hive.

> **Live:** [hivemind.ahcomputing.com](https://hivemind.ahcomputing.com) ·
> **Timezone:** America/Denver for display, UTC for storage ·
> **Identity:** a browser has a robot—not a username or profile.

## What is here now

- **Three focused pages.** The source-first opportunities page, a Share an
  update form, and a 15-second-polling User reports feed with a Coffee filter.
- **Official schedule, safely imported.** An operator-triggered Sessionize
  importer validates a complete response before atomically switching readers
  to a new snapshot. A reviewed Monday hackathon dataset joins the same
  snapshot. If an import fails, readers keep the last known-good schedule.
- **Cited “Find my ideal talk” recommendations.** A visitor can enter their
  interests and receive recommendations grounded in current official events.
  Attendee reports may add clearly labelled context—such as a room filling up
  fast—but every recommendation must cite at least one official event.
- **Anonymous, not unaccountable.** Reports allow up to 500 characters, an
  optional location, category, start time, and an expiry of 15–120 minutes,
  end of day, or a future custom time. Server-side validation, expiration,
  CSRF checks, ownership checks, escaping, and persistent per-browser rate
  limits apply to every report.
- **Robot-only identity.** An HttpOnly browser cookie holds a private random
  identifier and secret; only SHA-256 secret hashes are stored. A distinct
  public seed selects a self-hosted RoboHash robot. A local glyph appears if
  RoboHash is unavailable.
- **Operationally visible.** OpenTelemetry traces and structured application
  logs export to Dash0 using standard OTLP/HTTP. Kubernetes provides liveness
  and readiness checks; Dash0 is deliberately human-monitored rather than an
  automatic recovery system.
- **One real datastore.** Elasticsearch is the only primary store for session
  records, reports, official-event snapshots, bounded recommendation cache,
  and AI usage accounting.

## The shape of the system

```text
browser
  │ HTTPS
  ▼
mailserver Nginx ──► Traefik Ingress ──► 2 × FastAPI replicas
                                                │
                                                ├──► internal Elasticsearch StatefulSet
                                                ├──► self-hosted RoboHash
                                                └──► Dash0 (OTLP traces + logs)
```

Public TLS terminates at the mailserver Nginx. The cluster ingress accepts only
the private-LAN HTTP hop. Browsers never communicate with Elasticsearch,
RoboHash's cluster address, or Dash0 directly.

| Concern | Implementation |
| --- | --- |
| Application data | Authenticated single-node Elasticsearch on a 10 GiB Longhorn PVC |
| Public identity | Per-browser robot avatar; no handles, usernames, or profiles |
| Schedule freshness | Atomically published last-good snapshot with displayed refresh time |
| AI output | Structured, cited Responses API output with a fixed budget and safe fallback |
| Telemetry | Dash0 via vendor-neutral OpenTelemetry / OTLP |
| Delivery | Immutable commit-SHA images in GHCR; reviewed deployment promotion is separate |
| Cluster view | Radar for Kubernetes topology, resources, logs, events, and diagnostics |

## Completed portions

### Conference experience

- Mobile-first purple UI with keyboard-accessible controls and reduced-motion
  support.
- Shared anonymous reports across browsers, with safe rendering and
  server-side active/status/expiration filtering.
- Self-hosted RoboHash avatar delivery through same-origin `/avatars/<seed>.png`.
- Official-session importer with snapshot semantics and a public freshness cue.
- Source cards for official events and attendee observations, kept visually and
  semantically distinct.

### Cited assistance, with spending controls

- An optional `gpt-6-luna` Responses API path for opportunity briefs and
  interest-based talk recommendations.
- Explicit model and verified price configuration; a fixed **$50 UTC-month**
  maximum; 30-second timeout; no retry; bounded input/output tokens.
- Elasticsearch-backed maximum-cost reservation, actual-usage reconciliation,
  uncertain-reservation retention, cross-replica 60-second evidence caching,
  and a three-generation-per-browser-per-minute limit.
- If AI, accounting, or the monthly cap is unavailable, source cards remain
  useful and the application does not pretend a summary exists.

### Deployment and review path

- Two FastAPI replicas, internal Elasticsearch, Longhorn-backed storage,
  Traefik ingress, and public mailserver TLS routing.
- GitHub Actions runs Ruff and pytest, then publishes an immutable
  `ghcr.io/ahcomputing/hivemind:<commit-sha>` image only after `main` passes.
- Gitar and CI are required checks on `main`; repository-specific review
  guidance covers privacy, citations, accessibility, spending, and deployment
  boundaries.
- Dash0 receives application telemetry; Radar provides the Kubernetes
  operations view. Neither product automatically changes production state.

## Run it locally

1. Copy `.env.example` to `.env` and replace every `CHANGE_ME` value. The
   local `.env` is ignored by Git. Development may use `COOKIE_SECURE=false`;
   production cannot.
2. Install dependencies with `uv sync --all-groups`.
3. Start authenticated Elasticsearch, the self-hosted RoboHash renderer, and
   the app:

   ```bash
   docker compose up --build
   ```

4. Open <http://localhost:8080>. `/healthz` is the liveness endpoint;
   `/readyz` returns `503` until Elasticsearch is reachable.

Run the ordinary checks:

```bash
uv run ruff check hivemind tests
uv run pytest -q
```

The real-Elasticsearch integration suite is deliberately opt-in; it never
silently uses an in-memory substitute:

```bash
ELASTICSEARCH_INTEGRATION_URL=http://localhost:9200 \
ELASTICSEARCH_USERNAME=elastic ELASTICSEARCH_PASSWORD='…' \
uv run pytest -m integration -q
```

After Compose is healthy, `scripts/verify-elasticsearch-restart.sh` writes a
proof record, restarts Elasticsearch, and verifies the record survives. It is
an explicit operator check, not an unrun claim.

## Configuration and AI safety

`.env.example` documents every setting. Startup rejects placeholder secrets, a
short `APP_SECRET`, production without secure cookies or Elasticsearch/admin
credentials, and any attempt to enable evolution. Values are never logged.
Kubernetes refers to an out-of-band `hivemind-secrets` Secret;
`k8s/secrets.example.yaml` is intentionally unusable.

An OpenAI key alone never enables paid traffic. Paid recommendations require
all of the following together:

- `OPENAI_SUMMARY_ENABLED=true`
- an explicit model identifier
- verified input and output pricing
- the fixed $50 UTC-month cap

The visitor's interests are untrusted prompt input. They are not linked to a
session identifier, avatar seed, or stored profile; they affect only a hashed
cache key. Output must cite retrieved evidence. An ideal-talk result must cite
an official event, while attendee reports may appear only as labelled context.
Expired or unsupported citations are discarded before display.

### Dash0 telemetry

HiveMind uses `opentelemetry-instrument` and the standard OTLP/HTTP exporter.
Set `OTEL_SDK_DISABLED=false`, configure the Dash0 base endpoint in
`OTEL_EXPORTER_OTLP_ENDPOINT`, and keep `OTEL_EXPORTER_OTLP_HEADERS` solely in
`hivemind-secrets`. The exporter adds paths such as `/v1/traces` itself.

Do **not** enable OpenTelemetry header or body capture. Report text, cookie
values, CSRF tokens, session identifiers, locations, and avatar seeds are
excluded from telemetry by design. See [Dash0’s OpenTelemetry environment
variable guidance](https://www.dash0.com/guides/opentelemetry-environment-variables).

## Operations and delivery

`k8s/` contains namespace-scoped resources:

- a secured, Longhorn-backed Elasticsearch StatefulSet and internal-only
  service;
- a two-replica FastAPI Deployment, Service, Traefik Ingress, probes, and
  resource limits;
- no production secret values, DNS mutation, cluster-wide default change, or
  deployment auto-promotion.

Before an apply, run `scripts/preflight-cluster.sh`. It reads current cluster
state and `vm.max_map_count`; Elasticsearch needs at least `262144` on every
possible node. Confirm Longhorn's schedulable capacity and two-replica health
before changing storage. Do not alter node settings or the default storage
class implicitly.

For the mailserver edge, use `scripts/deploy_mailserver.py` on that host. It
writes only the HiveMind virtual host, validates Nginx before reload, retains a
timestamped script-managed backup, verifies the private Traefik upstream, and
uses the mailserver's existing Certbot integration. Start with `--dry-run`;
use `--email` only for a first non-interactive Certbot registration.

GitHub Actions publishes, but does not deploy. Promote a reviewed SHA
separately, then verify rollout, public `/readyz`, and the intended user flow.

## Privacy, attribution, and limits

RoboHash runs inside the cluster rather than at the public service. The browser
requests only same-origin `/avatars/<seed>.png`; HiveMind validates the public
seed and fetches only from the fixed cluster-local service. No session secret,
IP address, or report text goes to RoboHash. If the renderer is unavailable,
the browser uses a local glyph instead of falling back to a third party.

The classic robot set is by Zikri Kader under
[CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); RoboHash's Python
code is MIT. See `k8s/robohash/` and `hivemind/static/ui/README.md` before
changing the set or its credit.

HiveMind does **not** currently provide login, author edits, flags, a moderator
UI, questions/replies, search, a provenance browser, backup automation,
Elasticsearch high availability, or an accessibility certification. Longhorn
protects the volume, not service availability. The mobile UI and keyboard
controls have source-level coverage, but a real phone-on-cellular check remains
the final public-launch acceptance test.

## Abandoned features — by design

These are intentional product and safety decisions, not hidden roadmap items:

- **Self-evolution or an evolution scheduler.** HiveMind will not autonomously
  inspect usage, alter its code, open a PR, merge, or deploy. The setting is
  rejected at startup. Product changes stay branch-based, reviewed, tested,
  and manually promoted.
- **Automatic production promotion and recovery.** CI publishes an immutable
  image; a person approves deployment. Dash0 and Radar provide visibility, and
  Kubernetes probes may restart a failed container, but no system performs an
  automatic rollback or product-level repair.
- **Usernames, handles, profiles, and account identity.** The robot is the
  entire public attribution model. Clearing browser data produces a new robot.
- **Third-party avatar delivery.** HiveMind does not fall back to public
  RoboHash; avatar seeds stay on this infrastructure.
- **Automatic schedule scraping or refresh.** Official schedule imports are
  explicit operator actions so a bad upstream response cannot silently replace
  the last-good snapshot.
- **Unbounded or unsourced AI answers.** No key-only activation, arbitrary web
  retrieval, uncited generated claims, or open-ended spend is part of HiveMind.

## AI assistance and review

This project was built with AI coding assistance. Human review remains required
for deployments and for changes touching reports, AI, or infrastructure.
`.gitar/review/` provides project-specific review guidance. Gitar must review
the final PR commit, CI must pass that exact commit, and deployment promotion
remains a separate human decision.
