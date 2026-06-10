# Design Review — AI Recruitment Frontend

Date: 2026-05-22  
Reviewer: /plan-design-review (gstack)  
Branch: main  
App type: APP UI (internal HR tool, Ardshinbank)  
Initial score: 5/10 → Final score: 7/10

---

## Decisions Made

### Information Architecture

**D2 — Contextual header title**  
Replace static "AI Recruitment" text in AppLayout's Header with a route-aware title.
- `/` → "Candidates"
- `/candidates/:id` → candidate's name
- `/jobs` → "Jobs"
- `/jobs/:id` → job title
- `/jobs/:id/compare` → "Compare Candidates"
Implementation: `useLocation` + a title map or per-page `<title>` pattern.

**D3 — Remove Settings nav item**  
Remove the disabled Settings item from `menuItems` in AppLayout. Re-add when the settings page is built.

### Interaction States

**D4 — Add error states to CandidateList and CandidateDetail**  
Each `useQuery` needs an `isError` branch with:
- Inline error message: "Couldn't load candidates. Check your connection."
- Retry button (calls `queryClient.invalidateQueries`)

**D5 — Standardize loading on AntD Skeleton**  
Replace the custom CSS pulse-skeleton in CandidateDetail with AntD `<Skeleton>`. Use full-page Spin only for inline actions (button submit), not page-level loads.

### User Journey

**D6 — Add Compare CTA to JobDetail**  
Add "Compare Candidates" button above the applications list in JobDetail.  
Target: `/jobs/:id/compare`. Show only when `applications.filter(a => a.candidate_id).length >= 2`.

**D7 — Update CandidateList empty state copy**  
Replace:
- Title: "No candidates yet"
- Subtitle: (none)

With:
- Title: "Upload resumes to start matching candidates to jobs with AI"
- Subtitle: "Then compare top candidates head-to-head."

### AI Slop

**D8 — Remove decorative blobs from CandidateDetail hero**  
Delete the two `position: absolute` div circles in the hero banner section of CandidateDetail. The `linear-gradient` background and avatar accent color provide sufficient visual character.

**D9 — Style JobList table to match design system**  
Keep the table layout (appropriate for columnar job data) but apply the token set:
- Font: Plus Jakarta Sans, #0F172A headers
- Remove default AntD table borders; use `#F8FAFC` row hover
- Replace `<Tag>` seniority with matching pill badges from SENIORITY_CONFIG
- Match the filter bar styling from CandidateList (`#F8FAFC` bg, `#E2E8F0` border, `borderRadius: 12`)

### Design System

**D10 — Extract SectionCard to shared component**  
Move `SectionCard` from CandidateDetail to `frontend/src/components/ui/SectionCard.tsx`.  
Replace raw AntD `<Card>` usage in JobDetail with it.

**D11 — Shared SeniorityBadge component**  
Create `frontend/src/components/ui/SeniorityBadge.tsx` using `SENIORITY_CONFIG`.  
Replace all 4 divergent implementations (CandidateList, CandidateDetail, JobList, JobDetail).

### Responsive & Accessibility

**D12 — Keyboard navigation for candidate cards**  
Wrap each `CandidateCard` div in a React Router `<Link>` or add `tabIndex={0}`, `role="button"`, `onKeyDown` (Enter/Space triggers click). The delete button inside the card should remain a separate focusable element.

**D13 — Contrast fix: secondary text**  
Replace `#94A3B8` with `#6B7280` in all small-text (≤13px) contexts.  
`#6B7280` on white = 4.63:1 (passes WCAG AA).  
Grep targets: `color: '#94A3B8'` in CandidateList, CandidateDetail, JobList.

### Responsive

**D14 — CompareCandidates mobile layout**  
At `≤768px`: stack A column (full width) → AI center card → B column.  
One media query or Tailwind breakpoint.

---

## NOT in Scope

- Settings page design — doesn't exist yet
- Login/auth UI flow — no auth in Sprint 1
- Pagination UI — acceptable to fetch all for MVP
- Export/report functionality — not planned
- Full mobile-first redesign — fixes specified are targeted, not a redesign

---

## What Already Exists (Reuse)

- `SectionCard` — CandidateDetail:139 — extract to `components/ui/`
- `SENIORITY_CONFIG` — `constants/seniority.ts` — already shared
- `avatarColor()` + `initials()` — duplicated in CandidateList and CandidateDetail — move to `utils/candidate.ts`
- `contactChipStyle` — CandidateDetail — generalize to `utils/styles.ts`
- UploadModal 3-step wizard — no changes needed

---

## Implementation Tasks

Synthesized from this review's findings. Each task derives from a specific finding above.

