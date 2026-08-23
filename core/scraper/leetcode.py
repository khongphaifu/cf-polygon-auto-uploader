import re
from typing import Optional
import requests
from bs4 import BeautifulSoup
from core.scraper.base import BaseScraper


class LeetCodeScraper(BaseScraper):
    """Scraper for LeetCode problems using GraphQL API."""

    def can_handle(self, url: str) -> bool:
        return "leetcode.com/problems/" in url

    def extract_title_slug(self, url: str) -> Optional[str]:
        match = re.search(r"leetcode\.com/problems/([^/?#]+)", url)
        if match:
            return match.group(1)
        return None

    def scrape_raw(self, url: str) -> str:
        slug = self.extract_title_slug(url)
        if not slug:
            # Fallback to direct HTML
            return self.fetch_html(url)

        graphql_url = "https://leetcode.com/graphql"
        query = """
        query getQuestionDetail($titleSlug: String!) {
            question(titleSlug: $titleSlug) {
                questionId
                questionFrontendId
                title
                content
                difficulty
                exampleTestcases
                sampleTestCase
            }
        }
        """
        payload = {
            "query": query,
            "variables": {"titleSlug": slug},
        }

        try:
            resp = self.session.post(graphql_url, json=payload, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                q = data.get("data", {}).get("question")
                if q:
                    raw_content = q.get("content", "")
                    # Convert HTML content to readable text / keep equations
                    soup = BeautifulSoup(raw_content, "html.parser")
                    text_content = soup.get_text("\n", strip=True)
                    return f"Title: {q.get('title')}\nDifficulty: {q.get('difficulty')}\nFrontend ID: {q.get('questionFrontendId')}\n\nContent:\n{text_content}\n\nExample Test Cases:\n{q.get('exampleTestcases')}"
        except Exception:
            pass

        # Fallback to HTML
        return self.fetch_html(url)
