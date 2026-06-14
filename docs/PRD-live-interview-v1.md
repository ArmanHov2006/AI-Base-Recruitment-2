# PRD — AI Interview v1: Async Recorded Interview + AI Scoring

**Status:** Ready to build (all forks resolved)
**Date:** 2026-06-14
**Owner:** Arman
**Mode:** New scored pipeline stage (post-shortlist)
**Depends on:** PRD-saas-pivot-v1 T1–T5 (multi-tenancy) shipped first

---

## 1. Decision summary (locked via review)

| Fork | Decision | Why |
|------|----------|-----|
| Delivery mode | **Async one-way recorded** | No WebRTC/TURN/signaling. Reuses MinIO + Celery + SSE. No scheduling. ~1–2 sessions vs 4–6 for live video. |
| Eye/gaze tracking | **Dropped entirely** | EU AI Act Annex III high-risk / Art. 5 prohibition on emotion+biometric in recruitment; BIPA exposure; weak science; bias liability. SaaS pivot targets EU GTM after CIS — gaze kills that path. Loses no real predictive signal. |
| Speech-to-text | **Local faster-whisper in worker** | Keeps PII in-house (PRD-next-stage S-2 guardrail). No per-minute cost. Mirrors `LLM_PROVIDER` swap pattern. |
| Timing | **After tenancy P1 (T1–T5)** | Interview tables need `org_id` from birth — avoids T1 retrofit migration pain. Interview is a post-shortlist step; needs org scoping anyway. |

**Non-goals (v1):** live synchronous video, human-in-call AI co-pilot, any biometric/gaze/emotion signal, automated reject decision (AI suggests, human decides — Art. 22 posture), **re-scoring** (each session scored once; rubric changes do not retro-apply to old recordings).

**Retention (decided):** raw answer video hard-deleted from MinIO **30 days after `scored`** (recruiter may delete earlier; absolute cap 90 days). Transcript + `CandidateEvaluation` scores retained as the durable evaluation record (text), erasable via existing `app/gdpr/` candidate-erasure path. Enforced by a Celery-beat purge task.

---

## 2. What it does

1. Recruiter opens a shortlisted application → **"Start AI interview"**.
2. System generates role-tailored questions (reuse `LLMClient.suggest_interview_questions`).
3. Recruiter shares a **tokened candidate link** (no candidate login).
4. Candidate: consent gate → sees questions one at a time → records each answer in-browser (`MediaRecorder`) → uploads to MinIO via presigned PUT → submits.
5. Worker: ffmpeg normalize → faster-whisper STT per answer → assemble transcript → LLM scores into the existing **`CandidateEvaluation`** model with `stage="ai_interview"`.
6. Recruiter reviews: per-answer recordings, transcripts, AI dimension scores, `ai_suggested_rating`, and writes the human verdict (existing evaluations UI).

**Question set:** 10–20 **technical** questions per session, role-tailored (skills + seniority drive depth). Recruiter can trim/edit the generated set before sending.

AI scores **content only**: technical accuracy, answer relevance, problem structure/clarity, communication. Optional later: audio prosody (pace, filler density) — non-biometric.

**Camera required** (candidate must record video, not audio-only). Note: camera is required to *capture* the answer — the video is **never scored for gaze/face/emotion** (that stays prohibited per §1). Required-camera is an integrity/identity measure, disclosed in the consent gate. Accessibility carve-out: candidates needing accommodation contact the recruiter (manual path), don't hard-block silently.

---

## 3. Reuse map (≈80% existing)

- `app/llm/base.py::suggest_interview_questions` — question generation, already in interface.
- `app/evaluations/models.py::CandidateEvaluation` — score sink. New `stage="ai_interview"`; reuse `technical_score`, `communication_score`, `domain_score`, `english_score`, `ai_suggested_rating`, `feedback`. **No new score table.**
- `app/applications/models.py::JobApplication` — interview hangs off the application.
- `app/storage/` — presigned PUT (UUID keys), magic-byte validator (extend for video mime + larger cap).
- `app/worker/` — new Celery task alongside `scoring.py`.
- `app/ai/router.py` SSE pattern — optional live "scoring in progress" stream to recruiter.
- `app/notifications/` — notify recruiter on `scored`.

