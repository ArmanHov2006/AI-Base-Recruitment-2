"""Recruiter notification emails. Plain-text bodies, fire-and-forget."""
import html

from app.users.email import _send


async def notify_new_application(
    job_title: str,
    candidate_name: str | None,
    creator_email: str,
) -> None:
    safe_title = html.escape(job_title)
    safe_name = html.escape(candidate_name or "Unknown")
    subject = f"New application submitted for: {safe_title}"
    body = (
        f"A new resume has been submitted for the position: {safe_title}\n\n"
        f"Candidate: {safe_name}\n\n"
        f"Log in to review and score the application."
    )
    await _send(to=creator_email, subject=subject, html=f"<pre>{body}</pre>")


async def notify_candidate_rejected(
    job_title: str,
    candidate_name: str | None,
    candidate_email: str,
) -> None:
    safe_title = html.escape(job_title)
    safe_name = html.escape(candidate_name or "Candidate")
    subject = f"Your application for {safe_title}"
    body = (
        f"Dear {safe_name},\n\n"
        f"Thank you for applying for the {safe_title} position at Ardshinbank.\n\n"
        f"After careful review, we will not be moving forward with your application "
        f"at this time. We appreciate the time you invested and wish you the best "
        f"in your search.\n\n"
        f"Best regards,\n"
        f"Ardshinbank Recruitment Team"
    )
    await _send(to=candidate_email, subject=subject, html=f"<pre>{body}</pre>")


async def notify_stage_change(
    job_title: str,
    candidate_name: str | None,
    new_stage: str,
    creator_email: str,
) -> None:
    safe_title = html.escape(job_title)
    safe_name = html.escape(candidate_name or "Unknown")
    safe_stage = html.escape(new_stage)
    subject = f"Application stage updated: {safe_title}"
    body = (
        f"An application for {safe_title} has moved to a new stage.\n\n"
        f"Candidate: {safe_name}\n"
        f"New stage: {safe_stage}\n\n"
        f"Log in to view the application."
    )
    await _send(to=creator_email, subject=subject, html=f"<pre>{body}</pre>")
