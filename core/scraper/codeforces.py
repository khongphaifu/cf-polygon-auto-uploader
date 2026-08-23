from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class CodeforcesScraper(BaseScraper):
    """Scraper for Codeforces problem statements."""

    def can_handle(self, url: str) -> bool:
        return "codeforces.com" in url and ("/problem/" in url or "/problemset/problem/" in url)

    def scrape_raw(self, url: str) -> str:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        
        problem_statement = soup.find("div", class_="problem-statement")
        if problem_statement:
            return problem_statement.get_text("\n", strip=True)
            
        return soup.get_text("\n", strip=True)
