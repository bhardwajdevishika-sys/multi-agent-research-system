"""
CitationAgent — generates properly formatted APA citations from real source metadata.
Uses actual title, URL, and domain extracted by WebSearchService.
"""

from datetime import datetime
from urllib.parse import urlparse
from backend.utils.logger import logger


class CitationAgent:
    def run(self, sources: list, style: str = "APA") -> list:
        logger.info(f"CitationAgent: generating {style} citations for {len(sources)} source(s).")
        citations = []
        year = datetime.now().year

        for i, source in enumerate(sources, 1):
            if not isinstance(source, dict):
                continue

            title  = source.get("title",  "").strip() or f"Source {i}"
            url    = source.get("url",    "#").strip()
            author = source.get("author", "").strip()
            domain = source.get("domain", self._domain(url))

            # Use domain as author if no real author name available
            if not author or author.lower() in ("system", "tavily ai", ""):
                author = domain or f"Source {i}"

            # Remove trailing numbers / generic suffixes from title
            clean_title = title.rstrip("0123456789 -–—")

            if style == "APA":
                citation = f"{author}. ({year}). {clean_title}. Retrieved from {url}"
            elif style == "IEEE":
                citation = f'{author}, "{clean_title}," {year}. [Online]. Available: {url}'
            elif style == "MLA":
                citation = f'{author}. "{clean_title}." Web. {year}. <{url}>.'
            else:
                citation = f"{author}. {clean_title}. {year}. {url}"

            citations.append(citation)
            logger.debug(f"  [{i}] {citation}")

        return citations

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return urlparse(url).netloc.replace("www.", "")
        except Exception:
            return url
