import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from collections import defaultdict

def scrape_page(url):
    response = requests.get(url)
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove scripts and styles
    for element in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        element.extract()

    # Get all visible text
    text = soup.get_text(separator="\n", strip=True)

    # Optional: remove empty lines
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


# Get the allowed URLS provided by WLU to scrap
def get_sitemap_urls():
    SITEMAP_URL = "https://students.wlu.ca/sitemap.xml"

    # Fetch sitemap
    response = requests.get(SITEMAP_URL)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch sitemap: {response.status_code}")

    # Parse XML
    soup = BeautifulSoup(response.text, "xml")
    urls = [loc.text for loc in soup.find_all("loc") if "/news/" not in loc.text] # filter noise

    return urls

# Helper function, list all sub urls for viewing or filtering data
# + Used to filter out news posts line 17 (3220 pages -> 2140 pages)
# + Use to group scraped data
def get_sitemap_categories():
    # Count pages per top-level category, excluding /news/
    category_counts = defaultdict(int)
    category_counts["Total"] = 0

    for url in get_sitemap_urls():
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        path_parts = path.split("/")
        if path_parts:
            category_counts["Total"] += 1
            category_counts[path_parts[0]] += 1

    return dict(category_counts)