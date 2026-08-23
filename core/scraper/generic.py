from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class GenericScraper(BaseScraper):
    """Fallback scraper that extracts main content from any webpage."""

    def can_handle(self, url: str) -> bool:
        return True

    def scrape_raw(self, url: str) -> str:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        # Remove irrelevant tags
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            element.decompose()

        # Try to find main content containers
        main_tags = soup.find_all(["article", "main", "div[role='main']", "#content", ".problem-statement", ".content"])
        if main_tags:
            # Pick the container with the largest text
            best_tag = max(main_tags, key=lambda t: len(t.get_text()))
            text = best_tag.get_text("\n", strip=True)
            if len(text) > 100:
                return text

        # Fallback to body
        body = soup.find("body")
        if body:
            return body.get_text("\n", strip=True)

        return soup.get_text("\n", strip=True)
