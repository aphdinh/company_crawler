import sys
import os

# Add the project root to Python path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.url_scraper import CompanyURLScraper
from src.info_scraper import CompanyInfoScraper
from src.utils import logger
from typing import List
from src.models import Company

def main():
    # Define the portfolio URL
    portfolio_url = "https://www.blackbird.vc/portfolio"

    # Initialize the URL scraper
    url_scraper = CompanyURLScraper(portfolio_url)

    # Get company URLs from the portfolio page
    logger.info("Starting URL scraping...")
    company_urls = url_scraper.get_company_urls(portfolio_url)

    if not company_urls:
        logger.error("No company URLs found. Exiting...")
        return

    logger.info(f"Found {len(company_urls)} company URLs. Proceeding to extract information.")

    # Initialize the Info Scraper
    info_scraper = CompanyInfoScraper()

    # Extract company information from each URL
    companies: List[Company] = []
    for url in company_urls:
        try:
            company = info_scraper.extract_company_info(url, portfolio_url)
            if company:
                companies.append(company)
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")

    if not companies:
        logger.error("No company information could be extracted. Exiting...")
        return

    # Save the extracted information to a CSV file
    output_file = "companies.csv"
    logger.info(f"Saving extracted information to {output_file}...")
    info_scraper.save_to_csv(companies, output_file)
    logger.info(f"Successfully saved information for {len(companies)} companies.")

if __name__ == "__main__":
    main()
