"""Academic Calendar program pages -> Evidence. Pure functions."""
from backend.domain.entities.retrieval import Evidence
from backend.domain.entities.wlu.wlu_pages import WluPageRead


def program_evidence(page: WluPageRead, primary: bool) -> Evidence:
    # Program requirements lose meaning when shortened (a dropped "or" changes eligibility), so every
    # detail level carries the full page.
    content = "\n".join([f"Academic Calendar program: {page.title}", f"Version: {page.version}", page.content])
    metadata = page.metadata_json

    return Evidence(
        source_id=f"wlu_page:{page.id}",
        title=page.title,
        url=page.url or "",
        content=content,
        compact_content=content,
        minimal_content=content,
        external_links=list(metadata.external_links or []) if metadata is not None else [],
        primary=primary,
    )
