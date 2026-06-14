# PRD — SaaS Pivot v1: Agency Multi-Tenant Platform

**Status:** Locked (CEO review, SELECTIVE EXPANSION mode)
**Date:** 2026-06-12
**Owner:** Arman
**Mode:** Single-tenant internal tool → multi-tenant SaaS

---

## 1. Strategy (locked)

**Goal:** ~$1M ARR per-seat SaaS = ~40–80 paying agencies.

**Wedge:** Staffing / outsourcing agencies. Their product *is* placements; time-to-first-qualified-shortlist is literally revenue. In-house ATSs (Greenhouse, Ashby, Lever) are built for companies hiring for themselves, not agencies juggling many reqs across many clients. Underserved, acute pain, pays per seat.

**Beachhead:** CIS / Armenian agencies first — uncontested localization moat (Armenian + Russian ES analyzers, local-hire scoring, Armenia 2015 data-protection awareness already in backlog). Incumbents will never build this. Then expand to US/EU agencies on the **throughput** story, not the generic-AI story.

**North-star metric:** time-to-first-qualified-shortlist ↓ and placements/recruiter/month ↑. Scoring accuracy is a means, not the metric.

**Top failure modes (inversion):**
1. Cross-tenant data leak (company-ending) — mitigated by tenancy Approach A + RLS.
2. Day-1 cold-start emptiness → churn — mitigated by bulk ingest + proactive background scoring.
3. Recruiter distrust of AI score → ignored product — mitigated by calibration flag.

---

## 2. Packaging (locked)

- **Pricing:** per recruiter seat / month ($50–150 range, exact TBD from design-partner conversations).
- **Billing:** **manual invoicing** for first 1–3 design partners. No Stripe in v1 — don't build billing infra before price is validated. Stripe deferred.
- Build only the seat data model + seat limits in v1.

---

## 3. v1 Scope (the locked baseline + accepted cherry-picks)

| # | Item | Source | Effort (human / CC) |
|---|------|--------|---------------------|
| 1 | **Multi-tenancy foundation** — Approach A | baseline | L / few sessions |
| 2 | **Self-serve signup → org provisioning** | baseline | M / ~1 session |
| 3 | **Bulk ingest → ranked shortlist** (hero) | baseline | M / ~1 session |
| 4 | Bulk ingest progress + partial-failure UX | cherry-pick | S / ~20min |
| 5 | Proactive background scoring (kills cold-start) | TODO-001 | S / ~30min |
| 6 | Score calibration / "feels off" flag | TODO-004 | S / ~20min |
| 7 | `client` tag field on jobs | cherry-pick | S / ~10min |
| 8 | Per-seat data model + seat limits (no Stripe) | packaging | S / ~20min |

### Tenancy decision (Approach A — one-way door, locked)
Shared schema + `org_id` on every tenant-scoped table + Postgres **Row-Level Security** as the leak safety net.

- `org_id` set per-request from JWT inside the `get_db` dependency → every session scoped by construction.
- RLS policy keyed on `current_setting('app.org_id')` — catches any query a developer forgets to scope. Defense-in-depth on the catastrophic failure.
- **ES:** single `candidates` index, mandatory `org_id` filter term on every query.
- **pgvector:** `WHERE org_id = ?` on every similarity query.
- **Backfill migration:** existing 50 candidates / 9 jobs assigned to a seed org, or app breaks on first scoped query. Required, not optional.
- Reference/config tables (rubric config) stay global; users belong to exactly one org.

---

## 4. NOT in scope (explicitly deferred)

| Deferred | Why |
|----------|-----|
| Stripe / self-serve checkout | Validate price manually first |
| Full client-management module (clients as entities, per-client analytics, contacts) | Single `client` field covers v1; build module when a partner asks |
| Email / inbox resume ingestion ("forward to address") | Strong expansion, not v1-critical |
| Schema-per-tenant / DB-per-tenant | Premature isolation; Approach A right-sized for 40–80 tenants |
| US/EU GTM | Sequenced after CIS proof + logos |
| GDPR Art. 22 reasoning-access audit (TODO-005) | P1 compliance, fast-follow once multi-tenant; needed before processing real client PII at scale |

---

## 5. What already exists (reuse map)

- Scoring engine (`llm/rubric.py` hybrid) — reuse as-is.
- Dual search (ES + pgvector) — reuse, add `org_id` scoping.
- Localization moat (Armenian/Russian analyzers, local-hire) — the wedge, reuse.
- GDPR module + audit middleware — extend per-tenant.
- `CandidateJobScore` (candidates ←→ many jobs) — already models the agency shared-pool-scored-against-many-reqs pattern. Key discovery: agency fit needs no hierarchy rebuild.
- Multi-tenancy, billing, bulk-ingest path — net new.

