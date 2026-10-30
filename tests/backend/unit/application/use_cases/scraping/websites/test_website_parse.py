"""A website page keeps only its content root's text: no site header, footer or navigation."""
from backend.application.use_cases.scraping.websites.parse import parse_website_page
from tests.backend.unit.application.use_cases.scraping.websites.factories import SCHOLARS, WLU

WLU_PAGE = """<html><head><title>Working at Laurier | Wilfrid Laurier University</title></head><body>
<header class="site__header"><nav><a href="/apply">Apply</a> Menu</nav></header>
<main class="row site__content">
  <header><p>Page banner</p></header>
  <h1>Working at Laurier</h1>
  <p>We are a community. See <a href="/careers/index.html">career opportunities</a>.</p>
  <footer><p>Section footer</p></footer>
</main>
<footer class="site__footer">75 University Ave W</footer>
</body></html>"""


def test_wlu_page_keeps_main_without_header_and_footer():
    page = parse_website_page(WLU_PAGE, "https://www.wlu.ca/about/working-at-laurier/index.html", WLU)

    assert page.title == "Working at Laurier"
    assert "We are a community." in page.content
    for noise in ("Menu", "Apply", "Page banner", "Section footer", "75 University"):
        assert noise not in page.content
    assert page.links == ["https://www.wlu.ca/careers/index.html"]
    assert "[career opportunities](@@1@@)" in page.content  # Same citation format as the calendar.


def test_title_falls_back_to_the_document_title_without_the_site_suffix():
    html = "<title>Benefits | Wilfrid Laurier University</title><main><p>Dental and health.</p></main>"
    assert parse_website_page(html, "https://www.wlu.ca/benefits.html", WLU).title == "Benefits"


def test_scholars_uses_the_content_div():
    html = """<title>Theses | Research at Wilfrid Laurier University</title>
    <div id="header">Scholars Commons</div><div id="content"><h1>Theses and Dissertations</h1><p>Browse.</p></div>"""
    page = parse_website_page(html, "https://scholars.wlu.ca/etd/", SCHOLARS)

    assert page.title == "Theses and Dissertations"
    assert "Browse." in page.content
    assert "Scholars Commons" not in page.content


def test_page_without_the_content_root_is_none():
    assert parse_website_page("<html><body><p>Just a moment...</p></body></html>", "https://www.wlu.ca/x", WLU) is None
