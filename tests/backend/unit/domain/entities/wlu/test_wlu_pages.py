"""Reference-only Academic Calendar pages: cross-listings that only point to another entry."""
import pytest

from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageMetadata, WluPageRead


def page(title: str, body: str) -> WluPageRead:
    return WluPageRead(
        id=1, title=title, content=f"{title}\n\n{body}", version="2026/2027", url="", site_name="academic-calendar",
        record_type=AcademicCalendarType.PROGRAM, metadata_json=WluPageMetadata(),
    )


# Real shapes seen in the 2026/2027 Calendar.
@pytest.mark.parametrize(("title", "body"), [
    ("Honours BSc Psychology and Computer Science",
     "[Program](@@1@@) description link in [Computer Science and Physics](@@2@@) section."),
    ("Honours BA French, Co-operative Education", "Refer to the [Co-operative Education](@@1@@) section."),
    ("Honours BSc Chemistry and Biology", "(Refer to [Biology](@@1@@) [program](@@2@@) description section.)"),
    ("Canadian Studies Minor", "Link to [Canadian Studies Minor](@@1@@)."),
    ("Honours BA Religion and Culture with Co-Operative Education",
     "Please see [Honours BA Religion and Culture with Co-Operative Education](@@1@@) for [Co-Op](@@2@@) details."),
    # Title repeated as a link, with non-breaking and doubled spaces from the scraped HTML.
    ("Honours BSc Environmental Science",
     "[Honours\xa0 BSc Environmental Science](@@1@@):\xa0 See Environmental Science section"),
])
def test_pages_that_only_point_elsewhere_are_reference_only(title, body):
    assert page(title, body).is_reference_only


@pytest.mark.parametrize(("title", "body"), [
    # Short, but with its own requirements; the reference comes last.
    ("Anthropology Minor",
     ("[AN100](@@1@@) plus 2.5 additional [senior](@@2@@) [credits](@@3@@) in Anthropology. "
      "Note: Refer to [Regulations Governing all Minors.](@@4@@)")),
    ("Honours BSc Computer Science and Psychology",
     "The [program](@@1@@) consists of a minimum of 20.0 credits, including CP104 and CP164."),
    # Opens with a reference but goes on with real content.
    ("Honours BSc Data Science",
     "See the Data Science section for the full description. " + "Required: CP104, CP164, MA103, ST259. " * 5),
])
def test_pages_with_their_own_content_are_kept(title, body):
    assert not page(title, body).is_reference_only
