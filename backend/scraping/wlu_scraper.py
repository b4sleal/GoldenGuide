import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from collections import defaultdict
import os
import json
from backend.scraping.parser import get_sitemap_urls, scrape_page

# Store scrapped pages
def scrape_all_and_save(output_folder="scraped_pages"):
    urls = get_sitemap_urls()
    category_contents = defaultdict(list)

    for i, url in enumerate(urls, start=1):
        # Determine top-level category
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            continue  # skip root URL (no useful content)
        category = path.split("/")[0]

        print(f"[{i}/{len(urls)}] Scraping: {url}")
        text = scrape_page(url)
        if text:
            category_contents[category].append({
                "url": url,
                "content": text
            })

    # Create folder if needed
    os.makedirs(output_folder, exist_ok=True)

    # Save one file per category
    for category, pages in category_contents.items():
        filename = os.path.join(output_folder, f"{category}.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Scraping complete. Saved {len(category_contents)} category files to '{output_folder}'.")
