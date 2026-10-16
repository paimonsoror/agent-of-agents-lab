# Member portal (sample application)

The business application whose incident Maestro investigates. It is deliberately
dependent on all three domains: the **edge gateway** (APIM) fronts it, it caches member
lookups in **Valkey** (cache), and it publishes `member.events` to **Kafka** (messaging).
One image, three entrypoints: `python -m portal.api` (FastAPI on :8000,
`GET /api/members/{id}`, `GET /api/health`, `/metrics`), `python -m portal.consumer`
(Kafka consumer group `portal-consumer`, `/metrics` on :8000) and `python -m portal.loadgen`
(steady synthetic traffic through the edge gateway so every dashboard has a baseline).
Each dependency degrades gracefully — a missing cache is a miss, a missing broker is a
logged publish failure — so a fault in one domain shows up as a *signal*, not a crash.
Metric names are the contract in `docs/contracts.md`.