Reusing ~70% of the engine. Pivot = foundation layer + 2 features, not a rewrite.

---

## 6. Architecture (target)

```
                       ┌─────────────────────────────────────────┐
                       │  Agency A (org_id=1)   Agency B (org_id=2)│
                       └─────────────────────────────────────────┘
                                        │ JWT carries org_id
                                        ▼
         ┌──────────────────────────────────────────────────────────┐
         │ FastAPI  get_db dependency:                               │
         │   SET app.org_id = <jwt.org_id>   (per request)           │
         └──────────────────────────────────────────────────────────┘
            │                    │                      │
            ▼                    ▼                      ▼
   ┌─────────────────┐  ┌─────────────────┐   ┌────────────────────┐
   │ Postgres        │  │ Elasticsearch   │   │ pgvector           │
   │ shared schema   │  │ single index    │   │ similarity         │
   │ + RLS on org_id │  │ filter: org_id  │   │ WHERE org_id = ?   │
   │ (safety net)    │  │ (mandatory)     │   │                    │
   └─────────────────┘  └─────────────────┘   └────────────────────┘

   Leak defense: app-layer scoping (primary) + RLS (catches forgotten filter)
```

### Bulk ingest data flow (hero feature, all 4 paths)
```
 UPLOAD N files ─▶ VALIDATE ─▶ PARSE ─▶ EMBED+INDEX ─▶ SCORE ─▶ RANKED LIST
       │             │           │          │            │          │
       ▼             ▼           ▼          ▼            ▼          ▼
   [0 files?]   [bad magic/   [corrupt   [ES down?    [LLM        [empty pool?
    empty-      >10MB?        PDF?       → PG          malformed/   → empty-state
    state msg]   reject loud]  skip+     fallback]     refusal?     "drop resumes"]
                              report]                  → mark row   CTA]
                                                       failed,
                                                       don't drop]
   PARTIAL: 2000 in, 30 fail → show which + why, never silent drop (item #4)
```

---

## 7. Implementation tasks

- [ ] **T1 (P1)** — db — `org_id` migration: add column to all tenant-scoped tables + backfill seed org. Files: `alembic/versions/`, `app/*/models.py`. Verify: `alembic upgrade head` on copy of current data, no orphan rows.
- [ ] **T2 (P1)** — auth/db — set `app.org_id` from JWT in `get_db`; add RLS policies. Files: `app/database.py`, `app/auth.py`, new migration. Verify: cross-tenant query returns 0 rows in a 2-org test.
- [ ] **T3 (P1)** — search — `org_id` filter on every ES query + pgvector similarity. Files: `app/search/service.py`, `app/candidates/`. Verify: org-A search never returns org-B candidate.
- [ ] **T4 (P1)** — auth — self-serve signup → create org + first admin atomically. Files: `app/auth.py`, `app/auth_sso.py`, frontend `Register.tsx`. Verify: new signup lands in isolated empty org.
- [ ] **T5 (P1)** — ingest — bulk upload endpoint + ranked-list response. Files: new `app/ingest/`, `frontend/src/pages/`. Verify: drop 50 resumes → ranked list out.
- [ ] **T6 (P2)** — ingest — progress + partial-failure UX (which failed, why). Verify: 1 corrupt file in 10 → 9 succeed, 1 reported.
- [ ] **T7 (P2)** — scoring — proactive background scoring on new application. Files: `app/applications/service.py` post-create hook → Celery. Verify: new app appears scored in leaderboard without manual trigger.
- [ ] **T8 (P2)** — feedback — `score_flags` table + flag endpoint + UI button. Files: new migration, `app/jobs/router.py`, leaderboard UI. Verify: flag persists, surfaces to admin.
- [ ] **T9 (P2)** — jobs — optional `client` field. Files: `app/jobs/models.py` + migration + filter. Verify: tag + filter by client.
- [ ] **T10 (P2)** — billing — seat data model + seat-limit enforcement (no Stripe). Files: `app/orgs/`, signup flow. Verify: org over seat limit blocks new user.

**P1 (T1–T5) blocks design-partner ship. T2/T3 are the cross-tenant-leak gate — most-tested code in the repo.**

---

## 8. Open questions (for design-partner conversations, not blocking build)

- Exact seat price ($50 vs $150) — learn from first 3 agency calls.
- Do CIS agencies need Russian-language *UI* (not just search analyzers) at launch?
- Resume volume per agency (sizes bulk-ingest + worker capacity).
