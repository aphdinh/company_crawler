from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import List
from utils import logger, get_openai_client
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time


class CompanyURLScraper:
    def __init__(self, vc_url):
        self.vc_url = vc_url
        self.client = get_openai_client()
        self.driver = self._setup_selenium_driver()

    def _setup_selenium_driver(self):
        """Set up and configure Selenium WebDriver."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-extensions")

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def get_page_content(self, url: str, timeout: int = 20) -> str:
        """Fetch page content using Selenium"""
        try:
            self.driver.get(url)

            # Wait for the body tag to load
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Scroll dynamically
            scroll_pause_time = 2
            last_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )

            while True:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
                time.sleep(scroll_pause_time)
                new_height = self.driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    break
                last_height = new_height

            return self.driver.page_source

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def __del__(self):
        """Cleanup method to close WebDriver."""
        if hasattr(self, "driver"):
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")

    # Rest of the methods remain the same
    def preprocess_html(self, html_content: str) -> List[str]:
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
    portfolio_url = "https://www.nvfund.com/portfolio/"
    scraper = CompanyURLScraper(portfolio_url)
    company_urls = scraper.get_company_urls(portfolio_url)

    if not company_urls:
        logger.error("No company URLs found")
        return

    logger.info(f"Extracted Company URLs: {len(company_urls)} companies")
    for url in company_urls:
        print(url)


if __name__ == "__main__":
    main()
