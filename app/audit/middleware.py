import uuid
from typing import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.audit.models import AuditLog
from app.config import settings
from app.database import async_session_factory

log = structlog.get_logger()

WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

# Endpoints we deliberately skip — high-volume or already audited elsewhere.
SKIP_PATHS = frozenset({
    "/healthz",
    "/auth/refresh",
    "/auth/login",
    "/auth/logout",
    "/auth/forgot-password",
    "/auth/resend-verification",
})


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = uuid.uuid4()
        response = await call_next(request)

        if request.method not in WRITE_METHODS:
            return response
        if request.url.path in SKIP_PATHS:
            return response

        try:
            user = getattr(request.state, "user", None)
            user_id = user.id if user is not None else None
            peer_ip = request.client.host if request.client else None
            xff = request.headers.get("x-forwarded-for", "")
            trusted = set(settings.trusted_proxies)
            client_host = (
                xff.split(",")[0].strip()
                if xff and peer_ip in trusted
                else peer_ip
            )

            async with async_session_factory() as session:
                session.add(
                    AuditLog(
                        user_id=user_id,
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        ip=client_host,
                        user_agent=request.headers.get("user-agent"),
                        request_id=request.state.request_id,
                    )
                )
                await session.commit()
        except Exception as exc:
            log.warning("audit.write_failed", error=str(exc), path=request.url.path)

        return response
