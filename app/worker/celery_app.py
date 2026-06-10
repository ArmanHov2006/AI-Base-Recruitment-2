import sys

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ai_recruitment",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks", "app.worker.audit_tasks"],
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # prefork pool uses Unix semaphores broken on Windows; solo runs in-process
    worker_pool="solo" if sys.platform == "win32" else "prefork",
)

celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update({
    "audit-purge-daily": {
        "task": "audit.purge_old_logs",
        "schedule": crontab(hour=2, minute=0),
    },
    "interview-reminders-every-15min": {
        "task": "interview.send_reminders",
        "schedule": crontab(minute="*/15"),
    },
    "sla-alerts-daily": {
        "task": "sla.send_alerts",
        "schedule": crontab(hour=9, minute=0),
    },
    "digest-daily": {
        "task": "digest.send_daily",
        "schedule": crontab(hour=8, minute=0),
    },
    "digest-weekly": {
        "task": "digest.send_weekly",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 8am UTC
    },
    "slack-daily-summary": {
        "task": "slack.daily_summary",
        "schedule": crontab(hour=14, minute=0),  # 6pm Yerevan (UTC+4)
    },
})
