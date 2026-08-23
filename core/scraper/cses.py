from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class CSESScraper(BaseScraper):
    """Scraper for CSES problem set."""

    def can_handle(self, url: str) -> bool:
        return "cses.fi/problemset/task/" in url

    def scrape_raw(self, url: str) -> str:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        
        content = soup.find("div", class_="content")
        if content:
            return content.get_text("\n", strip=True)
            
        return soup.get_text("\n", strip=True)
