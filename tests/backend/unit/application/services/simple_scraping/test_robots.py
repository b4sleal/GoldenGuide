"""robots.txt rules follow RFC 9309: group selection, longest match, wildcards, fetch outcomes."""
import pytest

from backend.application.services.simple_scraping.robots import RobotsRules

WLU = """
User-agent: *
Disallow: /search
Disallow: /calendar/*
Disallow: /arts
Allow: /arts/public
Disallow: /*.php$
"""


def allowed(text: str, path: str, token: str = "goldenguide") -> bool:
    return RobotsRules.parse(text, token).can_fetch(f"https://www.wlu.ca{path}")


@pytest.mark.parametrize("path, expected", [
    ("/about/index.html", True),
    ("/search", False),
    ("/searching", False),             # Rules are path prefixes.
    ("/calendar/2026/events", False),  # `*` matches any characters.
    ("/arts/index.html", False),
    ("/arts/public/page.html", True),  # The longer Allow beats the shorter Disallow.
    ("/contact.php", False),           # `$` anchors the end...
    ("/contact.php?x=1", True),        # ...so a query string no longer matches.
])
def test_wlu_style_rules(path, expected):
    assert allowed(WLU, path) is expected


def test_equal_length_allow_wins():
    assert allowed("User-agent: *\nDisallow: /page\nAllow: /page\n", "/page") is True


def test_empty_disallow_allows_everything():
    assert allowed("User-agent: *\nDisallow:\n", "/anything") is True


def test_a_group_naming_our_token_replaces_the_star_group():
    text = "User-agent: *\nDisallow: /\n\nUser-agent: GoldenGuide\nDisallow: /private\n"
    assert allowed(text, "/public") is True
    assert allowed(text, "/private") is False


def test_groups_for_the_same_agent_are_merged_and_share_lines():
    text = "User-agent: a\nUser-agent: *\nDisallow: /one\n\nUser-agent: *\nDisallow: /two\n"
    assert allowed(text, "/one") is False
    assert allowed(text, "/two") is False


def test_comments_and_case_of_fields_are_ignored():
    assert allowed("USER-AGENT: *   # everyone\nDISALLOW: /x # no\n", "/x/y") is False


def test_paths_compare_percent_decoded():
    assert allowed("User-agent: *\nDisallow: /a%20b\n", "/a b/c") is False


def test_old_calendar_years_are_blocked_but_current_ones_are_not():
    # Shape of academic-calendar.wlu.ca/robots.txt.
    text = "User-agent: *\nDisallow: /*&y=61$\n"
    rules = RobotsRules.parse(text, "goldenguide")
    assert rules.can_fetch("https://academic-calendar.wlu.ca/course.php?c=1&y=61") is False
    assert rules.can_fetch("https://academic-calendar.wlu.ca/course.php?c=1&y=94") is True


@pytest.mark.parametrize("status, expected", [(200, False), (404, True), (403, True), (500, False), (503, False)])
def test_fetch_outcome_policy(status, expected):
    # 2xx parses (here: disallow all); 4xx = no robots.txt (allow); 5xx = unreachable (disallow).
    rules = RobotsRules.for_status(status, "User-agent: *\nDisallow: /\n", "goldenguide")
    assert rules.can_fetch("https://www.wlu.ca/page.html") is expected
