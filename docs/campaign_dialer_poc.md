# Campaign Dialer for Voice AI — POC Document

Status: Draft for review
Owner service: talko-service (all campaign/lead/dialer logic, data, and APIs)
Consumer: makun-ai (calls talko-service APIs; contributes no dialer state)

---

## 1. Executive Summary

This POC adds a campaign/lead outbound dialer to talko-service, similar in spirit to
Voice Genie / Tata Tele's own dialer products, but supporting **both AI-bridged calls**
(bot-driven, via makun-ai's voice pipeline) **and human-agent calls** (via Tata Tele),
from a single campaign/lead data model.

Key existing capability this POC builds on top of: **placing a single AI-bridged
outbound call already works end-to-end** in the current codebase (talko-service places
the call via Tata Tele and pre-creates a makun-ai voice session that bridges in
automatically). This POC is about the **campaign, lead, pacing, retry, DID allocation,
and reporting layer** on top of that primitive — not about building call placement or
the AI voice pipeline from scratch.

## 2. Goals / Non-Goals

**Goals**
- Bulk lead ingestion into named campaigns.
- Campaign lifecycle: create, start, pause, stop.
- Two call types per campaign: `ai` (bot-driven) and `human` (agent-driven).
- Pacing: progressive (default) and predictive (opt-in, AI campaigns only).
- DID allocation from the existing DID pool, aware of AI vs. human DID types.
- Retry/backoff on no-answer/busy, DND/calling-window compliance.
- Cost governance (call duration caps, budget caps).
- Real-time + rollup reporting, exposed as APIs for makun-ai to consume.
- Horizontal scalability and multi-partner fairness.

**Non-Goals (for this POC)**
- Building a custom agent-presence/predictive-dialing engine for human agents — delegated
  to Tata Tele's existing broadcast dialer product.
- Building a CRM or lead-scoring system.
- Adding a new telephony vendor — stays on Tata Tele.

## 3. What Already Exists vs. What's New

Verified directly against the codebase (not assumed):

| Capability | Status | Where |
|---|---|---|
| Place outbound call, AI-bridged, no human agent needed | Exists | `POST /talko-service/v1/call`, `enable_ai_bridge=true` — `src/components/call_management/dto.py:31` |
| Pre-create warm AI voice session while ringing | Exists | `_pre_create_session()` → `POST /ai/v1/voice/sessions` (makun-ai) — `src/components/call_management/services.py:397-418` (talko-service), `src/components/voice/controllers.py:152` (makun-ai) |
| TalkoCDR with campaign_id, lead_id, disposition, llm_analysis | Exists | `src/components/cdr/models.py` |
| DID pool with AI vs. human split | Exists | `TalkoPhoneNumberManagement.did_type` = `NORMAL` \| `AI_AGENT` — `src/components/did_management/models.py:26` |
| Human-agent broadcast dialer (Tata-native) | Exists | `src/components/dialer/` — `GET /lead-lists`, `POST /lead-lists/{list_id}/leads` |
| Static agent↔DID↔service-board mapping | Exists | `src/components/call_agent_map/` |
| Campaign entity, lead lifecycle, pacing/dispatch engine, agent presence tracking | **Does not exist** | **This POC** |

Note: talko-service's operational datastore is **MongoDB** (via Motor/`AsyncIOMotorClient`,
`src/core/doc_db.py`), matching the pattern used by `TalkoCDR` and `TalkoPhoneNumberManagement`. The
SQLAlchemy/Postgres wiring in `src/core/db.py` is legacy scaffolding, unused in the call/dialer
path, and is not used by this design.

## 4. Ownership & Integration Model

- **talko-service** owns all campaign/lead/dialer state, business logic, and background
  workers. It is the system of record.
- **makun-ai** is a pure API consumer: it calls talko-service to create campaigns, upload
  leads, control lifecycle, and pull reports. Its only role in call execution is the
  existing `/ai/v1/voice/sessions` endpoint, called internally by talko-service exactly
  as it is today — no changes required there.
- Auth: reuse the existing partner-scoped API-key mechanism already used between the two
  services; no new auth system.

