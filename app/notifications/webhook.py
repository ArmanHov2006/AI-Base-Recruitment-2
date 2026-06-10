"""Fire-and-forget Slack / MS Teams webhooks."""

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

_FINAL_STAGES = frozenset({"offer", "hired", "rejected"})
_HIGH_SCORE_THRESHOLD = 75  # 0-100 scale; proxy for S/A tier


async def _post(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        log.warning("webhook.post_failed", url=url, exc=str(exc))


async def _notify(text: str) -> None:
    if settings.slack_webhook_url:
        await _post(settings.slack_webhook_url, {"text": text})
    if settings.teams_webhook_url:
        await _post(settings.teams_webhook_url, {"text": text})


async def notify_stage_change(
    candidate_name: str | None,
    job_title: str | None,
    new_status: str,
    candidate_id: str | None = None,
) -> None:
    """Fire only for final pipeline stages; intermediate moves stay email-only."""
    if new_status not in _FINAL_STAGES:
        return
    link = f" — <{settings.app_base_url}/candidates/{candidate_id}|View profile>" if candidate_id else ""
    text = (
        f":briefcase: *Stage change* — "
        f"{candidate_name or 'Unknown candidate'} → "
        f"*{new_status}* for *{job_title or 'unknown job'}*{link}"
    )
    await _notify(text)


async def notify_sla_alert(
    candidate_name: str | None,
    job_title: str | None,
    status: str,
    days_stale: int,
    sla_days: int,
    candidate_id: str | None = None,
) -> None:
    link = f" — <{settings.app_base_url}/candidates/{candidate_id}|View profile>" if candidate_id else ""
    text = (
        f":warning: *SLA breach* — "
        f"{candidate_name or 'Unknown'} stuck in *{status}* "
        f"for *{days_stale}d* (SLA: {sla_days}d) — "
        f"*{job_title or 'unknown job'}*{link}"
    )
    await _notify(text)


async def notify_high_score(
    candidate_name: str | None,
    job_title: str | None,
    overall_score: int,
    candidate_id: str | None = None,
) -> None:
    link = f" — <{settings.app_base_url}/candidates/{candidate_id}|View profile>" if candidate_id else ""
    text = (
        f":star: *High-score candidate* — "
        f"{candidate_name or 'Unknown'} scored *{overall_score}/100* "
        f"for *{job_title or 'unknown job'}* — review now{link}"
    )
    await _notify(text)


async def notify_slack_daily_summary(
    new_today: int,
    open_total: int,
    sla_breaches: int,
    high_score_today: int,
    status_breakdown: dict[str, int],
) -> None:
    breakdown = ", ".join(f"{k}: {v}" for k, v in status_breakdown.items()) or "—"
    text = (
        f":bar_chart: *Daily Recruitment Summary*\n"
        f"• New applications today: *{new_today}*\n"
        f"• Open pipeline: *{open_total}* ({breakdown})\n"
        f"• Active SLA breaches: *{sla_breaches}*\n"
        f"• High-score candidates today (≥75): *{high_score_today}*"
    )
    await _notify(text)