---

## 4. Net-new

### 4.1 Data model (all carry `org_id` + RLS per tenancy Approach A)

`interview_sessions`
- `id`, `org_id`, `application_id` FK, `candidate_id`, `job_id`
- `status`: `created → questions_ready → recording → submitted → transcribing → scored → failed`
- `questions` JSONB (ordered list)
- `access_token` (signed, single session, `expires_at`)
- `consent_accepted_at`, `consent_text_version`
- `created_by`, `created_at`, `updated_at`, `deleted_at`

`interview_answers`
- `id`, `org_id`, `session_id` FK, `question_index`, `question_text`
- `recording_file_id` (MinIO key, nullable after purge), `duration_seconds`, `mime`
- `transcript` Text, `transcript_lang`
- `video_purged_at` (set when raw video deleted; transcript survives)
- `created_at`

`interview_sessions.scored_at` drives the 30-day video purge clock.

Aggregate result → `CandidateEvaluation(stage="ai_interview", ...)`. Per-answer transcripts stay in `interview_answers`.

### 4.2 Endpoints (`app/interviews/`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/interviews` | recruiter (`require_write`) | create session + generate questions |
| GET | `/interviews/{id}` | recruiter | status + results |
| GET | `/interviews/public/{token}` | token only | questions + consent text |
| POST | `/interviews/public/{token}/consent` | token | record consent |
| POST | `/interviews/public/{token}/answers/{idx}/upload-url` | token | presigned PUT |
| POST | `/interviews/public/{token}/submit` | token | finalize → enqueue worker |

### 4.3 Worker task (`app/worker/interview.py`)
`transcribe_and_score(session_id)`:
1. For each answer: download from MinIO → ffmpeg normalize to 16k mono wav → faster-whisper → store transcript.
2. Assemble Q/A transcript → LLM score (extend `LLMClient` with `score_interview()` or reuse `score_candidate` shape).
3. Upsert `CandidateEvaluation(stage="ai_interview")`. Set session `scored`. Notify recruiter.
4. Any answer fails → mark answer failed, **score the rest, never drop the session** (PRD-saas partial-failure principle).

### 4.4 Frontend
- Recruiter: "Start AI interview" button on application/pipeline → session created → copyable candidate link → results render in existing `EvaluationsSection`.
- Candidate: new public route `pages/InterviewSession.tsx` — consent → per-question recorder (`MediaRecorder`) → upload progress → submit confirmation. No login, no app shell.

### 4.5 New deps
- `faster-whisper` (+ model download in worker image), `ffmpeg` in worker Dockerfile.

---

## 5. Edge cases / risks

- **Upload size:** 10–20 technical Q × ~2 min video = a large total payload, but uploaded **per-answer** not as one blob. Per-answer video cap (e.g. 150 MB); chunked/resumable upload if single answers run long. Validate video magic bytes (webm/mp4). 10 MB global storage cap stays for other modules — video path gets its own limit.
- **Camera required:** hard-require `getUserMedia({video:true})`; block recording start if denied, show clear "camera needed" state + recruiter-contact accommodation path (no silent fail).
- **Browser codec variance:** Chrome `webm/vp8`, Safari `mp4` — always transcode via ffmpeg before whisper.
- **Token security:** signed token, expiry, per-token rate limit (`app/limiter.py`), single active session; revoke on use.
- **Consent record:** store `consent_accepted_at` + text version — legal requirement, not optional.
- **PII guardrail (S-2):** STT local keeps audio in-house. If `LLM_PROVIDER=openai`, transcript = real PII → must respect `ALLOW_REAL_PII` gate before sending. Default scoring path = Ollama.
- **org_id scoping:** every new table + ES/pgvector touch carries `org_id`; RLS policy; cross-tenant test (token from org A cannot read org B session).
- **Anti-cheat (no gaze):** per-answer time limit, single attempt per question, randomize order. Optional advisory **non-scored** tab-blur flag, consented, never feeds rating.
- **Whisper cost:** CPU works (base/small); GPU worker optional. Async so latency is fine.

---

## 6. Implementation tasks

