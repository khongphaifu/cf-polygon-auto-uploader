from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class VNOJScraper(BaseScraper):
    """Scraper for VNOJ (vnoi.info) problems."""

    def can_handle(self, url: str) -> bool:
        return "oj.vnoi.info/problem/" in url or "vnoi.info/problems/" in url

    def scrape_raw(self, url: str) -> str:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        
        # VNOJ task content is typically inside div with class "content-description" or "problem-body"
        problem_content = soup.find("div", class_="problem-body") or soup.find("div", class_="content-description")
        if problem_content:
            return problem_content.get_text("\n", strip=True)
            
        main_content = soup.find("main") or soup.find("div", id="content")
        if main_content:
            return main_content.get_text("\n", strip=True)
            
        return soup.get_text("\n", strip=True)
