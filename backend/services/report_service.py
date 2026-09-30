"""
ReportService — generates professional PDF and DOCX research reports.

PDF:  ReportLab with custom styles, cover page, TOC-style headers,
      numbered sections, page numbers, ruled lines.
DOCX: python-docx with matching section structure.
"""

import os
from datetime import datetime
from backend.utils.config import Config
from backend.utils.logger import logger

# ── ReportLab imports ──────────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    PageBreak, Table, TableStyle, ListFlowable, ListItem,
)
from reportlab.platypus.flowables import KeepTogether

# ── python-docx ───────────────────────────────────────────────────────────────
from docx import Document as DocxDocument
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe(text) -> str:
    """Return text as a clean string, never None."""
    if text is None:
        return ""
    return str(text).strip()


def _split_items(value) -> list:
    """Accept either a list or a newline/bullet-separated string."""
    if isinstance(value, list):
        return [_safe(i) for i in value if _safe(i)]
    text = _safe(value)
    if not text:
        return []
    import re
    lines = re.split(r"\n|(?<=\.)\s*\d+\.\s*", text)
    return [re.sub(r"^[\-\*\•\d\.]+\s*", "", l).strip() for l in lines if l.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# PDF Generation
# ─────────────────────────────────────────────────────────────────────────────

class _PageTemplate:
    """Adds page numbers + header line to every page."""

    def __init__(self, title: str):
        self.title = title

    def on_page(self, canvas, doc):
        canvas.saveState()
        w, h = A4
        # Header line
        canvas.setStrokeColor(colors.HexColor("#4361ee"))
        canvas.setLineWidth(1.5)
        canvas.line(2 * cm, h - 1.5 * cm, w - 2 * cm, h - 1.5 * cm)
        # Report title in header
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(2 * cm, h - 1.2 * cm, self.title[:80])
        # Footer line
        canvas.line(2 * cm, 1.5 * cm, w - 2 * cm, 1.5 * cm)
        # Page number
        canvas.drawRightString(w - 2 * cm, 1.0 * cm, f"Page {doc.page}")
        canvas.drawString(2 * cm, 1.0 * cm, f"Generated {datetime.now().strftime('%B %d, %Y')}")
        canvas.restoreState()


def _build_pdf_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title",
        fontSize=26, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_CENTER, spaceAfter=16,
    )
    styles["cover_subtitle"] = ParagraphStyle(
        "cover_subtitle",
        fontSize=13, fontName="Helvetica",
        textColor=colors.HexColor("#4361ee"),
        alignment=TA_CENTER, spaceAfter=8,
    )
    styles["cover_meta"] = ParagraphStyle(
        "cover_meta",
        fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#64748b"),
        alignment=TA_CENTER, spaceAfter=4,
    )
    styles["section_heading"] = ParagraphStyle(
        "section_heading",
        fontSize=14, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#4361ee"),
        spaceBefore=18, spaceAfter=8, leading=18,
    )
    styles["body"] = ParagraphStyle(
        "body",
        fontSize=10.5, fontName="Helvetica",
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_JUSTIFY, spaceAfter=10, leading=16,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet",
        fontSize=10.5, fontName="Helvetica",
        textColor=colors.HexColor("#1e293b"),
        leftIndent=16, spaceAfter=6, leading=15,
        bulletIndent=4,
    )
    styles["ref"] = ParagraphStyle(
        "ref",
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#475569"),
        leftIndent=16, spaceAfter=5, leading=13,
    )
    styles["toc_heading"] = ParagraphStyle(
        "toc_heading",
        fontSize=11, fontName="Helvetica",
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=5,
    )
    return styles


def _section(story, styles, number: str, heading: str, content, is_list=False):
    """Render one report section with number + heading + content."""
    if not content:
        return

    story.append(KeepTogether([
        HRFlowable(width="100%", thickness=0.5,
                   color=colors.HexColor("#e2e8f0"), spaceAfter=4),
        Paragraph(f"{number}. {heading}", styles["section_heading"]),
    ]))

    if is_list:
        items = _split_items(content)
        for item in items:
            story.append(Paragraph(f"• {item}", styles["bullet"]))
    else:
        for para in _safe(content).split("\n\n"):
            para = para.strip()
            if para:
                story.append(Paragraph(para, styles["body"]))

    story.append(Spacer(1, 8))


