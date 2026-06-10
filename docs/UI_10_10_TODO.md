# UI 10/10 Follow-Up

Use this as Claude handoff if more polish is needed.

## Done in Codex pass

- Login now stays in first viewport on tablet/desktop instead of stacking too early.
- Mobile login hides decorative preview cards so sign-in appears sooner.
- Protected-route loading now says `Checking session...` and returns to login after timeout.
- Candidate empty table no longer forces horizontal scroll.
- Added missing `frontend/public/icon.svg`.
- Fixed build-blocking `replaceAll` usage in `Pipeline.tsx`.

## Remaining To Reach 10/10

1. Create design tokens for spacing and panels. Replace one-off `rgba(...)` borders/shadows with variables.
2. Reduce indigo dominance across app. Keep primary blue for actions, use green for decisions, amber for risk, neutral gray for chrome.
3. Rework overview page hierarchy. Make one primary workspace area, not equal-weight card mosaic.
4. Audit all mobile app screens. Sidebar/header likely need bottom-nav or compact rail behavior below 720px.
5. Add proper empty states for jobs, pipeline, compare, analytics. Each should have one action, one sentence, no table chrome.
6. Normalize typography scale. Current headings are bold but not refined; define `title`, `section`, `label`, `metric`, `body`.
7. Add Playwright visual smoke screenshots for `/login`, `/`, `/jobs`, `/jobs/:id/pipeline`.
8. Fix mojibake text like `Â·`, `â€”`, `â†“`, `âŒ˜K` in source/CSS comments.

## Acceptance Bar

- No console errors on fresh load.
- Login usable without scroll at 390x844 and 1024x768.
- No horizontal scroll on empty tables.
- App still builds with `npm run build`.
- Screens look calm when shadows/glows are removed.
