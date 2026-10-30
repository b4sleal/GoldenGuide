from backend.application.services.router.evidence.academic_links import (
    AcademicLinkResolver,
)

LINKS = [
    "https://academic-calendar.wlu.ca/course.php?c=100",
    "https://academic-calendar.wlu.ca/course.php?c=200",
    "https://academic-calendar.wlu.ca/course.php?c=300",
]


def test_first_link_uses_index_zero():
    result = AcademicLinkResolver.resolve(
        "[CP104](@@1@@)",
        LINKS,
    )

    assert result == f"[CP104]({LINKS[0]})"


def test_second_link_uses_index_one():
    result = AcademicLinkResolver.resolve(
        "[CP164](@@2@@)",
        LINKS,
    )

    assert result == f"[CP164]({LINKS[1]})"


def test_escaped_markdown_links():
    result = AcademicLinkResolver.resolve(
        r"[CP213]\(@@3@@)",
        LINKS,
    )

    assert result == f"[CP213]({LINKS[2]})"


def test_multiple_links_preserve_indices():
    result = AcademicLinkResolver.resolve(
        "[A](@@3@@) or [B](@@1@@)",
        LINKS,
    )

    assert result == (
        f"[A]({LINKS[2]}) or [B]({LINKS[0]})"
    )


def test_unknown_index_does_not_create_broken_url():
    result = AcademicLinkResolver.resolve(
        "[Unknown](@@99@@)",
        LINKS,
    )

    assert result == "[Unknown]"


def test_zero_is_not_a_valid_placeholder_index():
    result = AcademicLinkResolver.resolve(
        "[Unknown](@@0@@)",
        LINKS,
    )

    assert result == "[Unknown]"


def test_invalid_urls_are_not_rendered():
    result = AcademicLinkResolver.resolve(
        "[Unknown](@@1@@)",
        ["null"],
    )

    assert result == "[Unknown]"


def test_plain_text_is_unchanged():
    result = AcademicLinkResolver.resolve(
        "CP213 requires CP164.",
        LINKS,
    )

    assert result == "CP213 requires CP164."
