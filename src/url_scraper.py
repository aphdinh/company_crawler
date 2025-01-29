import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import List
from utils import logger, get_openai_client


class CompanyURLScraper:
    def __init__(self, vc_url):
        self.vc_url = vc_url
        self.client = get_openai_client()

    def get_page_content(self, url: str) -> str:
        """Fetch and return the page content."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    def preprocess_html(self, html_content: str) -> List[str]:
        """Extract all href attributes in the HTML content."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            links = soup.find_all("a", href=True)
            hrefs = [link["href"] for link in links]
            logger.info(f"Extracted {len(hrefs)} hrefs from the HTML content.")
            return hrefs
        except Exception as e:
            logger.error(f"Error preprocessing HTML: {str(e)}")
            return []

    def extract_with_llm(self, hrefs: List[str], source_url: str) -> List[str]:
        """Use LLM to filter and extract company URLs from a list of hrefs."""
        try:
            hrefs_text = "\n".join(hrefs)
            prompt = f"""
            Given the following list of URLs extracted from a portfolio page, filter and return only those that point to portfolio company pages.
            The URLs may start with '/portfolio/', '/company/', '/investments/', or similar keywords, and they lead to individual company pages.
            
            Source URL: {source_url}
            Extracted URLs:
            {hrefs_text}
            
            Return ONLY the valid company URLs, one per line.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a URL filtering tool. Return only valid company URLs.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )

            # Process response
            extracted_urls = response.choices[0].message.content
            urls = [url.strip() for url in extracted_urls.splitlines() if url.strip()]

            # Validate and resolve URLs
            validated_urls = []
            for url in urls:
                if re.match(r"^(http|https|/)", url):
                    full_url = urljoin(source_url, url)
                    validated_urls.append(full_url)

            return validated_urls

        except Exception as e:
            logger.error(f"Error extracting URLs with LLM: {str(e)}")
            return []

    def get_company_urls(self, portfolio_url: str) -> list:
        """Get all company URLs from a VC portfolio page using LLM."""
        logger.info(f"Fetching company URLs from {portfolio_url}")
        html_content = self.get_page_content(portfolio_url)
        if not html_content:
            return []

        hrefs = self.preprocess_html(html_content)
        if not hrefs:
            logger.error("No hrefs found in the HTML content.")
            return []

        company_urls = self.extract_with_llm(hrefs, portfolio_url)
        company_urls.sort()

        logger.info(f"Found {len(company_urls)} company URLs")
        return company_urls


def main():
    portfolio_url = "https://www.sequoiacap.com/our-companies/"
    scraper = CompanyURLScraper(portfolio_url)
    company_urls = scraper.get_company_urls(portfolio_url)

    if not company_urls:
        logger.error("No company URLs found")
        return

    logger.info("Extracted Company URLs:")
    for url in company_urls:
        print(url)


if __name__ == "__main__":
    main()
