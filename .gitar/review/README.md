# HiveMind review instructions

Review every feature PR against the final head SHA, then ensure CI runs again if review or follow-up changes modify that SHA. These files are guidance for Gitar and human reviewers; they do not claim to configure a required status check.

## Required attention

- Treat browser session IDs, secret hashes, CSRF values, admin credentials, and Elasticsearch credentials as private. Do not serialize, log, or return them in public API responses.
- User text is untrusted. Validate it server-side and render it as text, never as HTML. Active feed/search/AI paths must re-check report status and expiration on the server.
- Preserve keyboard access, visible focus, semantic labels, readable status text, and reduced-motion behavior.
- Do not turn on paid AI, external content ingestion, or an evolution scheduler without an explicit, separately reviewed approval and spending cap.
- Keep image publication immutable and distinct from deployment promotion. Kubernetes changes must remain namespace-scoped unless explicitly approved.
