from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional
import time
from utils import logger, get_openai_client


class BaseScraper:
    def __init__(self):
        """Initialize base scraper with Selenium WebDriver and OpenAI client."""
        self.client = get_openai_client()
        self.driver = self._setup_selenium_driver()

    def _setup_selenium_driver(self):
        """Set up and configure Selenium WebDriver with robust options."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def _wait_for_page_load(self, timeout: int = 20) -> bool:
        """Wait for critical page elements to load."""
        try:
            # Wait for body
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Wait for main content containers
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "main, article, .content, #content, .company-profile, .portfolio-company",
                    )
                )
            )

            return True
        except Exception as e:
            logger.error(f"Error waiting for page load: {e}")
            return False

    def get_page_content(self, url: str, timeout: int = 20) -> Optional[str]:
        """Fetch page content with retry mechanism and dynamic scrolling."""
        try:
            logger.info(f"Fetching content from: {url}")
            self.driver.get(url)

            if not self._wait_for_page_load(timeout):
                return None

            # Dynamic scrolling
            scroll_pause_time = 2
            last_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )

            while True:
                # Scroll to bottom
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
                time.sleep(scroll_pause_time)

                new_height = self.driver.execute_script(
                    "return document.body.scrollHeight"
                )
                if new_height == last_height:
                    break
                last_height = new_height

            page_source = self.driver.page_source
            if len(page_source) < 1000:  # Basic content validation
                logger.warning(f"Page source too short for {url}")
                return None

            return page_source

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_with_llm(self, text: str, prompt: str) -> dict:
        """Base method for LLM extraction"""
        raise NotImplementedError("Subclasses must implement extract_with_llm")

    def __del__(self):
        """Cleanup method to close WebDriver."""
        if hasattr(self, "driver"):
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")
