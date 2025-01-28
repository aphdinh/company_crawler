import sys
import os
import argparse

# Add the project root to Python path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(project_root, 'src'))

from src.url_scraper import CompanyURLScraper
from src.info_scraper import CompanyInfoScraper
from src.utils import logger
from typing import List
from src.models import Company
from tqdm import tqdm

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Scrape company information from a portfolio URL")
    parser.add_argument(
        "--portfolio-url", 
        default="https://www.nvfund.com/portfolio/", 
        help="URL of the portfolio to scrape"
    )
    parser.add_argument(
        "--output", 
        default="companies.csv", 
        help="Output CSV filename"
    )
    
    # Parse arguments
    args = parser.parse_args()

    # Initialize the URL scraper
    url_scraper = CompanyURLScraper(args.portfolio_url)

    # Get company URLs from the portfolio page
    logger.info("Starting URL scraping...")
    company_urls = url_scraper.get_company_urls(args.portfolio_url)

    if not company_urls:
        logger.error("No company URLs found. Exiting...")
        return

    logger.info(f"Found {len(company_urls)} company URLs. Proceeding to extract information.")

    # Initialize the Info Scraper
    info_scraper = CompanyInfoScraper()

    # Extract company information from each URL
    companies: List[Company] = []
    
    for url in tqdm(company_urls, desc="Scraping Companies", unit="company"):
        try:
            company = info_scraper.extract_company_info(url, args.portfolio_url)
            if company:
                companies.append(company)
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}")

    if not companies:
        logger.error("No company information could be extracted. Exiting...")
        return

    # Save to a CSV file
    logger.info(f"Saving extracted information to {args.output}...")
    info_scraper.save_to_csv(companies, args.output)
    logger.info(f"Successfully saved information for {len(companies)} companies.")

if __name__ == "__main__":
    main()