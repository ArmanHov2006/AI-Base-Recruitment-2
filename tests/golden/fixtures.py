"""Golden-set fixtures for AI-interview tier-classification.

Each case is a full interview transcript (3 Q/A pairs) plus the expected tier
for each of the four `INTERVIEW_WEIGHTS` dimensions (app/llm/rubric.py). The
golden-set eval (tests/test_interview_scoring_golden.py) sends the transcript
through the real LLM client and asserts its per-dimension tier lands within
±1 tier of the label here.

Provenance: seeded by Claude (2026-07-15) as an anchor set spanning the tier
ladder, not collected from real candidate interviews. Each label is written
to be unambiguous (deliberately not boundary-adjacent) so ±1 tolerance is
meaningful rather than a coin flip. Treat these as a first draft — a human
reviewer (recruiter/hiring manager) should read each transcript and confirm
or correct the labels before this gates real prompt changes. Swap in real
(anonymized) transcripts as they become available; keep the tier spread wide.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenCase:
    id: str
    job_title: str
    job_description: str
    required_skills: list[str]
    qa_pairs: list[tuple[str, str]]  # (question, answer)
    expected_tiers: dict[str, str]  # dimension -> tier
    notes: str = ""

    @property
    def transcript(self) -> str:
        parts = [f"Q{i}: {q}\nA{i}: {a}" for i, (q, a) in enumerate(self.qa_pairs, 1)]
        return "\n\n".join(parts)


_BACKEND_JOB_TITLE = "Backend Engineer"
_BACKEND_JOB_DESC = (
    "Build and operate the core API platform: FastAPI services, PostgreSQL data "
    "layer, background job processing, and production reliability."
)
_BACKEND_SKILLS = ["Python", "FastAPI", "PostgreSQL", "Docker"]

_QUESTIONS = (
    "Walk me through a time you optimized a slow database query. What was the "
    "bottleneck and how did you fix it?",
    "How would you design a rate limiter for a public API?",
    "Tell me about a disagreement you had with a teammate over a technical "
    "decision — how did you resolve it?",
)


GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        id="excellent_all_dims",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "At my last job our candidate search endpoint went from 40ms to 1.2s as the "
                "table crossed two million rows. I pulled the query plan with EXPLAIN ANALYZE "
                "and found we were doing a sequential scan because the filter combined a "
                "status column with an ILIKE on name, and ILIKE can't use a plain btree index. "
                "I added a GIN trigram index on name and a partial btree index on status for "
                "the 'active' case, which is 95% of traffic. That got us back to 15ms. I also "
                "added a regression test that fails the build if a listed slow query's plan "
                "shows a sequential scan over more than 10k rows, so we'd catch this before "
                "it reached production again.",
            ),
            (
                _QUESTIONS[1],
                "I'd use a token bucket per API key, backed by Redis so it works across "
                "multiple app instances. Each key gets a bucket size and refill rate — say "
                "100 tokens, refilling 10/sec — implemented as a single Lua script in Redis "
                "so the check-and-decrement is atomic and we avoid race conditions under "
                "concurrent requests. I'd return 429 with a Retry-After header computed from "
                "how many tokens are missing divided by the refill rate. For fairness I'd key "
                "by API key rather than IP, since IPs are shared behind NAT and a token bucket "
                "keyed by IP would punish innocent users on the same network.",
            ),
            (
                _QUESTIONS[2],
                "A teammate wanted to add a caching layer with Redis for a report endpoint "
                "that was slow. I pushed back — the report data changes per request based on "
                "filters, so cache hit rate would've been near zero and we'd be adding an "
                "operational dependency for no benefit. Instead of just saying no, I profiled "
                "the endpoint with them and we found the real cost was N+1 queries in the "
                "serializer. We fixed that with a single joined query, got the same latency "
                "win without the new infra, and documented the decision in the PR so the next "
                "person doesn't re-propose caching for the same reason.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "excellent",
            "answer_relevance": "excellent",
            "problem_structure": "excellent",
            "communication": "excellent",
        },
        notes="Correct, specific, quantified evidence on all three answers; STAR-shaped; confident fluent delivery.",
    ),
    GoldenCase(
        id="strong_technical_weak_communication",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "Yeah so basically there was this query, it was slow, like really slow, and I "
                "think what happened is, um, there was no index or something, so the database "
                "had to like scan through everything, and what I did was I added an index on "
                "the column we were filtering by and then it got way faster, I think it went "
                "from like a second to almost nothing, so that fixed it I guess.",
            ),
            (
                _QUESTIONS[1],
                "So for a rate limiter I'd probably do like a counter per user, and every "
                "request just increments it, and then, um, if it goes over some number you "
                "block them, and then it resets after a while, maybe using Redis for that "
                "because it's fast, and you'd want it shared across servers so one server "
                "isn't tracking it separately from another one I think.",
            ),
            (
                _QUESTIONS[2],
                "There was this one time, someone wanted to do something a certain way and I "
                "didn't really agree, so we kind of went back and forth about it for a bit, "
                "and eventually we just tried it their way first and it turned out okay so we "
                "kept it I guess, it wasn't a huge deal really.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "strong",
            "answer_relevance": "strong",
            "problem_structure": "partial",
            "communication": "weak",
        },
        notes=(
            "Right ideas each time (index, shared counter/Redis, compromise) but hedgy, "
            "filler-heavy, unstructured delivery with no concrete numbers on Q2/Q3."
        ),
    ),
    GoldenCase(
        id="partial_technically_wrong_but_fluent",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "Great question. In my experience, the best way to speed up any slow query is "
                "to simply upgrade the database server to more CPU and RAM — vertical scaling "
                "solves most performance issues in my experience, and it's usually faster to "
                "just throw hardware at the problem than to spend engineering time profiling "
                "the query itself.",
            ),
            (
                _QUESTIONS[1],
                "For a rate limiter, I would store the request count in a plain in-memory "
                "Python dictionary on the server, keyed by user ID, and reset it every minute "
                "with a background thread. That keeps things simple and avoids adding an "
                "external dependency like Redis.",
            ),
            (
                _QUESTIONS[2],
                "I generally avoid disagreements at work — I find it's best to defer to "
                "whoever has more seniority and just implement what they ask for, since "
                "second-guessing the decision usually just slows the team down.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "partial",
            "answer_relevance": "partial",
            "problem_structure": "strong",
            "communication": "strong",
        },
        notes=(
            "Well-spoken and directly on-topic, but the content is wrong or thin: vertical "
            "scaling is not the standard fix, an in-memory dict rate limiter breaks under "
            "multiple app instances, and the third answer dodges rather than describes a "
            "resolved technical disagreement."
        ),
    ),
    GoldenCase(
        id="weak_none_disengaged",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "I don't really remember a specific time like that. I guess sometimes things "
                "are slow and you just have to wait for it, or restart the server.",
            ),
            (
                _QUESTIONS[1],
                "I'm not sure, I haven't built anything like that before. Maybe you'd just "
                "block people who use it too much?",
            ),
            (
                _QUESTIONS[2],
                "I try to avoid conflict at work so nothing really comes to mind.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "none",
            "answer_relevance": "weak",
            "problem_structure": "weak",
            "communication": "partial",
        },
        notes=(
            "No technical substance anywhere ('restart the server', 'block people'); answers "
            "gesture at the topic without addressing it, no structure, short flat delivery."
        ),
    ),
    GoldenCase(
        id="junior_shallow_but_relevant_and_clear",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "In a school project, our app was slow when listing items from the database. "
                "I looked it up and learned that adding an index on the column we searched by "
                "helps the database find rows faster instead of checking every row. I added "
                "one on the 'name' column since that's what we searched by most, and the page "
                "loaded noticeably faster after that.",
            ),
            (
                _QUESTIONS[1],
                "I haven't built a rate limiter before, but from what I understand, you'd want "
                "to count how many requests each user makes in a time window, like per minute, "
                "and reject requests once they go over a limit. I'd want to look up existing "
                "libraries first rather than build the counting logic myself, since this is a "
                "well-known problem others have already solved carefully.",
            ),
            (
                _QUESTIONS[2],
                "On a group project, a teammate and I disagreed about naming conventions for "
                "our API endpoints. I explained why I preferred one style, listened to their "
                "reasoning, and since it was a small stylistic choice, I agreed to follow "
                "their preference so we'd stay consistent instead of spending more time on it.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "weak",
            "answer_relevance": "strong",
            "problem_structure": "strong",
            "communication": "strong",
        },
        notes=(
            "Directly on-topic, honest about limits, clearly organized and articulate — but "
            "shallow/student-level technical depth (no quantified before/after, no awareness "
            "of concurrency or distributed rate-limiting concerns)."
        ),
    ),
    GoldenCase(
        id="solid_competent_no_standout",
        job_title=_BACKEND_JOB_TITLE,
        job_description=_BACKEND_JOB_DESC,
        required_skills=_BACKEND_SKILLS,
        qa_pairs=[
            (
                _QUESTIONS[0],
                "We had a slow endpoint that joined orders with customers and filtered by "
                "date range. I checked the query plan, saw it wasn't using an index on the "
                "date column, added one, and confirmed with EXPLAIN that it switched to an "
                "index scan. Response time improved noticeably in our staging benchmarks.",
            ),
            (
                _QUESTIONS[1],
                "I'd implement a fixed-window counter per user stored in Redis with a TTL "
                "matching the window length, incrementing on each request and rejecting once "
                "the counter passes the limit. It's simpler than a sliding window or token "
                "bucket, and good enough unless we need smoother request pacing.",
            ),
            (
                _QUESTIONS[2],
                "A teammate and I disagreed on whether to use a message queue for a feature "
                "that didn't obviously need one. We talked through the actual requirements "
                "together, agreed it added complexity we didn't need yet, and went with a "
                "simpler synchronous call, keeping the queue idea documented for later if "
                "load increased.",
            ),
        ],
        expected_tiers={
            "technical_accuracy": "strong",
            "answer_relevance": "strong",
            "problem_structure": "strong",
            "communication": "strong",
        },
        notes=(
            "Correct and relevant throughout, reasonably structured — competent, no "
            "standout depth or quantified impact to justify 'excellent'."
        ),
    ),
]
