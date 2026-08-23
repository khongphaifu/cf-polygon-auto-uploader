from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class AtCoderScraper(BaseScraper):
    """Scraper for AtCoder problems."""

    def can_handle(self, url: str) -> bool:
        return "atcoder.jp/contests/" in url and "/tasks/" in url

    def scrape_raw(self, url: str) -> str:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for English task statement first
        task_statement = soup.find("div", id="task-statement")
        if task_statement:
            en_section = task_statement.find("span", class_="lang-en")
            if en_section:
                return en_section.get_text("\n", strip=True)
            return task_statement.get_text("\n", strip=True)
            
        # Fallback to main container
        main_container = soup.find("div", id="main-container")
        if main_container:
            return main_container.get_text("\n", strip=True)
            
        return soup.get_text("\n", strip=True)
