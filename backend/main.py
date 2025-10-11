from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.scraping.parser import get_sitemap_urls, get_sitemap_categories, scrape_page
from backend.scraping.wlu_scraper import scrape_all_and_save

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start storing all sites
# scrape_all_and_save()

# Test origin
@app.get("/")
def root():
    return {"message": "Backend running on localhost:8000"}

# See all WLU scrappable sites
@app.get("/sitemap")
def sitemap():
    urls = get_sitemap_urls()

    return urls

# See all categories of WLU student website
@app.get("/sitemapcategories")
def sitemap():
    urls = get_sitemap_categories()

    return urls

# View scrapped text from URL
@app.get("/getpage")
def getpage():
    url = "https://students.wlu.ca/academics/support-and-advising/academic-advising/science-advising/index.html"

    return scrape_page(url)