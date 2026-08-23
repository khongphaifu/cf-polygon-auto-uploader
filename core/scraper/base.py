from abc import ABC, abstractmethod
from typing import Optional
import requests
from bs4 import BeautifulSoup
from core.models import ProblemData


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

    def fetch_html(self, url: str) -> str:
        """Fetch raw HTML content from URL with retry."""
        import time
        last_err = None
        for attempt in range(1, 4):
            try:
                response = self.session.get(url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except Exception as e:
                last_err = e
                time.sleep(1.5 * attempt)
        raise last_err

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this scraper can handle the given URL."""
        pass

    @abstractmethod
    def scrape_raw(self, url: str) -> str:
        """Extract main problem text or HTML from URL."""
        pass