## 5. Architecture

```
makun-ai (UI/backend)
   │ REST: create campaign, upload leads, start/pause, get status/report
   ▼
talko-service — new "campaign" module (MongoDB via Motor, same convention as TalkoCDR/DID)
   │
   ├─ call_type = "human" ──► sync leads into Tata Tele broadcast list
   │                          (existing bulk_create_leads) — Tata paces + rings agents
   │                          natively; no new pacing/presence code needed
   │
   └─ call_type = "ai" ─────► talko-owned dispatch engine:
          Mongo (durable) → Redis sorted-set queue (hot path) → Celery workers
          → per-lead lock (idempotency) → per-partner concurrency/budget check
          → POST /call (enable_ai_bridge=true) → Tata dials customer
          → pre-created makun-ai voice session bridges in automatically
                    │
                    ▼
   Both paths converge: existing /call/webhook?type=dialer → TalkoCDR upsert
                    │
                    ▼
   Campaign/Lead status sync job reads TalkoCDR → updates Lead.status, schedules retries
                    │
                    ▼
   Reporting rollup ── GET /campaigns/{id}/report ── served to makun-ai
```

**Key decision**: for human-agent campaigns, delegate pacing/predictive-dial/agent-presence
entirely to Tata Tele's own broadcast dialer instead of rebuilding agent-presence tracking
and abandon-rate compliance ourselves — that infra does not exist in talko-service today
(confirmed: `call_agent_map` only does static agent↔DID mapping, no live presence/status)
and is expensive to build correctly. For AI campaigns, talko-service owns the full dispatch
engine, since Tata's product has no concept of AI bridging. Both call types share one
`Campaign`/`Lead` schema and one API surface, so makun-ai's integration is identical
regardless of call type.

## 6. Data Model (MongoDB)

Follows the existing `TalkoTimestampedModel` / `CollectionName` convention used by `TalkoCDR` and
`TalkoPhoneNumberManagement`.

```python
class Campaign(TalkoTimestampedModel):
    partner_id: int
    name: str
    call_type: str                      # "ai" | "human"
    agent_id: Optional[int]             # makun-ai agent, required if call_type=ai
    tata_lead_list_id: Optional[str]    # set if call_type=human
    dial_mode: str = "progressive"      # "progressive" | "predictive" (AI only)
    pacing_ratio: Optional[float]
    calling_window: Dict[str, Any]      # start, end, timezone
    max_retries: int = 3
    retry_backoff_minutes: int = 15
    max_call_duration_seconds: Optional[int]
    daily_budget: Optional[float]
    status: str = "draft"               # draft | running | paused | completed

    class CollectionName:
        CAMPAIGN = "campaign"


class Lead(TalkoTimestampedModel):
    campaign_id: ObjectId
    partner_id: int
    phone: str
    custom_fields: Dict[str, Any] = {}  # → context_data on /call
    status: str = "pending"             # pending | queued | in_progress | completed | failed | dnc
    attempt_count: int = 0
    next_attempt_at: Optional[int]
    last_call_uuid: Optional[str]       # joins into existing TalkoCDR.call_uuid

    class CollectionName:
        LEAD = "lead"
```

No separate `CallAttempt` collection — `TalkoCDR` already carries `campaign_id`, `lead_id`,
`disposition`, `llm_analysis`; join via `Lead.last_call_uuid`.

**Indexes**
- `{campaign_id: 1, status: 1, next_attempt_at: 1}` — loader query (due leads per campaign).
- `{partner_id: 1, status: 1}` — cross-campaign fairness and reporting.

## 7. AI Dispatch Engine

- **Redis sorted-set** per campaign (`campaign:{id}:due`, score = `next_attempt_at`) as the
  hot dispatch queue. A loader task pages due leads from Mongo into Redis in batches; Mongo
  is never polled on the hot path.
- **Dedicated Celery queue** `campaign_dialer_queue`, following the existing `task_routes`
  convention in `src/talko_celery/celery_config.py`, scaled independently of
  `call_operation_queue` / `did_management_queue` / `call_assets_queue` so campaign bursts
  don't starve TalkoCDR polling or DID-cooldown tasks.
