# Engineering Learning Plan

> **Ratio: 20% consuming resources, 80% building.**
> If you can't rebuild a stripped-down version (~50–200 lines), you don't understand it yet.

## The Learning Loop

```
1. Read just enough to know what problem it solves
2. Use it on a real task in this repo
3. Hit a wall → read the SOURCE CODE of the library
4. Rebuild a stripped-down version from scratch
5. Explain it in writing
6. Move on
```

---

## Phase 1 — Async Python Internals (Weeks 1–2)

**Done when:** You can explain why `asyncio.gather([c1, c2])` beats `await c1; await c2`, and debug a sync function blocking the event loop.

### Read
- [ ] asyncio "Coroutines and Tasks" — docs.python.org/3/library/asyncio-task.html
- [ ] "How the Python Event Loop Works" — Jesse Jiryu Davis PyCon talk (YouTube, 30 min)

### Read source
- `cpython/Lib/asyncio/base_events.py` — read `run_until_complete`
- `cpython/Lib/asyncio/tasks.py` — how `Task` wraps a coroutine
- → github.com/python/cpython/tree/main/Lib/asyncio

### Build
- [ ] `mini_event_loop.py` (~100 lines): callback queue + runs one `async def` + handles `await asyncio.sleep(0)`

### Apply here
- [ ] `app/database.py` — trace why `async_sessionmaker(expire_on_commit=False)` matters
- [ ] Write 3-sentence explanation in journal

**Verification:** *Why does `asyncio.sleep(0)` yield control but `time.sleep(0)` blocks the event loop?*

---

## Phase 2 — FastAPI + Starlette + Pydantic (Weeks 3–5)

**Done when:** You can build `app/notifications/` (router, service, schemas, tests) without looking at existing modules.

### Read
- [ ] FastAPI tutorial — fastapi.tiangolo.com/tutorial/ (skim in one sitting, then stop)

### Read source
- `fastapi/routing.py` — how `@app.get()` registers a route
- `fastapi/dependencies/` — how `Depends()` resolves
- `starlette/routing.py` — actual request → response flow
- `pydantic/main.py` — how validation works
- → github.com/fastapi/fastapi — read `APIRouter.add_api_route()`

### Build
- [ ] `mini_fastapi.py` using only Starlette: `GET /users/{id}`, manual Pydantic validation, one hand-written `Depends()`

### Apply here
- [ ] Trace full request: `app/main.py` → `app/candidates/router.py` → service → DB → response
- [ ] Implement TODO-002: re-score endpoint in `app/comparisons/`
- [ ] Write test in `tests/` using `httpx.AsyncClient`

**Verification:** *What does Starlette do when a request comes in before FastAPI touches it?*

---

## Phase 3 — SQLAlchemy 2.x + Alembic (Weeks 6–7)

**Done when:** You can explain Unit of Work in 2 sentences and write a FK migration without data loss.

### Read
- [ ] SQLAlchemy ORM quickstart — docs.sqlalchemy.org/en/20/orm/quickstart.html
- [ ] Async extensions — docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html

### Read source
- `sqlalchemy/orm/session.py` — Session, identity map, Unit of Work
- `sqlalchemy/orm/query.py` — how `select()` builds SQL
- → github.com/sqlalchemy/sqlalchemy — read `Session.flush()`

### Build
- [ ] `mini_orm.py` (~150 lines): `User` → `users` table via raw `sqlite3`, identity map by PK, `add()` / `flush()` / `commit()`

### Apply here
- [ ] Run `alembic history` — understand the full migration chain
- [ ] Read all models: `app/candidates/models.py`, `app/jobs/models.py`, `app/applications/models.py`
- [ ] Add `resume_language` column to candidates via new Alembic migration, then roll back
- [ ] Find a N+1 query (hint: routes loading related objects) → fix with `selectin` loading

**Verification:** *What is the identity map and why does `expire_on_commit=True` cause `MissingGreenlet` in async?*

---

## Phase 4 — AI/ML Foundations (Weeks 8–10)

**Done when:** You can explain why "extract skills as a JSON array" fails on edge cases and redesign with few-shot + output validation.

### The sequence
1. [ ] Karpathy "Neural Networks: Zero to Hero" — all 7 videos, code along → youtube.com/@AndrejKarpathy
2. [ ] "Attention Is All You Need" — arxiv.org/abs/1706.03762 (after video 7)
3. [ ] Anthropic research blog — anthropic.com/research (Constitutional AI + RLHF papers)
4. [ ] "The Illustrated Word2Vec" — jalammar.github.io/illustrated-word2vec/

### Build
- [ ] `bigram_lm.py` — character-level bigram LM in 50 lines of NumPy (before PyTorch)
- [ ] Tiny self-attention in NumPy
- [ ] Semantic search over job descriptions using sentence-transformers + cosine similarity

### Apply here
- [ ] Read `app/llm/base.py` — understand why `LLMClient` Protocol exists
- [ ] Read `app/parser/` — trace resume text → `CandidateCreate`
- [ ] Improve extraction prompt with few-shot examples, measure on 5 test resumes

**Verification:** *Why does self-attention have O(n²) memory complexity, and when does that matter?*

---

## Phase 5 — LLMs in Production (Weeks 11–12)

**Done when:** Measurable eval exists, prompt caching enabled (>80% hit rate), tool use for structured extraction.

### Read source
- `anthropic-sdk-python/src/anthropic/` + `_streaming.py`
- → github.com/anthropics/anthropic-sdk-python — read `Messages.create()`

### Reference
- Prompt caching — docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Tool use — docs.anthropic.com/en/docs/build-with-claude/tool-use
- Cookbook — github.com/anthropics/anthropic-cookbook
- Simon Willison's blog — simonwillison.net

### Apply here
- [ ] Migrate `app/llm/openai_client.py` → Anthropic client
- [ ] Add `cache_control: {"type": "ephemeral"}` to static system prompt in parser. Log cache hit rate.
- [ ] Replace "return JSON" pattern in `app/parser/` with `tool_use` call
- [ ] Create `scripts/eval_parser.py` — 5 sample resumes, score field extraction accuracy

**Verification:** *What is cache-busting in prompt caching and how do you avoid it?*

---

## Phase 6 — Claude Code Mastery (Ongoing from Day 1)

- [ ] Always `/plan` before non-trivial work
- [ ] Use `@file` for precise context — `@app/candidates/router.py` not "the candidates module"
- [ ] Read Claude Code hooks guide → docs.anthropic.com/en/docs/claude-code/hooks
- [ ] Set up `PostToolUse` hook: runs `pytest -x` after file edits
- [ ] Set up `PreCommit` hook: runs `ruff check .`
- [ ] Add project-specific commands to `.claude/commands/`
- [ ] Write to `CLAUDE.md` at end of every session: what you learned, what patterns emerged

**Rule: never accept Claude's first output without reading it. Read every diff.**

**Verification:** *What's the difference between a `PreToolUse` and `PostToolUse` hook?*

---

## Progress Log

| Phase | Started | Completed | Notes |
|---|---|---|---|
| 1 — Async Python | | | |
| 2 — FastAPI | | | |
| 3 — SQLAlchemy | | | |
| 4 — AI/ML | | | |
| 5 — LLMs in Production | | | |
| 6 — Claude Code | ongoing | — | |
