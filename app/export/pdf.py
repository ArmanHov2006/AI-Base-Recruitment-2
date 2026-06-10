"""PDF generation helpers using reportlab."""

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_W, _H = A4
_STYLES = getSampleStyleSheet()

_HEADING1 = ParagraphStyle(
    "Heading1",
    parent=_STYLES["Heading1"],
    fontSize=16,
    spaceAfter=6,
)
_HEADING2 = ParagraphStyle(
    "Heading2",
    parent=_STYLES["Heading2"],
    fontSize=12,
    spaceAfter=4,
    textColor=colors.HexColor("#1a56db"),
)
_NORMAL = _STYLES["Normal"]
_SMALL = ParagraphStyle("Small", parent=_STYLES["Normal"], fontSize=9, textColor=colors.grey)


def _p(text: str, style: ParagraphStyle | None = None) -> Paragraph:
    return Paragraph(str(text or ""), style or _NORMAL)


def _hr() -> HRFlowable:
    return HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=6)


def _kv_table(rows: list[tuple[str, Any]]) -> Table:
    data = [[_p(k, _SMALL), _p(str(v or "—"))] for k, v in rows if v]
    if not data:
        return Table([[_p("—")]])
    tbl = Table(data, colWidths=[4 * cm, 13 * cm])
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


def build_candidate_pdf(candidate: Any) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    story.append(_p(candidate.name or "Unnamed Candidate", _HEADING1))
    story.append(_hr())

    story.append(_kv_table([
        ("Email", candidate.email),
        ("Phone", candidate.phone),
        ("Location", candidate.location),
        ("Seniority", candidate.seniority),
        ("Experience", f"{candidate.years_experience} years" if candidate.years_experience else None),
        ("Desired Role", candidate.desired_position),
        ("Desired Salary", f"${candidate.desired_salary:,}" if candidate.desired_salary else None),
        ("LinkedIn", candidate.linkedin_url),
        ("GitHub", candidate.github_url),
    ]))

    if candidate.summary:
        story.append(Spacer(1, 8))
        story.append(_p("Summary", _HEADING2))
        story.append(_p(candidate.summary))

    if candidate.skills:
        story.append(Spacer(1, 8))
        story.append(_p("Skills", _HEADING2))
        story.append(_p(", ".join(candidate.skills)))

    if candidate.certifications:
        story.append(Spacer(1, 8))
        story.append(_p("Certifications", _HEADING2))
        story.append(_p(", ".join(candidate.certifications)))

    if candidate.languages:
        story.append(Spacer(1, 8))
        story.append(_p("Languages", _HEADING2))
        story.append(_p(", ".join(candidate.languages)))

    if candidate.work_experiences:
        story.append(Spacer(1, 8))
        story.append(_p("Work Experience", _HEADING2))
        for exp in candidate.work_experiences:
            if isinstance(exp, dict):
                title = exp.get("title") or exp.get("position") or ""
                company = exp.get("company") or ""
                dates = f"{exp.get('start_date', '')} – {exp.get('end_date', 'present')}"
                story.append(_p(f"<b>{title}</b> at {company} ({dates})"))
                if exp.get("description"):
                    story.append(_p(exp["description"], _SMALL))
                story.append(Spacer(1, 4))

    if candidate.education:
        story.append(Spacer(1, 8))
        story.append(_p("Education", _HEADING2))
        for edu in candidate.education:
            if isinstance(edu, dict):
                degree = edu.get("degree") or ""
                institution = edu.get("institution") or ""
                year = edu.get("year") or ""
                story.append(_p(f"<b>{degree}</b> – {institution} {year}"))
                story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


def build_analytics_pdf(
    overview: Any,
    funnel: Any,
    time_to_hire: Any,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    story.append(_p("Recruitment Analytics Report", _HEADING1))
    story.append(_hr())

    # Overview
    story.append(_p("Overview", _HEADING2))
    story.append(_kv_table([
        ("Total Candidates", overview.total_candidates),
        ("Total Jobs", overview.total_jobs),
        ("Total Applications", overview.total_applications),
    ]))

    story.append(Spacer(1, 8))
    story.append(_p("Applications by Status", _HEADING2))
    status_rows = [[_p("Status", _SMALL), _p("Count", _SMALL)]]
    for st, cnt in sorted(overview.applications_by_status.items()):
        status_rows.append([_p(st), _p(str(cnt))])
    tbl = Table(status_rows, colWidths=[8 * cm, 9 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4ff")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    # Time-to-hire
    if time_to_hire and time_to_hire.overall_avg_days is not None:
        story.append(Spacer(1, 8))
        story.append(_p("Time to Hire", _HEADING2))
        story.append(_kv_table([("Overall average", f"{time_to_hire.overall_avg_days} days")]))
        if time_to_hire.per_job:
            job_rows = [[_p("Job", _SMALL), _p("Avg Days", _SMALL), _p("Hired", _SMALL)]]
            for item in time_to_hire.per_job:
                job_rows.append([
                    _p(item.job_title or str(item.job_id)),
                    _p(str(item.avg_days_to_hire or "—")),
                    _p(str(item.hired_count)),
                ])
            tbl2 = Table(job_rows, colWidths=[9 * cm, 4 * cm, 4 * cm])
            tbl2.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f4ff")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(tbl2)

    doc.build(story)
    return buf.getvalue()


def build_qualified_candidates_pdf(
    job_title: str,
    threshold: float,
    candidates: list[dict],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm)
    story = []

    story.append(_p(f"Qualified Candidates — {job_title}", _HEADING1))
    story.append(_p(
        f"Threshold: {threshold:.1f} / 10  ·  "
        f"{len(candidates)} candidate{'s' if len(candidates) != 1 else ''} qualified",
        _SMALL,
    ))
    story.append(_hr())

    if not candidates:
        story.append(_p("No candidates meet the threshold."))
    else:
        header = [[_p("#", _SMALL), _p("Name", _SMALL), _p("Email", _SMALL), _p("Score", _SMALL)]]
        data_rows = [
            [
                _p(str(i + 1), _SMALL),
                _p(c.get("name") or "Unnamed"),
                _p(c.get("email") or "—", _SMALL),
                _p(f"{c['score']:.1f}"),
            ]
            for i, c in enumerate(candidates)
        ]
        tbl = Table(header + data_rows, colWidths=[1.2 * cm, 5.8 * cm, 6.5 * cm, 2.5 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ]))
        story.append(tbl)

    doc.build(story)
    return buf.getvalue()