- **Idempotent dispatch**: `SET NX EX` Redis lock per lead before dialing, preventing
  double-dial if two workers race on the same lead.
- **Concurrency cap**: atomic Redis counter per partner (`in_flight:{partner_id}`), bounded
  by `min(pacing_ratio, available AI_AGENT DIDs, per-partner global cap)`, checked before
  every dispatch.
- **Backpressure / circuit breaker**: exponential cooldown per partner if
  `/ai/v1/voice/sessions` or Tata Tele starts erroring — avoids burning telephony minutes
  on calls that can't bridge.
- **DID allocation**: round-robin over `TalkoPhoneNumberManagement` where `did_type=AI_AGENT`,
  honoring `cooldown_until` / `spam_count`.
- **Dial modes**:
  - *Progressive* (default): one lead → one call → wait for disposition → next lead. No
    abandon-rate risk, since the "agent" is the bot — matches how bot-driven dialers
    (Voice Genie-style) operate.
  - *Predictive* (opt-in, high-volume AI campaigns): bounded by DID/voice-session capacity,
    not agent count — a pure throughput knob, not an agent-utilization optimization.

## 8. Human Dispatch Path

Sync `Lead`s into a Tata Tele broadcast list via the existing `bulk_create_leads`
(chunked, respecting `duplicate_option`). Tata's platform owns agent pacing, ringing, and
abandon-rate compliance for this path. Status flows back through the same
`/call/webhook?type=dialer` → TalkoCDR (`is_incoming_from_broadcast`) → `Lead.status` sync —
no new webhook handling required.

## 9. API Surface (`/talko-service/v1/campaigns`) — consumed by makun-ai

| Endpoint | Purpose |
|---|---|
| `POST /campaigns` | Create campaign (call_type, agent_id or lead-list target, pacing, calling window, retry policy, budget) |
| `POST /campaigns/{id}/leads` | Bulk upload leads, chunked, dedup via `duplicate_option` |
| `POST /campaigns/{id}/start` | Start dispatch |
| `POST /campaigns/{id}/pause` | Pause dispatch |
| `POST /campaigns/{id}/stop` | Stop campaign |
| `GET /campaigns/{id}/status` | Live counters — served from Redis, not Mongo, for cheap polling |
| `GET /campaigns/{id}/report` | Connect rate, avg talk time, disposition breakdown, cost estimate |
| `GET /campaigns/{id}/leads?status=` | Paginated lead-level drill-down |

All endpoints scoped by `partner_id` from auth context, matching every existing
talko-service endpoint.

## 10. DID Management Strategy

- Reuse the existing `TalkoPhoneNumberManagement` model as-is — no schema change needed.
- AI campaigns draw exclusively from `did_type=AI_AGENT`; human campaigns from
  `did_type=NORMAL`.
- Allocation is round-robin with cooldown/spam awareness (`cooldown_until`, `spam_count`
  fields already present).
- DID pool size is a direct input to the concurrency ceiling (see §12) — provisioning more
  DIDs is the cheapest lever to raise AI-call throughput.

## 11. Scale & Robustness

- **No fixed cap on number of campaigns or partners** — creation and bulk lead ingestion
  (chunked Mongo inserts) are cheap and fast; the design intentionally decouples "how many
  campaigns/leads exist" from "how many calls execute concurrently right now."
- **Concurrency is bounded by five independently scalable layers**, in likely tightest-first
  order:
  1. Tata Tele concurrent channel limit (commercial trunk contract — confirm with Tata
     account; not present in either codebase).
  2. `AI_AGENT` DID pool size.
  3. makun-ai voice worker capacity (LiveKit agent processes; `src/components/voice/worker.py`
     uses standard horizontal-worker config — `num_idle_processes=1`, `load_threshold=0.99`
     — scales by adding worker nodes).
  4. Celery dispatch worker throughput (cheapest layer — dispatch itself is a lock + one
     HTTP call).
  5. Mongo/Redis throughput (not expected to bottleneck at these volumes given the indexed
     query design).
