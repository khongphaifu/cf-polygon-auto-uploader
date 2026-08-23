from typing import List
from core.scraper.base import BaseScraper
from core.scraper.leetcode import LeetCodeScraper
from core.scraper.atcoder import AtCoderScraper
from core.scraper.codeforces import CodeforcesScraper
from core.scraper.cses import CSESScraper
from core.scraper.vnoj import VNOJScraper
from core.scraper.generic import GenericScraper

ALL_SCRAPERS: List[BaseScraper] = [
    LeetCodeScraper(),
    AtCoderScraper(),
    CodeforcesScraper(),
    CSESScraper(),
    VNOJScraper(),
    GenericScraper(),  # Must be last
]


def scrape_problem_text(url: str) -> str:
    """Find appropriate scraper and extract raw problem text."""
    for scraper in ALL_SCRAPERS:
        if scraper.can_handle(url):
            return scraper.scrape_raw(url)
    return GenericScraper().scrape_raw(url)
