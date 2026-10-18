from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class MarisaOJScraper(BaseScraper):
    """Scraper for MarisaOJ (marisaoj.com) - Vietnamese OJ protected by Cloudflare."""

    def can_handle(self, url: str) -> bool:
        return "marisaoj.com" in url

    def scrape_raw(self, url: str) -> str:
        html = self._fetch_with_cloudscraper(url)
        if not html:
            # Fallback to standard fetch with enhanced headers
            html = self._fetch_with_enhanced_headers(url)
        if not html:
            raise RuntimeError(f"MarisaOJScraper: Cannot fetch content from {url}")

        soup = BeautifulSoup(html, "html.parser")

        # Remove irrelevant tags
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        # Try common MarisaOJ content selectors
        selectors = [
            ("div", {"class": "problem-content"}),
            ("div", {"class": "problem-body"}),
            ("div", {"class": "statement"}),
            ("div", {"id": "problem-body"}),
            ("div", {"id": "problem-statement"}),
            ("div", {"class": "content"}),
            ("div", {"class": "problem"}),
            ("article", {}),
            ("main", {}),
        ]

        for tag_name, attrs in selectors:
            element = soup.find(tag_name, attrs) if attrs else soup.find(tag_name)
            if element:
                text = element.get_text("\n", strip=True)
                if len(text) > 100:
                    return text

        # Final fallback: body text
        body = soup.find("body")
        if body:
            return body.get_text("\n", strip=True)

        return soup.get_text("\n", strip=True)

    def _fetch_with_cloudscraper(self, url: str) -> str:
        """Bypass Cloudflare using cloudscraper library."""
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
            response = scraper.get(url, timeout=30)
            response.encoding = response.apparent_encoding or "utf-8"
            if response.status_code == 200:
                return response.text
            return ""
        except ImportError:
            return ""
        except Exception:
            return ""

    def _fetch_with_enhanced_headers(self, url: str) -> str:
        """Fallback: fetch with enhanced browser-like headers."""
        try:
            import requests
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            }
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=20)
            response.encoding = response.apparent_encoding or "utf-8"
            if response.status_code == 200:
                return response.text
            return ""
        except Exception:
            return ""