- **Multi-partner fairness**: all campaigns draw from one shared concurrency budget; the
  per-partner Redis counter ensures no single partner's campaign starves others. Each
  partner's slice is a config knob, not a code change.
- **Horizontal scaling path**: add DIDs, add voice worker nodes, add Celery workers to
  `campaign_dialer_queue`, or upgrade the Tata trunk — no architectural rewrite required to
  go from POC-scale to production volume.
- **Idempotency**: per-lead Redis lock plus `task_acks_late=True` (already the talko-service
  Celery convention) means a crashed worker mid-dispatch cannot double-dial.

## 12. Cost Governance

- `max_call_duration_seconds` enforced on the LiveKit session — hard cap on a runaway call.
- Daily budget cap per campaign/partner, checked against the same Redis counter used for
  concurrency.
- Reuse makun-ai's existing greeting-audio cache (`skip_greeting_audio`) instead of
  regenerating TTS per call.
- Early-hangup on voicemail/AMD if Tata exposes the signal in `call_actions`/
  `hangup_cause` — **open item, needs confirmation before Phase 2** (see §15).

## 13. Compliance & Safety

- DND/DNC check before dispatch (required for Tata Tele numbers in India).
- Calling-hour windows enforced per campaign timezone.
- Abandon-rate compliance owned by Tata Tele for the human path; not applicable to AI
  progressive mode (no abandon risk when the "agent" is the bot).

## 14. Observability

- Per-campaign metrics: dispatch rate, connect rate, error rate, cost burn — all derivable
  from existing TalkoCDR fields plus the new Redis counters, no new observability stack needed.
- Alerts: DID-pool exhaustion, circuit-breaker trips, budget-cap breaches.

## 15. Open Items to Resolve Before/During Phase 0–1

1. Confirm whether Tata Tele's webhook payload exposes an AMD/voicemail signal — determines
   whether early-hangup cost savings are available at launch or need to wait for Phase 2.
2. Confirm lead ingestion source(s) for real campaigns (CSV upload / CRM sync / API push) —
   affects the upload endpoint's validation and mapping logic.
3. Confirm real per-partner concurrency/budget defaults — needed to size Redis counters and
   DID pool provisioning correctly.
4. Confirm actual Tata Tele concurrent channel limit from the account/contract — likely the
   tightest real-world ceiling on concurrent AI calls.

## 16. Phased POC Roadmap

**Phase 0 — Walking Skeleton**
- `Campaign` / `Lead` Mongo collections.
- Single-worker progressive AI dispatch calling the existing `/call` API directly (no Redis
  queue yet — direct Mongo query is fine at this scale).
- Human path: direct pass-through to Tata's existing lead-list API.
- Exit criteria: for one campaign, the full loop works — lead → call → AI conversation →
  TalkoCDR → lead status update.

**Phase 1 — Production Dispatch Mechanics**
- Redis sorted-set dispatch queue, per-lead locking, per-partner concurrency cap.
- Retry/backoff on no-answer/busy, DND/calling-window checks.
- Full `/campaigns/*` API surface available for makun-ai integration.

**Phase 2 — Cost & Reporting**
- Cost/budget caps, circuit breaker on makun-ai/Tata error rates.
- Reporting rollups, live Redis-backed status endpoint.

**Phase 3 — Scale & Predictive**
- Predictive dial mode for AI campaigns.
- Horizontal worker scale-testing at target volume.
- Revisit whether human-agent campaigns ever need custom pacing beyond Tata's own dialer.

## 17. Explicit Non-Duplication Notes

To avoid rebuilding what already exists, this POC must reuse, not reimplement:
- Call placement: `POST /talko-service/v1/call` (`enable_ai_bridge`).
- AI voice session bridging: `POST /ai/v1/voice/sessions` (makun-ai).
- TalkoCDR ingestion and disposition capture: existing `/call/webhook?type=dialer` handler.
- Human-agent predictive dialing: Tata Tele's native broadcast list feature via the
  existing `dialer` module.
- DID pool model and cooldown/spam logic: existing `TalkoPhoneNumberManagement`.
- Celery queue/task-routing conventions: existing `src/talko_celery/celery_config.py`
  pattern.
