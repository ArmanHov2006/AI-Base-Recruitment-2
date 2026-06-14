import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import app.interviews.models  # noqa: F401 — register InterviewSession/InterviewAnswer with SQLAlchemy Base
import app.resumes.models  # noqa: F401 — register CandidateResume with SQLAlchemy Base
from app.ai.router import router as ai_router
from app.analytics.router import router as analytics_router
from app.applications.router import router as applications_router
from app.audit.middleware import AuditLogMiddleware
from app.audit.router import router as audit_router
from app.auth_sso import router as sso_router
from app.candidates.router import router as candidates_router
from app.comparisons.router import router as comparisons_router
from app.config import settings
from app.database import engine
from app.evaluations.router import router as evaluations_router
from app.gdpr.router import router as gdpr_router
from app.interviews.router import router as interviews_router
from app.jobs.router import router as jobs_router
from app.limiter import limiter
from app.llm import get_llm_client
from app.notes.router import router as notes_router
from app.notifications.router import router as notifications_router
from app.parser.router import router as parser_router
from app.search.client import close_es_client, ensure_index
from app.storage.client import ensure_bucket
from app.storage.router import router as storage_router
from app.users.admin_router import router as users_admin_router
from app.users.router import router as auth_router
from app.watchers.router import router as watchers_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await ensure_bucket()
    try:
        await get_llm_client().warmup()
    except Exception as exc:
        logger.warning("LLM warmup failed: %s", exc)
    # Elasticsearch: create index if needed (no-op when ES_URL is unset)
    try:
        await ensure_index()
    except Exception as exc:
        logger.warning("Elasticsearch index setup failed: %s", exc)
    yield
    await close_es_client()
    await engine.dispose()


app = FastAPI(title="AI Recruitment API", lifespan=lifespan)  # type: ignore[assignment]

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(AuditLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)

app.include_router(auth_router)
app.include_router(sso_router)
app.include_router(users_admin_router)
app.include_router(storage_router)
app.include_router(parser_router)
app.include_router(candidates_router)
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(comparisons_router)
app.include_router(evaluations_router)
app.include_router(notes_router)
app.include_router(notifications_router)
app.include_router(watchers_router)
app.include_router(analytics_router)
app.include_router(audit_router)
app.include_router(ai_router)
app.include_router(gdpr_router)
app.include_router(interviews_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
