from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import List, Set

from base_scraper import BaseScraper
from utils import logger


class CompanyURLScraper(BaseScraper):
    def __init__(self, vc_url: str):
        """Initialize URL scraper with VC portfolio URL."""
        super().__init__()
        self.vc_url = vc_url

    def preprocess_html(self, html_content: str) -> Set[str]:
        """Extract URLs from all possible clickable elements and attributes."""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            hrefs = set()  # Using set to avoid duplicates

            # 1.Elements with href attribute
            elements_with_href = soup.find_all(attrs={"href": True})
            hrefs.update(element["href"] for element in elements_with_href)

            # 2. Elements with onclick attribute
            elements_with_onclick = soup.find_all(attrs={"onclick": True})
            for element in elements_with_onclick:
                onclick = element["onclick"]
                # Look for any URL pattern in onclick
                url_matches = re.findall(
                    r"['\"](https?://[^'\"]+|/[^'\"]+)['\"]", onclick
                )
                hrefs.update(url_matches)

            # 3. Elements with data-url or similar attributes
            url_attributes = [
                "data-url",
                "data-href",
                "data-link",
                "data-redirect",
                "data-navigate",
            ]
            for attr in url_attributes:
                elements = soup.find_all(attrs={attr: True})
                hrefs.update(element[attr] for element in elements)

            # 4. URLs in script tags
            scripts = soup.find_all("script", string=True)
            for script in scripts:
                # Look for URL patterns in script content
                url_matches = re.findall(
                    r"['\"](https?://[^'\"]+|/[^'\"]+)['\"]", script.string
                )
                hrefs.update(url_matches)

            logger.debug(f"Found {len(hrefs)} potential URLs")
            return hrefs

        except Exception as e:
            logger.error(f"Error preprocessing HTML: {str(e)}")
            logger.error(f"Error details: {str(e.__class__.__name__)}: {str(e)}")
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
            
            Return ONLY valid company URLs, one per line.
            Do not include navigation links, asset URLs, or general pages.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a URL filtering tool specialized in identifying portfolio company pages from VC websites.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            # Process response
            extracted_urls = response.choices[0].message.content
            urls = [url.strip() for url in extracted_urls.splitlines() if url.strip()]

            # Resolve relative URLs and validate
            validated_urls = []
            for url in urls:
                if re.match(r"^(http|https|/)", url):
                    full_url = urljoin(source_url, url)
                    validated_urls.append(full_url)

            # Remove duplicates while preserving order
            unique_urls = list(dict.fromkeys(validated_urls))

            logger.info(f"Extracted {len(unique_urls)} unique company URLs")
            return unique_urls

        except Exception as e:
            logger.error(f"Error extracting URLs with LLM: {str(e)}")
            return []

    def get_company_urls(self, portfolio_url: str) -> List[str]:
        """Main method to extract company URLs from portfolio page."""
        logger.info(f"Processing portfolio page: {portfolio_url}")

        try:
            # Fetch page content
            html_content = self.get_page_content(portfolio_url)
            if not html_content:
                logger.error("Failed to fetch page content")
                return []

            # Extract all potential URLs
            hrefs = self.preprocess_html(html_content)
            if not hrefs:
                logger.error("No URLs found in page content")
                return []

            # Filter for company URLs using LLM
            company_urls = self.extract_with_llm(list(hrefs), portfolio_url)

            # Sort for consistent output
            company_urls.sort()

            logger.info(f"Successfully extracted {len(company_urls)} company URLs")
            return company_urls

        except Exception as e:
            logger.error(f"Error processing portfolio page: {e}")
            return []


def main():
    """Command line interface for URL scraper."""
    portfolio_url = "https://www.nvfund.com/portfolio/"
    scraper = CompanyURLScraper(portfolio_url)

    try:
        company_urls = scraper.get_company_urls(portfolio_url)

        if not company_urls:
            logger.error("No company URLs found")
            return

        logger.info(f"Found {len(company_urls)} companies")
        for url in company_urls:
            print(url)

    except Exception as e:
        logger.error(f"Error in main execution: {e}")


if __name__ == "__main__":
    main()