class ReportService:

    @staticmethod
    def generate_pdf(report_data: dict, output_path: str) -> str | None:
        logger.info(f"Generating PDF: {output_path}")
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            title    = _safe(report_data.get("title", "Research Report"))
            tpl      = _PageTemplate(title)
            doc      = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                topMargin=2.5 * cm,  bottomMargin=2.5 * cm,
            )
            styles = _build_pdf_styles()
            story  = []

            # ── Cover page ─────────────────────────────────────────────────
            story.append(Spacer(1, 3 * cm))
            story.append(Paragraph(title, styles["cover_title"]))
            story.append(Spacer(1, 0.4 * cm))
            story.append(HRFlowable(width="60%", thickness=2,
                                     color=colors.HexColor("#4361ee"),
                                     hAlign="CENTER"))
            story.append(Spacer(1, 0.4 * cm))
            story.append(Paragraph("AI Multi-Research Agent — Automated Research Report",
                                    styles["cover_subtitle"]))
            story.append(Spacer(1, 0.6 * cm))
            story.append(Paragraph(
                f"Generated on {datetime.now().strftime('%B %d, %Y  %H:%M')} UTC",
                styles["cover_meta"],
            ))
            story.append(Paragraph(
                f"Powered by Mixtral-8x7B · Tavily Search · RAG Pipeline",
                styles["cover_meta"],
            ))
            story.append(PageBreak())

            # ── Abstract ───────────────────────────────────────────────────
            abstract = _safe(report_data.get("abstract"))
            if abstract:
                story.append(Paragraph("Abstract", styles["section_heading"]))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                         color=colors.HexColor("#e2e8f0"), spaceAfter=6))
                story.append(Paragraph(abstract, styles["body"]))
                story.append(Spacer(1, 12))

            # ── Report sections ────────────────────────────────────────────
            _section(story, styles, "1", "Introduction",
                     report_data.get("introduction"))
            _section(story, styles, "2", "Key Findings",
                     report_data.get("key_findings") or report_data.get("findings"),
                     is_list=False)
            _section(story, styles, "3", "Key Insights",
                     report_data.get("insights"), is_list=True)
            _section(story, styles, "4", "Methodology",
                     report_data.get("methodology"))
            _section(story, styles, "5", "Challenges & Limitations",
                     report_data.get("challenges"))
            _section(story, styles, "6", "Future Directions",
                     report_data.get("future_directions"))
            _section(story, styles, "7", "Conclusion",
                     report_data.get("conclusion"))

            # ── References ─────────────────────────────────────────────────
            refs = _split_items(report_data.get("references", []))
            if refs:
                story.append(PageBreak())
                story.append(Paragraph("References", styles["section_heading"]))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                         color=colors.HexColor("#e2e8f0"), spaceAfter=6))
                for idx, ref in enumerate(refs, 1):
                    story.append(Paragraph(f"[{idx}] {ref}", styles["ref"]))

            doc.build(story, onFirstPage=tpl.on_page, onLaterPages=tpl.on_page)
            logger.info(f"PDF saved: {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"PDF generation failed: {exc}", exc_info=True)
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # DOCX Generation
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_docx(report_data: dict, output_path: str) -> str | None:
        logger.info(f"Generating DOCX: {output_path}")
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            doc   = DocxDocument()
            title = _safe(report_data.get("title", "Research Report"))

            # ── Styles ─────────────────────────────────────────────────────
            def set_heading(paragraph, text: str, level: int = 1):
                paragraph.clear()
                run = paragraph.add_run(text)
                run.bold = True
                run.font.size = Pt(16 - (level * 2))
                run.font.color.rgb = RGBColor(0x43, 0x61, 0xEE)

            def add_body(doc, text: str):
                if not text.strip():
                    return
                for chunk in text.split("\n\n"):
                    chunk = chunk.strip()
                    if chunk:
                        p = doc.add_paragraph(chunk)
                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                        p.runs[0].font.size = Pt(11)

            def add_bullet_list(doc, items):
                for item in _split_items(items):
                    p = doc.add_paragraph(style="List Bullet")
                    run = p.add_run(item)
                    run.font.size = Pt(11)

            def add_section(doc, number: str, heading: str, content, is_list=False):
                if not content:
                    return
                h = doc.add_heading("", level=1)
                set_heading(h, f"{number}. {heading}", level=1)
                if is_list:
                    add_bullet_list(doc, content)
                else:
                    add_body(doc, _safe(content))
                doc.add_paragraph()

            # ── Cover ──────────────────────────────────────────────────────
            cover = doc.add_paragraph()
            cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = cover.add_run(title)
            r.bold      = True
            r.font.size = Pt(22)
            r.font.color.rgb = RGBColor(0x1e, 0x29, 0x3b)

            sub = doc.add_paragraph()
            sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            sr = sub.add_run("AI Multi-Research Agent — Automated Research Report")
            sr.font.size  = Pt(12)
            sr.font.color.rgb = RGBColor(0x43, 0x61, 0xEE)

            meta = doc.add_paragraph()
            meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
            mr = meta.add_run(
                f"Generated: {datetime.now().strftime('%B %d, %Y')}  |  "
                "Powered by Mixtral-8x7B · Tavily · RAG"
            )
            mr.font.size  = Pt(9)
            mr.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)
            doc.add_page_break()

            # ── Abstract ───────────────────────────────────────────────────
            abstract = _safe(report_data.get("abstract"))
            if abstract:
                h = doc.add_heading("Abstract", level=1)
                set_heading(h, "Abstract", level=1)
                add_body(doc, abstract)
                doc.add_paragraph()

            # ── Sections ───────────────────────────────────────────────────
            add_section(doc, "1", "Introduction",         report_data.get("introduction"))
            add_section(doc, "2", "Key Findings",         report_data.get("key_findings") or report_data.get("findings"))
            add_section(doc, "3", "Key Insights",         report_data.get("insights"),          is_list=True)
            add_section(doc, "4", "Methodology",          report_data.get("methodology"))
            add_section(doc, "5", "Challenges & Limitations", report_data.get("challenges"))
            add_section(doc, "6", "Future Directions",    report_data.get("future_directions"))
            add_section(doc, "7", "Conclusion",           report_data.get("conclusion"))

            # ── References ─────────────────────────────────────────────────
            refs = _split_items(report_data.get("references", []))
            if refs:
                doc.add_page_break()
                h = doc.add_heading("References", level=1)
                set_heading(h, "References", level=1)
                for idx, ref in enumerate(refs, 1):
                    p = doc.add_paragraph()
                    r = p.add_run(f"[{idx}]  {ref}")
                    r.font.size = Pt(9.5)

            doc.save(output_path)
            logger.info(f"DOCX saved: {output_path}")
            return output_path

        except Exception as exc:
            logger.error(f"DOCX generation failed: {exc}", exc_info=True)
            return None
