from pathlib import Path
from typing import List
from urllib.parse import urlparse
import requests
from core.scraper.base import BaseScraper, ScrapedProblem
from core.scraper.leetcode import LeetCodeScraper
from core.scraper.atcoder import AtCoderScraper
from core.scraper.codeforces import CodeforcesScraper
from core.scraper.cses import CSESScraper
from core.scraper.vnoj import VNOJScraper
from core.scraper.marisaoj import MarisaOJScraper
from core.scraper.generic import GenericScraper

ALL_SCRAPERS: List[BaseScraper] = [
    LeetCodeScraper(),
    AtCoderScraper(),
    CodeforcesScraper(),
    CSESScraper(),
    VNOJScraper(),
    MarisaOJScraper(),
    GenericScraper(),  # Must be last
]


def scrape_problem_data(source: str) -> ScrapedProblem:
    """Extract problem data from a URL or local file (.pdf, .png, .jpg, .webp, .txt, .md)."""
    source_clean = source.strip()
    local_path = Path(source_clean)
    if local_path.exists() and local_path.is_file():
        suffix = local_path.suffix.lower()
        if suffix == ".pdf":
            return ScrapedProblem(
                raw_text=f"[Local PDF: {local_path.name}]",
                pdf_bytes=local_path.read_bytes(),
                pdf_url=str(local_path.resolve()),
                title=local_path.stem,
            )
        elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
            mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else f"image/{suffix.lstrip('.')}"
            return ScrapedProblem(
                raw_text=f"[Local Image: {local_path.name}]",
                image_bytes=local_path.read_bytes(),
                image_mime=mime,
                title=local_path.stem,
            )
        else:
            return ScrapedProblem(
                raw_text=local_path.read_text(encoding="utf-8", errors="replace"),
                title=local_path.stem,
            )

    parsed_url = urlparse(source_clean)
    if parsed_url.scheme in ("http", "https") and parsed_url.path.lower().endswith(".pdf"):
        resp = requests.get(source_clean, timeout=25, headers=GenericScraper().headers)
        resp.raise_for_status()
        return ScrapedProblem(
            raw_text=f"[Direct PDF URL: {source_clean}]",
            pdf_bytes=resp.content,
            pdf_url=source_clean,
            title=Path(parsed_url.path).stem,
        )

    for scraper in ALL_SCRAPERS:
        if scraper.can_handle(source_clean):
            return scraper.scrape(source_clean)
    return GenericScraper().scrape(source_clean)


def scrape_problem_text(url: str) -> str:
    """Find appropriate scraper and extract raw problem text."""
    return scrape_problem_data(url).raw_text
