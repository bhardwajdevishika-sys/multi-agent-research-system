"""
ReporterAgent — builds a fully structured research report in ONE LLM call.

Output sections:
  ABSTRACT | INTRODUCTION | KEY_FINDINGS | METHODOLOGY | CHALLENGES |
  FUTURE_DIRECTIONS | CONCLUSION
"""

import re
from backend.models.llm_loader import LLMLoader
from backend.utils.logger import logger

# Section markers the LLM is asked to use
_SECTIONS = [
    "ABSTRACT",
    "INTRODUCTION",
    "KEY_FINDINGS",
    "METHODOLOGY",
    "CHALLENGES",
    "FUTURE_DIRECTIONS",
    "CONCLUSION",
]


class ReporterAgent:
    def __init__(self):
        self.llm = LLMLoader()

    def run(self, topic: str, summary: str, insights: list, citations: list) -> dict:
        logger.info(f"Reporter: assembling report for '{topic}'")

        insights_block = "\n".join(f"- {i}" for i in insights) if insights else "- See findings below."

        system = (
            "You are a professional academic report writer. "
            "Produce well-structured, factual, formal research reports. "
            "Use only information from the provided summary. Never fabricate data."
        )
        user = (
            f"Write a complete, professional research report on the topic:\n"
            f"\"{topic}\"\n\n"
            f"BASE YOUR REPORT ON THIS VERIFIED SUMMARY:\n{summary[:4500]}\n\n"
            f"KEY INSIGHTS ALREADY EXTRACTED:\n{insights_block}\n\n"
            f"OUTPUT FORMAT — use these EXACT section headers on their own line:\n"
            f"ABSTRACT\n"
            f"INTRODUCTION\n"
            f"KEY_FINDINGS\n"
            f"METHODOLOGY\n"
            f"CHALLENGES\n"
            f"FUTURE_DIRECTIONS\n"
            f"CONCLUSION\n\n"
            f"REQUIREMENTS:\n"
            f"- ABSTRACT: 150–200 words, third-person academic style\n"
            f"- INTRODUCTION: 2–3 paragraphs, background & objectives\n"
            f"- KEY_FINDINGS: 3–5 numbered, specific findings from the summary\n"
            f"- METHODOLOGY: describe the research approaches/methods found in sources\n"
            f"- CHALLENGES: limitations and open problems\n"
            f"- FUTURE_DIRECTIONS: 2–3 sentences on next steps\n"
            f"- CONCLUSION: 1–2 paragraphs summarising significance\n\n"
            f"Begin the report now:"
        )

        raw = self.llm.query(user, system_prompt=system, max_length=1800)
        sections = self._parse_sections(raw)

        report = {
            "title":             f"Research Report: {topic.title()}",
            "abstract":          sections.get("ABSTRACT",          ""),
            "introduction":      sections.get("INTRODUCTION",      ""),
            "key_findings":      sections.get("KEY_FINDINGS",       ""),
            "methodology":       sections.get("METHODOLOGY",        ""),
            "challenges":        sections.get("CHALLENGES",         ""),
            "future_directions": sections.get("FUTURE_DIRECTIONS",  ""),
            "conclusion":        sections.get("CONCLUSION",         ""),
            "insights":          insights,
            "findings":          summary,
            "references":        citations,
        }

        # Fallback: if parsing failed use full raw text as findings
        if not any([report["abstract"], report["introduction"], report["key_findings"]]):
            logger.warning("Reporter: section parsing failed — storing raw output.")
            report["findings"] = raw

        logger.info(f"Reporter: report assembled with {len([k for k,v in report.items() if v])} populated sections.")
        return report

    @staticmethod
    def _parse_sections(text: str) -> dict:
        """
        Split the LLM output into labelled sections using the header markers.
        """
        sections = {}
        # Build a pattern that matches any known header at the start of a line
        pattern = re.compile(
            r"^(" + "|".join(re.escape(s) for s in _SECTIONS) + r")\s*[:\-]?\s*$",
            re.MULTILINE | re.IGNORECASE,
        )
        parts   = pattern.split(text)
        # parts = [pre_text, header1, body1, header2, body2, ...]
        i = 1
        while i < len(parts) - 1:
            header = parts[i].strip().upper()
            body   = parts[i + 1].strip()
            if header and body:
                sections[header] = body
            i += 2
        return sections
