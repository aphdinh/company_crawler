from info_scraper import CompanyInfoScraper

scraper = CompanyInfoScraper()

company = scraper.scrape_single("https://www.notion.vc/portfolio/aikido-security")

if company:
    print(company)