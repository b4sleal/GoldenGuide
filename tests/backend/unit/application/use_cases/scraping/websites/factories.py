"""Website settings as configured for wlu.ca and scholars.wlu.ca (see configs/catalogs/scraping)."""
from backend.domain.settings.scraping import WebsiteScrapeSettings

IGNORED_EXTENSIONS = (".pdf", ".docx", ".jpg")

WLU = WebsiteScrapeSettings(
    site_name="wlu_ca",
    allowed_domains=("www.wlu.ca", "wlu.ca"),
    sitemap_urls=("https://www.wlu.ca/sitemap.xml",),
    seed_urls=("https://www.wlu.ca/home.html",),
    content_selector="main",
    remove_selectors=("header", "footer"),
    excluded_path_patterns=("/news/",),
    title_suffix=" | Wilfrid Laurier University",
)

SCHOLARS = WebsiteScrapeSettings(
    site_name="scholars_wlu",
    allowed_domains=("scholars.wlu.ca",),
    sitemap_urls=("https://scholars.wlu.ca/siteindex.xml",),
    content_selector="#content",
    excluded_path_patterns=("/viewcontent.cgi",),
    title_suffix=" | Research at Wilfrid Laurier University",
)
