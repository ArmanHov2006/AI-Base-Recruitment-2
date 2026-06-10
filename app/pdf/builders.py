"""PDF document builders (reportlab, pure-Python — no system deps).

Two outputs:
- candidate_pdf: a formatted candidate profile.
- analytics_pdf: a recruitment dashboard summary.

Both return raw PDF bytes ready to hand back as `application/pdf`.
"""
import html
import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.analytics.schemas import FunnelResponse, OverviewResponse
from app.candidates.models import Candidate

_ACCENT = colors.HexColor("#0369A1")
_MUTED = colors.HexColor("#64748B")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=22, leading=26,
            textColor=colors.HexColor("#0F172A"),
        ),
        "kicker": ParagraphStyle(
            "kicker", parent=base["Normal"], fontSize=9, leading=12,
            textColor=_ACCENT, spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13, leading=16,
            textColor=_ACCENT, spaceBefore=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10, leading=14, alignment=TA_LEFT
        ),
        "muted": ParagraphStyle(
            "muted", parent=base["Normal"], fontSize=9, leading=12, textColor=_MUTED
        ),
        "item": ParagraphStyle(
            "item", parent=base["Normal"], fontSize=10, leading=13, leftIndent=10
        ),
    }
    return styles


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _render(elements: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Export",
    )
    doc.build(elements)
    return buf.getvalue()


# ── Candidate profile ───────────────────────────────────────────────────────


def candidate_pdf(candidate: Candidate) -> bytes:
    s = _styles()
    el: list = []

    el.append(Paragraph("CANDIDATE PROFILE", s["kicker"]))
    el.append(Paragraph(_esc(candidate.name or "Unknown candidate"), s["title"]))

    contact_bits = [b for b in (candidate.email, candidate.phone, candidate.location) if b]
    if contact_bits:
        el.append(Paragraph(_esc("  •  ".join(contact_bits)), s["muted"]))
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))

    # Key facts table
    facts: list[tuple[str, str]] = []
    if candidate.seniority:
        facts.append(("Seniority", candidate.seniority.capitalize()))
    if candidate.years_experience is not None:
        facts.append(("Experience", f"{candidate.years_experience} years"))
    if candidate.desired_position:
        facts.append(("Desired position", candidate.desired_position))
    if candidate.desired_salary is not None:
        facts.append(("Desired salary", f"{candidate.desired_salary:,}"))
    if candidate.linkedin_url:
        facts.append(("LinkedIn", candidate.linkedin_url))
    if candidate.github_url:
        facts.append(("GitHub", candidate.github_url))
    if facts:
        table = Table(
            [
                [Paragraph(f"<b>{_esc(k)}</b>", s["body"]), Paragraph(_esc(v), s["body"])]
                for k, v in facts
            ],
            colWidths=[40 * mm, None],
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        el.append(Spacer(1, 8))
        el.append(table)

    if candidate.summary:
        el.append(Paragraph("Summary", s["h2"]))
        el.append(Paragraph(_esc(candidate.summary), s["body"]))

    if candidate.skills:
        el.append(Paragraph("Skills", s["h2"]))
        el.append(Paragraph(_esc(", ".join(candidate.skills)), s["body"]))

    if candidate.certifications:
        el.append(Paragraph("Certifications", s["h2"]))
        el.append(Paragraph(_esc(", ".join(candidate.certifications)), s["body"]))

    if candidate.languages:
        el.append(Paragraph("Languages", s["h2"]))
        el.append(Paragraph(_esc(", ".join(candidate.languages)), s["body"]))

    work = candidate.work_experiences or []
    if work:
        el.append(Paragraph("Work Experience", s["h2"]))
        for exp in work:
            if not isinstance(exp, dict):
                continue
            role = exp.get("role") or "Unknown role"
            company = exp.get("company")
            header = role + (f" · {company}" if company else "")
            period = f"{exp.get('start_date') or '?'} – {exp.get('end_date') or 'present'}"
            el.append(Paragraph(f"<b>{_esc(header)}</b>", s["body"]))
            el.append(Paragraph(_esc(period), s["muted"]))
            if exp.get("description"):
                el.append(Paragraph(_esc(exp["description"]), s["item"]))
            for bullet in exp.get("achievements") or []:
                el.append(Paragraph(f"• {_esc(bullet)}", s["item"]))
            el.append(Spacer(1, 4))

    education = candidate.education or []
    if education:
        el.append(Paragraph("Education", s["h2"]))
        for edu in education:
            if not isinstance(edu, dict):
                continue
            inst = edu.get("institution") or "Institution"
            degree = edu.get("degree")
            year = edu.get("year")
            line = inst
            if degree:
                line += f" — {degree}"
            if year:
                line += f" ({year})"
            el.append(Paragraph(_esc(line), s["body"]))

    if len(el) <= 4:  # only header rendered → no profile data
        el.append(Spacer(1, 8))
        el.append(Paragraph("No additional profile data available.", s["muted"]))

    return _render(el)


# ── Analytics summary ─────────────────────────────────────────────────────────

_STAGE_LABELS = {
    "applied": "Applied",
    "reviewing": "Reviewing",
    "shortlisted": "Shortlisted",
    "interview": "Interview",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
    "parsing": "Parsing",
    "parse_failed": "Parse failed",
    "screening": "Screening",
}


def _summary_table(rows: list[list[Any]], header: list[str], col_widths: list[Any]) -> Table:
    head_style = getSampleStyleSheet()["Normal"]
    data: list = [[Paragraph(f"<b>{html.escape(h)}</b>", head_style) for h in header]]
    for row in rows:
        data.append([
            Paragraph(html.escape(str(cell)), head_style) if isinstance(cell, str) else cell
            for cell in row
        ])
    table = Table(data, colWidths=col_widths, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def analytics_pdf(overview: OverviewResponse, funnel: FunnelResponse) -> bytes:
    s = _styles()
    el: list = []

    el.append(Paragraph("RECRUITMENT ANALYTICS", s["kicker"]))
    el.append(Paragraph("Dashboard Summary", s["title"]))
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))

    el.append(Paragraph("Totals", s["h2"]))
    el.append(
        _summary_table(
            [
                ["Candidates", str(overview.total_candidates)],
                ["Jobs", str(overview.total_jobs)],
                ["Applications", str(overview.total_applications)],
            ],
            ["Metric", "Count"],
            [60 * mm, 40 * mm],
        )
    )

    el.append(Paragraph("Hiring Funnel", s["h2"]))
    funnel_rows = [
        [
            _STAGE_LABELS.get(stage.stage, stage.stage),
            str(stage.count),
            "—" if stage.conversion_rate is None else f"{stage.conversion_rate}%",
        ]
        for stage in funnel.stages
    ]
    if funnel_rows:
        el.append(
            _summary_table(
                funnel_rows, ["Stage", "Count", "Conversion"], [60 * mm, 30 * mm, 40 * mm]
            )
        )
    else:
        el.append(Paragraph("No funnel data.", s["muted"]))

    if overview.top_skills:
        el.append(Paragraph("Top Skills", s["h2"]))
        el.append(
            _summary_table(
                [[sc.skill, str(sc.count)] for sc in overview.top_skills],
                ["Skill", "Count"],
                [90 * mm, 30 * mm],
            )
        )

    return _render(el)
