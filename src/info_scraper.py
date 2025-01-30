import json
import re
import pandas as pd
from typing import List, Optional
from bs4 import BeautifulSoup

from base_scraper import BaseScraper
from utils import logger
from models import Company


class CompanyInfoScraper(BaseScraper):
    def __init__(self):
        """Initialize company info scraper."""
        super().__init__()

    def clean_html(self, html_content: str) -> str:
        """Clean and structure HTML content for LLM processing."""
        if not html_content:
            logger.warning("Received empty HTML content")
            return ""

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove non-content elements
            for tag in soup(
                ["script", "style", "nav", "header", "footer", "meta", "svg", "iframe"]
            ):
                tag.decompose()

            # Extract meaningful text with context
            lines = []
            priority_tags = ["h1", "h2", "h3", "h4", "p", "div", "article", "section"]
            priority_classes = [
                "company-name",
                "description",
                "about",
                "location",
                "industry",
            ]

            for element in soup.find_all(priority_tags):
                text = element.get_text(strip=True, separator=" ")
                if text and len(text) > 10:
                    tag_name = element.name
                    class_names = " ".join(element.get("class", []))

                    # Mark priority content
                    is_priority = any(
                        pc in class_names.lower() for pc in priority_classes
                    )
                    prefix = "[PRIORITY] " if is_priority else ""

                    lines.append(f"{prefix}{tag_name} {class_names}: {text}")

            cleaned_text = "\n".join(lines)
            logger.debug(f"Cleaned text length: {len(cleaned_text)}")
            return cleaned_text

        except Exception as e:
            logger.error(f"Error cleaning HTML: {e}")
            return ""

    def extract_with_llm(self, text: str, source_url: str) -> dict:
        """Extract structured company information using LLM."""
        try:
            max_text_length = 4000
            truncated_text = text[:max_text_length] if text else ""

            prompt = f"""
            Extract company information from this webpage content.
            The content may include priority-marked sections ([PRIORITY]) which are likely more relevant.

            Look for:
            1. Company name (often in h1 tags or elements with 'company-name' class)
            2. Company description (look for longer text blocks describing the company's activities)
            3. Company website URL (look for:
               - Links containing the company name
               - Company URLs in text content
               - External website references
               Must start with http:// or https://)
            4. Location (city, country, or region information)
            5. Domain/Industry (company's field of operation like "Fintech", "Healthcare", etc.)

            Source URL: {source_url}
            Content:
            {truncated_text}

            Return ONLY a JSON object with these exact fields:
            {{
                "name": "company name",
                "description": "company description",
                "url": "company website URL",
                "location": "company location",
                "domain": "industry/domain"
            }}
            """

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise data extraction tool specialized in identifying company information from web content. Focus on accuracy and completeness.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            # Process response
            cleaned_content = re.sub(
                r"```json|\```", "", response.choices[0].message.content.strip()
            )
            result = json.loads(cleaned_content)

            # Validate URL format
            if not result.get("url", "").startswith(("http://", "https://")):
                logger.warning(f"Invalid URL format: {result.get('url')}")
                result["url"] = source_url

            result["source"] = source_url
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in LLM response: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error in LLM extraction: {e}")
            return {}

    def extract_company_info(self, url: str, source_url: str) -> Optional[Company]:
        """Main method to extract company information from a URL."""
        logger.info(f"Processing company URL: {url}")

        try:
            # Fetch page content
            html_content = self.get_page_content(url)
            if not html_content:
                logger.warning(f"Failed to get content from {url}")
                return None

            # Clean and structure content
            cleaned_text = self.clean_html(html_content)
            if not cleaned_text:
                logger.warning(f"No meaningful content extracted from {url}")
                return None

            # Extract information using LLM
            extracted_info = self.extract_with_llm(cleaned_text, url)
            if not extracted_info:
                logger.warning(f"Failed to extract information from {url}")
                return None

            # Create Company object
            try:
                company = Company(
                    url=extracted_info.get("url") or url,
                    name=extracted_info.get("name"),
                    description=extracted_info.get("description"),
                    source=source_url,
                    location=extracted_info.get("location"),
                    domain=extracted_info.get("domain"),
                )

                logger.info(f"Successfully extracted information for {company.name}")
                return company

            except Exception as e:
                logger.error(f"Error creating Company object: {e}")
                return None

        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return None

    def save_to_csv(self, companies: List[Company], filename: str = "companies.csv"):
        """Save extracted company information to CSV."""
        try:
            if not companies:
                logger.warning("No companies to save")
                return

            # Convert to dictionaries
            company_dicts = [company.model_dump() for company in companies]

            # Create DataFrame
            df = pd.DataFrame(company_dicts)

            # Save to CSV
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(companies)} companies to {filename}")

        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")

    def scrape_single(self, url: str) -> Optional[Company]:
        """Convenience method to scrape a single company URL."""
        return self.extract_company_info(url, url)
