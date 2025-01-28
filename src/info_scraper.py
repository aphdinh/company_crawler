from utils import logger, get_openai_client
from models import Company
import requests
from bs4 import BeautifulSoup
from typing import List, Optional
import pandas as pd
import json
import re

class CompanyInfoScraper:
    def __init__(self):
        self.client = get_openai_client()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def get_page_content(self, url: str) -> Optional[str]:
        """Fetch and return the page content."""
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    def clean_html(self, html_content: str) -> str:
        """Clean HTML content by removing scripts, styles, and unnecessary elements."""
        if not html_content:
            logger.error("Received empty HTML content")
            return ""
            
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 'meta']):
                element.decompose()
                
            # Get text while preserving some structure
            lines = []
            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div']):
                text = element.get_text(strip=True)
                if text:
                    tag_name = element.name
                    class_names = ' '.join(element.get('class', []))
                    lines.append(f"{tag_name} {class_names}: {text}")
            
            return '\n'.join(lines)
        except Exception as e:
            logger.error(f"Error cleaning HTML: {str(e)}")
            return ""

    def extract_with_llm(self, text: str, source_url: str) -> dict:
        """Use LLM to extract company information from text."""
        try:
            max_text_length = 4000
            truncated_text = text[:max_text_length] if text else ""
            
            prompt = self._create_extraction_prompt(truncated_text, source_url)
            
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=self._create_messages(prompt),
                temperature=0.2
            )

            return self._process_llm_response(response, source_url)

        except Exception as e:
            logger.error(f"Error in LLM extraction: {str(e)}")
            return self.create_empty_result(source_url)

    def _create_extraction_prompt(self, text: str, source_url: str) -> str:
        """Create the prompt for LLM extraction."""
        return f"""
        Extract company information from the following webpage content. 
        Look for:
        1. Company name (usually in headings or title)
        2. Company description (usually in paragraphs explaining what the company does)
        3. Company website URL (look for external links and return ONLY a valid URL starting with http:// or https://)
        4. Location (where the company is located, usually a country or a city)
        5. Domain (the industry or field the company operates in, such as "Finance", "Biotech", etc.)

        Source website: {source_url}
        
        Webpage content:
        {text}

        Return ONLY a valid JSON object with these fields:
        {{
            "name": "company name",
            "description": "main description of what the company does",
            "url": "company website URL (must start with http:// or https://)",
            "location": "where the company is located, either a country or a city",
            "domain": "the industry or field the company operates in"
        }}
        """

    def _create_messages(self, prompt: str) -> List[dict]:
        """Create messages for the LLM API."""
        return [
            {
                "role": "system", 
                "content": "You are a data extraction tool. Extract only the requested information and return it in JSON format."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ]

    def _process_llm_response(self, response, source_url: str) -> dict:
        """Process the LLM response and validate the result."""
        try:
            raw_content = response.choices[0].message.content
            cleaned_content = re.sub(r'```json|\```', '', raw_content).strip()
            
            result = json.loads(cleaned_content)
            
            # Validate required fields
            required_fields = ['name', 'description', 'url', 'location', 'domain']
            for field in required_fields:
                if field not in result:
                    logger.warning(f"Missing field in response: {field}")
                    result[field] = None

            # Validate URL format
            if result.get('url'):
                if not result['url'].startswith(('http://', 'https://')):
                    logger.warning(f"Invalid URL format: {result['url']}")
                    result['url'] = None
            
            result['source'] = source_url
            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return self.create_empty_result(source_url)

    def create_empty_result(self, source_url: str) -> dict:
        """Create an empty result dictionary with all required fields."""
        return {
            'name': None,
            'description': None,
            'url': None,
            'location': None,
            'domain': None,
            'source': source_url
        }

    def extract_company_info(self, url: str, source_url: str) -> Optional[Company]:
        """Extract company information using LLM."""
        logger.info(f"Extracting information from {url}")
        
        html_content = self.get_page_content(url)
        if not html_content:
            return None

        cleaned_text = self.clean_html(html_content)
        extracted_info = self.extract_with_llm(cleaned_text, source_url)
        
        if not extracted_info:
            return None

        try:
            company = Company(
                url=extracted_info.get('url', url),
                name=extracted_info.get('name'),
                description=extracted_info.get('description'),
                source=source_url,
                location=extracted_info.get('location'),
                domain=extracted_info.get('domain')
            )
            logger.info(f"Successfully extracted information for {company.name}")
            return company

        except Exception as e:
            logger.error(f"Error creating company object: {str(e)}")
            return None

    def save_to_csv(self, companies: List[Company], filename: str = 'companies.csv'):
        """Save extracted company information to CSV."""
        try:
            df = pd.DataFrame([company.model_dump() for company in companies])
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(companies)} companies to {filename}")
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}")