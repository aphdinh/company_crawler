import os
import re
import json
import time
import pandas as pd
from typing import List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from utils import logger, get_openai_client
from models import Company

class CompanyInfoScraper:
    def __init__(self):
        """
        Initialize the scraper with Selenium WebDriver and OpenAI client.
        """
        self.client = get_openai_client()
        self.driver = self._setup_selenium_driver()
    
    def _setup_selenium_driver(self):
        """
        Set up and configure Selenium WebDriver with robust options.
        
        Returns:
            WebDriver: Configured Chrome WebDriver
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-software-rasterizer")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
            # Set implicit and page load timeouts
            driver.set_page_load_timeout(30)  # 30 seconds page load timeout
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    def get_page_content(self, url: str, timeout: int = 20) -> Optional[str]:
        """Fetch page content with advanced scrolling and waiting."""
        try:
            self.driver.get(url)

            # Wait for the body tag to load
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )

            # Scroll dynamically
            scroll_pause_time = 2
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while True:
                self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
                time.sleep(scroll_pause_time)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Fetch page source after scrolling
            page_source = self.driver.page_source
            return page_source

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def clean_html(self, html_content: str) -> str:
        """
        Clean HTML content by removing unnecessary elements.
        
        Args:
            html_content (str): Raw HTML content
        
        Returns:
            str: Cleaned text content
        """
        if not html_content:
            logger.warning("Received empty HTML content")
            return ""
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script, style, and other non-content tags
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'meta', 'svg', 'iframe']):
                element.decompose()
            
            # Extract meaningful text while preserving some context
            lines = []
            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div', 'article']):
                text = element.get_text(strip=True, separator=' ')
                if text and len(text) > 10:  # Filter out very short texts
                    tag_name = element.name
                    class_names = ' '.join(element.get('class', []))
                    lines.append(f"{tag_name} {class_names}: {text}")
            
            return '\n'.join(lines)
        
        except Exception as e:
            logger.error(f"Error cleaning HTML: {e}")
            return ""
    
    def extract_with_llm(self, text: str, source_url: str) -> dict:
        """Use LLM to extract company information from text."""
        try:
            max_text_length = 4000
            truncated_text = text[:max_text_length] if text else ""
            
            prompt = f"""
            Extract company information from the following webpage content. 
            Look for:
            1. Company name (usually in headings or title)
            2. Company description (usually in paragraphs explaining what the company does)
            3. Company website URL (look for external links and return ONLY a valid URL starting with http:// or https://)
            4. Location (where the company is located, usually a country or a city)
            5. Domain (the industry or field the company operates in, such as "Finance", "Biotech", etc.)

            Source website: {source_url}

            Webpage content:
            {truncated_text}

            Return ONLY a valid JSON object with these fields:
            {{
                "name": "company name",
                "description": "main description of what the company does",
                "url": "company website URL (must start with http:// or https://)",
                "location": "where the company is located, either a country or a city",
                "domain": "the industry or field the company operates in"
            }}

            Do not include any additional text or explanations. Only return the JSON object.
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a data extraction tool. Extract only the requested information and return it in JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            # Get the raw response content
            raw_content = response.choices[0].message.content

            # Remove Markdown code formatting
            cleaned_content = re.sub(r'```json|\```', '', raw_content).strip()

            # Parse the cleaned JSON content
            result = json.loads(cleaned_content)

            # Validate the URL
            if not result.get("url", "").startswith(("http://", "https://")):
                logger.warning(f"Invalid URL format: {result.get('url')}")
                result["url"] = ""  # Set URL to empty if invalid

            # Add source website to the result
            result['source'] = source_url
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response: {raw_content}")
            return {}

        except Exception as e:
            logger.error(f"Error in LLM extraction: {str(e)}")
            return {}
    
    def extract_company_info(self, url: str, source_url: str) -> Optional[Company]:
        """
        Main method to extract company information from a URL.
        """
        logger.info(f"Extracting information from {url}")
        
        try:
            # Fetch page content
            html_content = self.get_page_content(url)
            if not html_content:
                logger.warning(f"Failed to retrieve content from {url}")
                return None
            
            # Clean HTML
            cleaned_text = self.clean_html(html_content)
            if not cleaned_text:
                logger.warning(f"No meaningful content extracted from {url}")
                return None
            
            # Extract with LLM
            extracted_info = self.extract_with_llm(cleaned_text, source_url)
            
            # Prepare URL for Pydantic validation
            company_url = extracted_info.get('url') or url
            
            # Ensure URL is properly formatted for HttpUrl validation
            if company_url and not str(company_url).startswith(('http://', 'https://')):
                company_url = f'https://{company_url}'
            
            # Create Company object
            try:
                company = Company(
                    url=company_url,
                    name=extracted_info.get('name'),
                    description=extracted_info.get('description'),
                    source=source_url,
                    location=extracted_info.get('location'),
                    domain=extracted_info.get('domain')
                )
                
                logger.info(f"Successfully extracted information for {company.name}")
                return company
            except Exception as val_error:
                logger.error(f"Validation error creating Company object: {val_error}")
                return None
        
        except Exception as e:
            logger.error(f"Comprehensive extraction error for {url}: {e}")
            return None
    
    def __del__(self):
        """
        Cleanup method to close WebDriver when the object is destroyed.
        """
        if hasattr(self, 'driver'):
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error closing WebDriver: {e}")
    
    def save_to_csv(self, companies: List[Company], filename: str = 'companies.csv'):
        """
        Save extracted company information to CSV.
        """
        try:
            # Convert companies to dictionary for DataFrame
            company_dicts = [company.model_dump() for company in companies]
            
            # Create DataFrame
            df = pd.DataFrame(company_dicts)
            
            # Save to CSV
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(companies)} companies to {filename}")
        
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")

    def scrape_single(self, url: str) -> Optional[Company]:
        """
        Scrape information for a single URL.
        """
        return self.extract_company_info(url, url)