- [ ] **T1 (P2, human: ~30min / CC: ~10min)** — AppLayout — Add route-aware contextual title to header
  - Surfaced by: Pass 1 (IA) — static "AI Recruitment" header wastes page context
  - Files: `frontend/src/components/Layout/AppLayout.tsx`
  - Verify: Navigate to each route; header reflects current page

- [ ] **T2 (P2, human: ~10min / CC: ~5min)** — AppLayout — Remove disabled Settings nav item
  - Surfaced by: Pass 1 (IA) — dead nav trains users to ignore nav
  - Files: `frontend/src/components/Layout/AppLayout.tsx`
  - Verify: Sidebar shows only Candidates + Jobs

- [ ] **T3 (P2, human: ~1h / CC: ~20min)** — CandidateList + CandidateDetail — Add error states with retry
  - Surfaced by: Pass 2 (States) — no error branch on useQuery calls
  - Files: `frontend/src/pages/CandidateList.tsx`, `frontend/src/pages/CandidateDetail.tsx`
  - Verify: Disable API in Network tab; error message + retry button appears

- [ ] **T4 (P2, human: ~45min / CC: ~15min)** — CandidateDetail — Replace CSS pulse-skeleton with AntD Skeleton
  - Surfaced by: Pass 2 (States) — inconsistent loading UX
  - Files: `frontend/src/pages/CandidateDetail.tsx`
  - Verify: Loading state matches JobDetail skeleton visually

- [ ] **T5 (P2, human: ~20min / CC: ~5min)** — JobDetail — Add "Compare Candidates" CTA
  - Surfaced by: Pass 3 (Journey) — Compare feature buried, not discoverable
  - Files: `frontend/src/pages/JobDetail.tsx`
  - Verify: Button visible when ≥2 applications exist; navigates to compare route

- [ ] **T6 (P2, human: ~10min / CC: ~5min)** — CandidateList — Update empty state copy
  - Surfaced by: Pass 3 (Journey) — copy doesn't communicate AI value
  - Files: `frontend/src/pages/CandidateList.tsx`
  - Verify: Empty state shows new copy with subtitle

- [ ] **T7 (P2, human: ~15min / CC: ~5min)** — CandidateDetail — Remove decorative blobs from hero
  - Surfaced by: Pass 4 (AI Slop) — decorative blobs earn no pixels
  - Files: `frontend/src/pages/CandidateDetail.tsx`
  - Verify: Hero renders without absolute-positioned circles

- [ ] **T8 (P1, human: ~2h / CC: ~30min)** — JobList — Style table to match design system
  - Surfaced by: Pass 4 (AI Slop) + Pass 5 (Design System) — visual inconsistency with CandidateList
  - Files: `frontend/src/pages/JobList.tsx`
  - Verify: Job rows use pill badges, matching filter bar, Plus Jakarta Sans headers

- [ ] **T9 (P2, human: ~1h / CC: ~20min)** — components/ui — Extract SectionCard + SeniorityBadge
  - Surfaced by: Pass 5 (Design System) — 4 divergent implementations of same pattern
  - Files: new `frontend/src/components/ui/SectionCard.tsx`, `frontend/src/components/ui/SeniorityBadge.tsx`
  - Verify: Both components render identically across all 5 pages

- [ ] **T10 (P2, human: ~45min / CC: ~10min)** — CandidateList — Add keyboard nav to candidate cards
  - Surfaced by: Pass 6 (A11y) — clickable divs not keyboard-accessible
  - Files: `frontend/src/pages/CandidateList.tsx`
  - Verify: Tab to card, press Enter → navigates to candidate detail

- [ ] **T11 (P2, human: ~30min / CC: ~10min)** — Global — Fix secondary text contrast
  - Surfaced by: Pass 6 (A11y) — #94A3B8 at 11-12px fails WCAG AA (3.6:1 vs 4.5:1)
  - Files: `frontend/src/pages/CandidateList.tsx`, `CandidateDetail.tsx`, `JobList.tsx`
  - Verify: `grep -r "94A3B8"` returns only acceptable uses (status dots, borders)

- [ ] **T12 (P2, human: ~30min / CC: ~10min)** — CompareCandidates — Mobile responsive stacking
  - Surfaced by: Pass 6 (Responsive) — 3-col layout breaks at 375px
  - Files: `frontend/src/pages/CompareCandidates.tsx`
  - Verify: At 375px, columns stack vertically; A → center AI → B

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | DECISIONS_RESOLVED | 8 decisions, 7 impl tasks — see ENG_REVIEW.md |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | ISSUES_OPEN | score: 5/10 → 7/10, 12 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**UNRESOLVED:** 0 (all 13 decisions resolved by user)
**VERDICT:** Design review ran with issues. Eng review complete. Both reviews resolved — ready to execute.
