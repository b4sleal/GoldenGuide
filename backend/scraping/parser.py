import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from collections import defaultdict

def scrape_page(url):
    """
    Clean pages so embedding focuses on meaningful content
    Returns the cleaned content
    """
    response = requests.get(url)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove scripts, styles, we only want the university page text
    for element in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        element.extract()

    # Get all visible text
    text = soup.get_text(separator="\n", strip=True)

    # Optional: remove empty lines
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

# Get the allowed URLS provided by WLU to scrap
def get_sitemap_urls():
    """
    Uses official WLU sitemap for authorized scraping
    Returns a list of urls
    """
    SITEMAP_URL = "https://students.wlu.ca/sitemap.xml"

    # Fetch sitemap
    response = requests.get(SITEMAP_URL)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch sitemap: {response.status_code}")

    # Parse XML
    soup = BeautifulSoup(response.text, "xml")
    # Links stored in a loc attribute in the sitemap xml
    # Filer out news posts (3220 pages -> 2140 pages)
    urls = [loc.text for loc in soup.find_all("loc") if "/news/" not in loc.text]

    return urls

def get_sitemap_categories():
    """
    List all sub urls for viewing or filtering data
    Groups URLs by top-level category
    Returns a dict: {"Total": 2140, "Academic": 1000, ...}
    """
    category_counts = defaultdict(int)
    category_counts["Total"] = 0

    # Get all URLs and parse each category
    for url in get_sitemap_urls():
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        path_parts = path.split("/")

        if path_parts:
            category_counts["Total"] += 1
            category_counts[path_parts[0]] += 1

    return dict(category_counts)