- [ ] **I1 (P1)** db — `interview_sessions` + `interview_answers` migrations, `org_id` + RLS. Verify: cross-tenant read blocked.
- [ ] **I2 (P1)** api — `app/interviews/` router + schemas + service; question gen on create. Verify: create returns N questions + token.
- [ ] **I3 (P1)** storage — video mime validation + larger cap + presigned PUT for answers. Verify: 100 MB webm uploads, txt rejected.
- [ ] **I4 (P1)** worker — `interview.py` transcribe+score; ffmpeg + faster-whisper in worker image. Verify: 3 answers → transcripts → `CandidateEvaluation(ai_interview)`.
- [ ] **I5 (P1)** llm — `score_interview()` (or reuse `score_candidate`) returning dimension scores + `ai_suggested_rating` + feedback. Verify: deterministic shape, refusal-safe.
- [ ] **I6 (P1)** fe-candidate — public `InterviewSession.tsx`: consent → MediaRecorder → upload → submit. Verify: full record→submit on Chrome + Safari.
- [ ] **I7 (P2)** fe-recruiter — start button + link share + results in `EvaluationsSection`. Verify: recruiter sees scores + plays recordings.
- [ ] **I8 (P2)** partial-failure UX — 1 corrupt answer of 3 → 2 scored, 1 flagged, session not dropped.
- [ ] **I9 (P2)** notifications — recruiter alert on `scored`.
- [ ] **I10 (P1)** retention — Celery-beat purge task: delete MinIO video where `scored_at < now-30d` (or recruiter-initiated), set `video_purged_at`, keep transcript. Absolute 90-day cap. Verify: aged session → video gone from MinIO, transcript + score intact. Wire candidate erasure (`app/gdpr/`) to also drop transcripts.

**P1 (I1–I6, I10) = working MVP. I2/I3/public-token path = the untrusted surface — most-tested. I10 is P1, not P2 — retention is a compliance gate before real candidates.**

---

## 7. Decisions + remaining open questions

**Decided (2026-06-14):**
- Question count: **10–20**, **technical** focus, role-tailored.
- Per-answer time limit: **2 min** default (tunable).
- Camera: **required** (no audio-only fallback; accommodation = manual recruiter path).
- Question language: **role language**.
- Recruiter override: yes — recruiter can trim/edit generated questions before sending.

- Re-score: **NO.** Each session scored once; rubric changes do not retro-apply.
- Retention: **raw video purged 30 days after `scored`** (recruiter early-delete; 90-day hard cap); transcript + scores kept, erasable via `gdpr/`. Task I10.

**All forks resolved — PRD is execution-ready.**

---

## 8. How to start (build order)

1. **Gate:** confirm PRD-saas-pivot T1–T5 (`org_id` + RLS) is merged. Interview tables must be born tenant-scoped.
2. **I1** migration (2 tables, `org_id`, RLS) → **I5** `score_interview()` in `LLMClient` → **I2** router/service + question gen.
3. **I3** storage (video mime + cap + presigned PUT) → **I4** worker (ffmpeg + faster-whisper + score) → **I6** candidate recorder page.
4. **I10** purge task (compliance gate) → **I7** recruiter UI → **I8** partial-failure → **I9** notify.
5. Test order priority: public-token path (I2/I3), cross-tenant isolation (I1), purge correctness (I10).

Suggest running this through `/plan-eng-review` once before I1 — tenancy coupling + the untrusted public surface are worth one architecture pass.

---

## 9. Eng-review outcome (2026-06-14)

`/plan-eng-review` run. Scope **reduced** to a thin slice, then split into two parallel mini-slices. Decisions below override conflicting parts of §3–§8.

### 9.1 Scope decision
Build a **thin slice first**, as **two parallel mini-slices** (TENSION-2):

```
Lane B (BE)  recruiter test-clip → ffmpeg → whisper(small.en)
             → LLM tier-classify → rubric.py → CandidateEvaluation(ai_interview)
Lane A (FE)  MediaRecorder record 1 answer (Chrome/Safari/mobile)
             → presigned POST → MinIO
                         │
                  converge → wire Lane A upload key into Lane B worker
```

