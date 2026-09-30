import re
from backend.models.llm_loader import LLMLoader
from backend.utils.logger import logger


class VerifierAgent:
    def __init__(self):
        self.llm = LLMLoader()

    def run(self, topic: str, findings: str) -> dict:
        logger.info(f"Verifier: fact-checking findings for '{topic}'")

        system = (
            "You are a rigorous fact-checking assistant. "
            "Your task is to review research findings for accuracy, consistency, and completeness. "
            "Remove unsupported claims. Preserve well-evidenced information. Be precise."
        )
        user = (
            f"TOPIC: {topic}\n\n"
            f"FINDINGS TO VERIFY:\n{findings[:4000]}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Remove duplicate or contradictory statements.\n"
            f"2. Flag and correct any clearly inaccurate claims.\n"
            f"3. Preserve all well-supported findings.\n"
            f"4. Improve clarity and logical flow where needed.\n"
            f"5. On the LAST line write exactly: CONFIDENCE: <integer 0-100>\n"
            f"   where 100 = highly reliable, 0 = unreliable.\n\n"
            f"VERIFIED FINDINGS:"
        )

        raw = self.llm.query(user, system_prompt=system, max_length=1000)
        verified, confidence = self._parse(raw, findings)
        logger.info(f"Verifier: confidence = {confidence}%")
        return {"verified_content": verified, "confidence_score": confidence}

    @staticmethod
    def _parse(raw: str, fallback: str) -> tuple:
        confidence = 78  # default
        verified   = raw.strip()

        match = re.search(r"CONFIDENCE[:\s]+(\d{1,3})", raw, re.IGNORECASE)
        if match:
            try:
                confidence = max(0, min(100, int(match.group(1))))
            except ValueError:
                pass
            verified = raw[: match.start()].strip()

        return (verified or fallback), confidence
