import re
from backend.models.llm_loader import LLMLoader
from backend.utils.logger import logger

# Hard cap on context sent to LLM — prevents token overflow
_MAX_CONTEXT_CHARS = 6000


class SummarizerAgent:
    def __init__(self):
        self.llm = LLMLoader()

    def run(self, topic: str, context: str) -> str:
        logger.info(f"Summarizer: synthesising findings for '{topic}'")

        # Trim context to avoid token overflow
        ctx = context[:_MAX_CONTEXT_CHARS]
        if len(context) > _MAX_CONTEXT_CHARS:
            ctx += "\n\n[Context truncated for length]"

        system = (
            "You are an expert research analyst. Your job is to produce accurate, "
            "well-structured research summaries grounded strictly in the provided sources. "
            "Never fabricate statistics, dates, or claims not present in the sources."
        )
        user = (
            f"RESEARCH TOPIC: {topic}\n\n"
            f"SOURCE EXCERPTS:\n{ctx}\n\n"
            f"INSTRUCTIONS:\n"
            f"Write a comprehensive research summary of 4–6 paragraphs covering:\n"
            f"1. Overview and background of the topic\n"
            f"2. Key methods, technologies, or approaches discussed\n"
            f"3. Main findings and results from the sources\n"
            f"4. Challenges, limitations, or open problems\n"
            f"5. Current trends and future directions\n\n"
            f"Rules:\n"
            f"- Cite sources inline as [Source 1], [Source 2], etc.\n"
            f"- Use only information present in the sources above.\n"
            f"- Write in clear, academic English.\n\n"
            f"SUMMARY:"
        )

        summary = self.llm.query(user, system_prompt=system, max_length=1000)
        logger.info("Summarizer: summary complete.")
        return summary

    def extract_insights(self, summary: str) -> list:
        """Returns a clean Python list of 6 specific insight strings."""
        system = (
            "You are a research analyst extracting precise, factual insights. "
            "Return only the numbered list — no preamble, no explanations."
        )
        user = (
            f"From the research summary below, extract exactly 6 key insights.\n"
            f"Each insight must be ONE specific, factual sentence (not vague).\n"
            f"Format: a plain numbered list only.\n\n"
            f"SUMMARY:\n{summary[:3000]}\n\n"
            f"KEY INSIGHTS:"
        )

        raw = self.llm.query(user, system_prompt=system, max_length=500)
        insights = self._parse_numbered_list(raw)
        logger.info(f"Summarizer: {len(insights)} insights extracted.")
        return insights

    @staticmethod
    def _parse_numbered_list(text: str) -> list:
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Remove leading "1.", "1)", "(1)", "- 1.", bullet chars
            cleaned = re.sub(r"^[\-\*\•]?\s*[\(\[]?\d+[\)\]\.]?\s*", "", line).strip()
            cleaned = re.sub(r"[*_]{1,2}", "", cleaned).strip()
            if len(cleaned) > 15:   # ignore very short/empty lines
                lines.append(cleaned)
        # Fallback: split by sentences if list parsing failed
        if not lines and text.strip():
            lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if len(s.strip()) > 15]
        return lines[:8]