Lane B de-risks scoring quality (feature's value engine). Lane A de-risks the untrusted record+upload surface (the real unknown per outside voice). Independent until integration → run in separate worktrees.

### 9.2 Locked decisions (correct the original PRD)

| # | Decision | Supersedes |
|---|----------|-----------|
| A1 | `CandidateEvaluation` gets `interview_session_id` FK + **partial unique index** `(candidate_id, job_id, stage) WHERE stage='ai_interview' AND deleted_at IS NULL`. Upsert keys on this, NOT `evaluator_id` (NULL for AI → NULLs distinct → no dedupe). | §4.1 "upsert" |
| A2 | Whisper **`small.en`, baked into worker image at build, pinned HF revision, `WHISPER_MODEL` env-swappable** (flips to multilingual `small` for hy/ru later). English-first. Non-root worker. No runtime download. | §4.5 "model download" |
| A3 | Keep `interview.*` namespace **(accepted risk)** despite existing `interview_scheduled_at` fields + `interview.send_reminders` beat task. | — |
| A4 | `score_interview()` = LLM **tier-classify** per dimension → `rubric.py` `TIER_POINTS`×`INTERVIEW_WEIGHTS` computes the number. Deterministic, unit-testable. Weights in `rubric.py`, never in prompt. | §4.3 step 2 |
| C1 | Separate `validate_video_upload()` fn **(accepted DRY debt)** — but share size + magic-byte primitives with the resume validator so they can't drift. | §3 validator |
| C2 | Any pipeline step error → `status='failed'` + persist **`failure_reason`** + recruiter-visible + re-enqueue action. Bounded Celery autoretry (3×) for transient (download/timeout) first. No row stuck in `transcribing`. | §4.3 step 4 |
| P1 | Worker **streams MinIO video to a temp file** (`fget_object` → `NamedTemporaryFile` → unlink), never buffers the blob in RAM. | §4.3 step 1 |
| T-1 | Upload+validate (full feature): **presigned POST policy** (`content-length-range`, exact UUID key, short TTL, single-use) → worker **magic-byte gate-0** (app never sees bytes, so pre-upload validation is impossible) → **non-root + timeboxed + rlimit ffmpeg** on validated file only. ffmpeg-on-untrusted-media is the real attack surface. Slice dodges via recruiter proxied test clip. | §3 "presigned PUT" (does not exist — GET-only today), §4.2 upload-url, §5 upload |
| T-3 | **Video stays required** (integrity/identity deterrent + recruiter human-review). Accept codec/size/consent cost. | — (reaffirms §1) |

### 9.3 What already exists (reuse — corrected to ~60%, not ~80%)
- `app/llm/base.py::suggest_interview_questions` — question gen interface. **Reuse.**
- `app/evaluations/models.py::CandidateEvaluation` — score sink. **Reuse + A1 schema change.**
- `app/llm/rubric.py` — deterministic tier→points engine. **Reuse + add `INTERVIEW_WEIGHTS`/interview tiers (A4).**
- `app/storage/` — presigned **GET** + server-proxied upload + ext/magic validator. **Partial:** presigned **PUT/POST does NOT exist** (net-new, T-1); validator extended (C1).
- `app/worker/` Celery + **beat already configured** (`celery_app.py`) — purge task slots in cleanly later. **Reuse.**
- `app/gdpr/router.py` — already snapshots evaluations on export. **Reuse + wire interview transcript erasure later.**
- `app/notifications/`, `app/ai/router.py` SSE — **reuse when layering.**

### 9.4 NOT in scope (deferred, with rationale)
- **Public token link + consent gate** (I2 public endpoints) — deferred to post-slice; Lane A proves the record/upload mechanics first.
- **N questions (10–20)** — slice does one; multi-Q after both lanes converge.
- **I10 retention purge (30/90-day)** — compliance gate **before real candidates**, not before pipeline proof. P1 when going live, not in slice.
- **I8 partial-failure (score rest, drop none)** — slice is single-answer; multi-answer resilience layers later.
- **org_id + RLS** — blocked on tenancy T1–T5 (not shipped; `org_id` absent everywhere). Slice can run single-tenant and retrofit; full feature gated.
- **SSE live "scoring in progress" stream** — already optional in §3; dropped from v1.
- **Audio prosody, anti-cheat tab-blur** — already deferred in PRD.
- **Golden-set scoring eval** — captured in `TODOS.md`; gate before scoring real candidates.

### 9.5 Failure modes (new codepaths)

| Codepath | Realistic failure | Test? | Error handling? | User sees? |
|----------|-------------------|-------|-----------------|------------|
| worker download | MinIO unreachable / key missing | gap → add | C2 autoretry 3× then failed | reason shown ✓ |
| ffmpeg transcode | malformed/hostile media (CVE surface), timeout | gap → add | C2 failed + reason; **harden: non-root+timeout+rlimit** | reason shown ✓ |
| whisper | empty transcript (silence/noise) | gap → add | C2 failed + reason | reason shown ✓ |
| LLM tier-classify | refusal / unparseable output | gap → add | C2 failed + reason; refusal-safe parse | reason shown ✓ |
| CandidateEvaluation upsert | retry double-write | **CRITICAL test** (proves A1) | partial unique index | n/a |
| presigned upload (layering) | oversized/wrong-type client blob | gap → add | POST policy + worker gate-0 | reject → failed |

No silent-failure critical gaps remain — C2 makes every path loud with a reason. The ffmpeg-on-untrusted step is the highest-risk and gets explicit hardening (T-1).

### 9.6 Test plan (slice)
Coverage starts 0% (all net-new). Required before slice merges:
- `rubric.py` interview scoring — **pure unit, 100%**: fixed tiers in → exact weighted score out; missing-dim guard; 0–100 clamp.
- Worker happy path — clip → transcript → `CandidateEvaluation(ai_interview)` written.
- **Upsert idempotency — CRITICAL** — re-run worker → exactly one `ai_interview` row (proves A1 partial unique index).
- Worker failure paths — ffmpeg fail / empty transcript / LLM refusal → `status='failed'` + `failure_reason` set.
- `validate_video_upload` — webm + mp4 magic accepted; txt rejected; over-cap rejected.
- Lane A integration `[→E2E]` — real record→upload→stored on Chrome + Safari.
- LLM tier quality `[→EVAL]` — **deferred** to `TODOS.md` (golden set).

### 9.7 Parallelization

| Step | Modules | Depends on |
|------|---------|-----------|
| Lane B: worker + llm + rubric + CE migration | `app/worker/`, `app/llm/`, `app/evaluations/`, `alembic/` | — |
| Lane A: MediaRecorder + presigned + validator | `frontend/`, `app/storage/` | — |
| Integration: wire upload key → worker; recruiter results | `app/interviews/`, `frontend/` | Lane A + Lane B |

**Execution:** Launch Lane A + Lane B in parallel worktrees (no shared modules). Merge both → Integration. **Conflict flag:** both lanes eventually touch `app/interviews/` at integration — keep new module skeleton on one lane, import from the other to avoid a merge collision.

### 9.8 Implementation Tasks
Synthesized from review findings. P1 = slice-blocking, P2 = converge/layer.

- [ ] **T0 (P1, human: ~varies / CC: —)** — foundation — confirm tenancy T1–T5 (`org_id`+RLS) status; slice runs single-tenant, full feature gated.
  - Surfaced by: Architecture / outside-voice #3 — `org_id` absent in `app/`.
  - Verify: explicit go/no-go on single-tenant slice.
- [ ] **T1 (P1, human: ~20min / CC: ~5min)** — evaluations — add `interview_session_id` FK + partial unique index to `CandidateEvaluation`.
  - Surfaced by: A1 — NULL `evaluator_id` breaks dedupe.
  - Files: `app/evaluations/models.py`, `alembic/versions/`. Verify: retry worker → one row.
- [ ] **T2 (P1, human: ~3h / CC: ~30min)** — llm/rubric — `score_interview()` tier-classify + `INTERVIEW_WEIGHTS` deterministic compute.
  - Surfaced by: A4. Files: `app/llm/`, `app/llm/rubric.py`. Verify: fixed tiers → exact score, no LLM in unit test.
- [ ] **T3 (P1, human: ~2h / CC: ~25min)** — worker (Lane B) — `interview.py`: stream→temp→ffmpeg(non-root+timeout)→whisper(small.en baked/pinned)→transcript→score→upsert.
  - Surfaced by: A2, P1, C2. Files: `app/worker/interview.py`, worker `Dockerfile`. Verify: clip → `CandidateEvaluation(ai_interview)`.
- [ ] **T4 (P1, human: ~1.5h / CC: ~20min)** — worker — failure handling: `status='failed'` + `failure_reason` + bounded transient autoretry + re-enqueue.
  - Surfaced by: C2. Files: `app/worker/interview.py`, session model. Verify: each failure path → failed + reason, no stuck `transcribing`.
- [ ] **T5 (P1, human: ~2h / CC: ~25min)** — tests (Lane B) — rubric pure unit + **CRITICAL upsert-idempotency** + worker failure paths.
  - Surfaced by: Test review. Files: `tests/`. Verify: `uv run pytest` green; idempotency proven.
- [ ] **T6 (P1, human: ~1d / CC: ~1h)** — fe (Lane A) — `InterviewSession.tsx` MediaRecorder: record 1 answer, Chrome+Safari+mobile.
  - Surfaced by: outside-voice #1 / TENSION-2. Files: `frontend/src/pages/`. Verify: record→blob on 3 browsers.
- [ ] **T7 (P1, human: ~2h / CC: ~25min)** — storage (Lane A) — presigned POST policy (content-length-range, UUID key, TTL, single-use).
  - Surfaced by: T-1. Files: `app/storage/client.py`, `router.py`. Verify: oversized/wrong-key rejected by MinIO.
- [ ] **T8 (P1, human: ~1h / CC: ~15min)** — storage/worker — `validate_video_upload()` magic-byte gate-0 (webm/mp4), shared primitives with resume validator.
  - Surfaced by: C1, T-1. Files: `app/storage/validator.py`. Verify: webm/mp4 pass, txt + over-cap reject.
- [ ] **T9 (P2, human: ~3h / CC: ~30min)** — integration — wire Lane A upload key → Lane B worker; recruiter results in `EvaluationsSection`.
  - Surfaced by: convergence. Files: `app/interviews/`, `frontend/`. Verify: end-to-end record→score→recruiter view.

## 10. Design-review outcome (Lane A candidate UI, 2026-06-14)

`/plan-design-review` run on the candidate recorder flow. Initial design completeness **3/10 → 8/10**. Mockups skipped (OpenAI image-gen org-verification blocked); ASCII wireframes used. Classification: App UI / guided form-flow. Calibrated to DESIGN.md.

### 10.1 Information architecture (one job per screen)
```
PUBLIC RECORDER  (375px portrait primary, no app shell)
┌─────────────────────────────┐
│ [agency logo]  Question 1/1 │  orientation: who + progress
├─────────────────────────────┤
│ "<technical question>"      │  THE QUESTION (read first)
│ ┌─────────────────────────┐ │
│ │  live camera preview    │ │  self-view (2nd focus)
│ │     ● REC   1:42        │ │  rec dot + countdown
│ └─────────────────────────┘ │
│        (  ● Record  )        │  ONE primary control, ≥44px, #5b6af5
│ Only the hiring team sees   │  trust line (muted)
│ this.        ⓘ Need help?   │  accommodation path, always visible
└─────────────────────────────┘
```

### 10.2 Locked design decisions

| # | Decision | Notes / backend impact |
|---|----------|------------------------|
| D2 | **True single-take**, no re-record. Pre-record warning: "You'll have one take — start when ready." | matches §5 anti-cheat |
| D3 | **Server-enforced attempt lock at record-start.** Refresh → "Attempt already used" lock screen (client-bypass-proof). Same-blob upload **retry** allowed while tab open; refresh that loses the in-memory blob = attempt burned. `beforeunload` warns during upload. **Backend add:** `attempt_consumed_at` on `interview_answers` (or session) + a "mark attempt started" public endpoint. | net-new, not in §9 |
| D4 | **No-stakes ready-check screen before the lock:** live cam/mic preview, mic level meter, question shown, "I'm ready" consumes the attempt. Biggest completion-rate lever under single-take. | — |
| D5 | **Calmer public theme variant** — reuse DESIGN.md tokens (`#5b6af5`, Fira Sans) but more whitespace, larger type, softer surfaces, single accent, no stage-color noise. Distinct from the dense recruiter dashboard. | — |
| D6 | **Agency (tenant) white-label brand** on the public page — candidate sees the hiring agency, not the product. **Backend add:** `org.display_name` (+ logo later) on the public token payload. | net-new, ties to SaaS pivot |

### 10.3 Interaction states (recorder)
```
STATE               | CANDIDATE SEES
--------------------|------------------------------------------------
permission-prompt   | plain-language "we need your camera" + Allow
permission-denied   | calm explainer + visible "contact recruiter" (no dead end)
unsupported-browser | "use Chrome or Safari" + which work
ready-check (D4)    | live preview, mic meter, question, "I'm ready" (no lock yet)
recording           | rec dot + countdown 2:00, big Stop, aria-live announce
auto-stopped (2:00) | "Time's up" → goes to uploading
uploading           | progress %, "Don't close this tab", reassurance
upload-failed       | "Upload didn't finish" + Retry (same blob held)
attempt-used (D3)   | refresh after start → "Your attempt is recorded/used" lock
submitted           | confirmation + "what happens next" + "safe to close"
```

### 10.4 Responsive + accessibility
- 375px portrait is the **primary** target; preview fills width; controls in thumb-reach (bottom third); desktop centers ~480px column.
- Permission/error states never silent-fail; "Need help? contact recruiter" on every blocking screen.
- Touch targets ≥44px; rec state + timer via `aria-live`; question text ≥16px, contrast ≥4.5:1, zoomable; `prefers-reduced-motion` disables pulsing rec animation.

### 10.5 Design-derived tasks (append to §9 build set)
- [ ] **T10 (P1)** db/api — `attempt_consumed_at` field + "mark attempt started" public endpoint; refresh → attempt-used lock (D3). Verify: refresh after record-start cannot start a new take.
- [ ] **T11 (P1)** fe — ready-check screen before lock: cam/mic preview + mic meter + question (D4). Verify: attempt consumed only on "I'm ready".
- [ ] **T12 (P1)** fe — full recorder state machine per §10.3 incl. upload retry + `beforeunload` guard. Verify: each state renders; failed upload retries same blob.
- [ ] **T13 (P2)** fe/api — agency white-label: `org.display_name` on public token payload, rendered in header (D6). Verify: candidate sees agency brand.
- [ ] **T14 (P2)** fe — calmer public theme variant from DESIGN.md tokens (D5). Verify: matches tokens, distinct from dashboard.

### 10.6 NOT in scope (design)
- Live captions / transcript display to candidate during recording — deferred.
- Candidate-page i18n (consent + chrome + errors) — captured in `TODOS.md`.
- Agency logo upload UI — D6 ships name first, logo later.
- Multi-question progress UX (1-of-N stepper) — slice is single question.

### 10.7 What already exists (design)
- DESIGN.md tokens + Ant Design dark theme — reuse via the calmer variant (D5).
- No existing public page, consent gate, or MediaRecorder component — all net-new.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Outside Voice | (Claude subagent) | Independent 2nd opinion | 1 | ISSUES_FOUND | 5 raised, 3 actioned (T-1, two-lane slice, video reaffirmed) |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | SCOPE_REDUCED | 8 issues, 0 critical gaps, 0 unresolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | 3/10 → 8/10, 6 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

- **OUTSIDE VOICE:** Codex auth failed (401 — needs `codex login`); fell back to Claude subagent. Caught the presigned-PUT/validation contradiction (→ T-1) the eng review missed; flagged slice-ordering (→ two parallel mini-slices) and audio-vs-video (kept video).
- **CROSS-MODEL:** Eng + Outside agree on namespace concern (A3, overridden) and the unshipped-tenancy gate. Design review added the candidate-UI layer (D2–D6) and surfaced two backend adds the eng pass missed: attempt-lock field/endpoint (D3) and `org.display_name` on the token payload (D6).
- **UNRESOLVED:** 0.
- **VERDICT:** ENG + DESIGN CLEARED. Scope = two-lane thin slice. 8 eng decisions (§9) + 6 design decisions (§10) locked; 15 tasks total (T1–T14 + T0 gate); 2 TODOs captured. Tenancy T1–T5 is the one external gate for the full feature; slice runs single-tenant. Ready to implement.
