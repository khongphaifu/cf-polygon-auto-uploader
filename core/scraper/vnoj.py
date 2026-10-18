from typing import Optional
import urllib.parse
from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper, ScrapedProblem


class VNOJScraper(BaseScraper):
    """Scraper for VNOJ (vnoi.info) problems, supporting both HTML text and embedded PDF statements."""

    def can_handle(self, url: str) -> bool:
        return "oj.vnoi.info/problem/" in url or "vnoi.info/problems/" in url or "oj.vnoi.info/problems/" in url

    def scrape(self, url: str) -> ScrapedProblem:
        html = self.fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        # 1. Check for embedded PDF statement
        pdf_url = None

        # Pattern A: <object data="...pdf">
        obj = (
            soup.find("object", id="pdfContainer")
            or soup.find("object", type="application/pdf")
            or soup.find("object", attrs={"data": lambda v: v and ".pdf" in v.lower()})
        )
        if obj and obj.get("data"):
            pdf_url = obj.get("data")

        # Pattern B: <iframe src="...pdf">
        if not pdf_url:
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src", "")
                if ".pdf" in src.lower():
                    pdf_url = src
                    break

        # Pattern C: <a href="...pdf">
        if not pdf_url:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text().lower()
                if ".pdf" in href.lower() and ("statement" in text or "đề bài" in text or "download" in text or "pdf" in href.lower()):
                    pdf_url = href
                    break

        # If PDF URL is found, download the PDF content
        if pdf_url:
            pdf_url = urllib.parse.urljoin(url, pdf_url)
            try:
                pdf_res = self.session.get(pdf_url, headers=self.headers, timeout=self.timeout)
                if pdf_res.status_code == 200 and len(pdf_res.content) > 100:
                    page_title = None
                    h1 = soup.find("h1") or soup.find("h2")
                    if h1:
                        page_title = h1.get_text(strip=True)
                    elif soup.title and soup.title.string:
                        page_title = soup.title.string.split("-")[0].strip()

                    return ScrapedProblem(
                        raw_text=f"[VNOJ PDF Statement: {pdf_url}]\nTitle: {page_title or 'Problem'}",
                        pdf_bytes=pdf_res.content,
                        pdf_url=pdf_url,
                        title=page_title,
                    )
            except Exception:
                pass

        # 2. Fallback to standard HTML text extraction
        raw_text = self.scrape_raw(url, html=html, soup=soup)
        return ScrapedProblem(raw_text=raw_text)

    def scrape_raw(self, url: str, html: Optional[str] = None, soup: Optional[BeautifulSoup] = None) -> str:
        if soup is None:
            if html is None:
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
