from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import time
import requests
from bs4 import BeautifulSoup
from core.models import ProblemData


@dataclass
class ScrapedProblem:
    """Holds extracted problem text and optional document/image binary (e.g. PDF, PNG)."""
    raw_text: str
    pdf_bytes: Optional[bytes] = None
    pdf_url: Optional[str] = None
    image_bytes: Optional[bytes] = None
    image_mime: Optional[str] = None
    title: Optional[str] = None


class BaseScraper(ABC):
    """Abstract base class for problem statement scrapers."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
        }
        self.session = requests.Session()

    def _fetch_with_cloudscraper(self, url: str) -> Optional[str]:
        """Fallback fetch using cloudscraper to bypass Cloudflare / bot checks."""
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            resp = scraper.get(url, timeout=max(self.timeout, 30))
            resp.encoding = resp.apparent_encoding or "utf-8"
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        return None

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML content from URL with retry and automatic cloudscraper fallback."""
        last_err = None
        for attempt in range(1, 3):
            try:
                response = self.session.get(url, headers=self.headers, timeout=self.timeout)
                if response.status_code in (403, 503):
                    cf_html = self._fetch_with_cloudscraper(url)
                    if cf_html:
                        return cf_html
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                text = response.text
                if "just a moment..." in text.lower() or "cf-browser-verification" in text.lower():
                    cf_html = self._fetch_with_cloudscraper(url)
                    if cf_html:
                        return cf_html
                return text
            except Exception as e:
                last_err = e
                time.sleep(1.0 * attempt)

        cf_html = self._fetch_with_cloudscraper(url)
        if cf_html:
            return cf_html
        raise last_err

    def clean_html_preserve_math(self, element) -> str:
        """Extract text from a BeautifulSoup element while preserving exponents, subscripts, and <pre> blocks."""
        if element is None:
            return ""
        soup = BeautifulSoup(str(element), "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        for sup in soup.find_all("sup"):
            txt = sup.get_text(strip=True)
            if txt:
                sup.replace_with(f"^{{{txt}}}")
        for sub in soup.find_all("sub"):
            txt = sub.get_text(strip=True)
            if txt:
                sub.replace_with(f"_{{{txt}}}")

        pre_blocks = {}
        for idx, pre in enumerate(soup.find_all("pre")):
            for br in pre.find_all("br"):
                br.replace_with("\n")
            for div in pre.find_all("div"):
                div.insert_after("\n")
            block_text = pre.get_text()
            token = f"__PRE_BLOCK_{idx}__"
            pre_blocks[token] = f"\n```\n{block_text.strip()}\n```\n"
            pre.replace_with(f"\n{token}\n")

        extracted = soup.get_text("\n", strip=True)
        import re
        extracted = re.sub(r"\s*\n\s*(\^\{[^}]*\}|_\{[^}]*\})", r"\1", extracted)
        extracted = re.sub(r"(\^\{[^}]*\}|_\{[^}]*\})\n+(?=[^\s])", r"\1 ", extracted)
        extracted = re.sub(r"(\^\{[^}]*\}|_\{[^}]*\}) ([.,;:)\]\}])", r"\1\2", extracted)
        for token, block in pre_blocks.items():
            extracted = extracted.replace(token, block)
        return extracted

    def scrape(self, url: str) -> ScrapedProblem:
        """Extract problem statement text or document from URL."""
        raw_text = self.scrape_raw(url)
        return ScrapedProblem(raw_text=raw_text)

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this scraper can handle the given URL."""
        pass

    @abstractmethod
    def scrape_raw(self, url: str) -> str:
        """Extract main problem text or HTML from URL."""
        pass
