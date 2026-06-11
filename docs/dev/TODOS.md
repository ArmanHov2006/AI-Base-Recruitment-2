# TODOS

## Deferred from Score Memory + Leaderboard feature

### TODO-001: Proactive background scoring (Approach C)
**What:** When a new application arrives, auto-score that candidate in the background.
Leaderboard pre-populates without waiting for manual comparisons.
**Why:** Today the leaderboard starts empty for new jobs. Background scoring
removes the cold-start gap — recruiter opens job, sees ranked leaderboard immediately.
**Depends on:** Validated leaderboard UX with real recruiter feedback. Adds Celery or APScheduler.
**Where to start:** `app/applications/service.py` post-create hook → enqueue scoring task.

### TODO-002: Force re-score action for admins
**What:** "Re-score" button on leaderboard row. Bypasses cache, calls LLM fresh,
updates `candidate_job_scores`.
**Why:** Recruiter wants a second opinion even when nothing changed. No way to force
fresh score today without editing candidate/job data.
**Depends on:** Stable leaderboard UI.
**Where to start:** `DELETE /jobs/{job_id}/leaderboard/{candidate_id}/score` +
new "Re-score" button in `JobLeaderboard.tsx`.

---

## Deferred from Role Analytics feature

### TODO-003: Cross-role pipeline health dashboard (Approach B)
**What:** A new page showing all open roles as cards with pipeline health indicators
(Underfilled / On Track / Overfilled), colored by status. HR managers click to
drill into individual role analytics.
**Why:** HR managers need to see which roles are stuck without drilling into each role
individually. The office-hours session identified this as the secondary user need.
The infrastructure (per-role threshold + analytics-summary endpoint) is built in this
PR — the cross-role view aggregates across jobs.
**Depends on:** `feat/role-analytics` merging. Validate that per-role threshold concept
resonates with recruiters before building the overview.
**Where to start:** New `GET /analytics/role-health` endpoint returning all active
jobs with `{job_id, title, qualified_count, target, status}`. New `RoleHealthDashboard.tsx`
page rendering a grid of health cards.
**Effort:** M (human ~3d / CC ~30min)
**Priority:** P2

### TODO-005: GDPR/compliance audit for AI reasoning text display (P1)
**What:** Audit the display of `CandidateJobScore.reasoning` (LLM-generated candidate assessments)
for compliance with Armenia's Law on Personal Data Protection (2015) and GDPR Article 22
(automated decision-making). Specifically: role-restrict access to reasoning text (admin/HR manager
only?), add view audit logging to BusinessEvent when a recruiter reads a candidate's reasoning,
and document the legal basis for automated scoring in AI_Based_recruitment's data processing records.
**Why:** The reasoning field contains free-text AI assessments about individual candidates used
in hiring decisions. Bank HR tools are typically subject to employment law compliance review.
Absence of view logs for automated decision explanations could be a finding in a data audit.
**Depends on:** feat/role-analytics merging. Legal review by AI_Based_recruitment's DPO.
**Where to start:** `app/comparisons/schemas.py` LeaderboardEntry — add role-based field filtering.
`app/jobs/router.py` get_job_leaderboard — log `CANDIDATE_REASONING_VIEWED` business event.
**Effort:** M (human ~2d / CC ~15min for technical work, plus legal review timeline)
**Priority:** P1 (compliance risk)

### TODO-004: Recruiter feedback flags — score calibration loop
**What:** A "Score feels off" flag button on candidate rows in the analytics page.
Flags stored in a new `score_flags` table: `candidate_id, job_id, flagged_by, reason_text, created_at`.
Flags are surfaced to admins for future model calibration.
**Why:** Recruiter trust in AI scores is the core adoption risk for threshold-based
filtering. The feedback loop turns passive consumers into active validators and builds
data for score calibration over time.
**Depends on:** `feat/role-analytics` merging. Validate that recruiters actually use
the threshold before investing in calibration.
**Where to start:** New migration for `score_flags` table. New `POST /jobs/{id}/score-flags`
endpoint. "Flag" icon button on each row in the qualified candidates table.
**Effort:** M (human ~2d / CC ~20min)
**Priority:** P3
