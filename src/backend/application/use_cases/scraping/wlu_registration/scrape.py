"""Extract one term's sections from LORIS (Banner class search) into a single JSON blob.

Banner keeps search state in the session, so the client resets it and selects the term before paging
through results. Each section's prerequisites, corequisites, restrictions and description come from
separate detail requests; a detail that cannot be fetched is stored empty and counted in the result
(detail_fetch_failures), never silently. Parsing and persistence happen later (persistence.py).
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog

from backend.application.services.simple_scraping.service import USER_AGENT
from backend.domain.ports.providers.blob import BlobStorage

logger = structlog.get_logger()

DETAIL_ATTEMPTS = 3
DETAIL_RETRY_DELAY_SECONDS = 1
# Concurrent sections whose four detail requests run at once (LORIS drops connections under load).
MAX_CONCURRENT_SECTIONS = 10


def loris_term_blob_key(term_code: str) -> str:
    """Where a term's raw extraction is stored; written by the scraper, read by persistence."""
    return f"loris/terms/{term_code}.json"


class WLURegistrationScraper:
    BASE_URL = "https://loris.wlu.ca"
    RESET_PATH = "/register/ssb/classSearch/resetDataForm"
    TERM_SEARCH_PATH = "/register/ssb/term/search?mode=search"
    SEARCH_RESULTS_PATH = "/register/ssb/searchResults/searchResults"
    PREREQ_PATH = "/register/ssb/searchResults/getSectionPrerequisites"
    COREQ_PATH = "/register/ssb/searchResults/getCorequisites"
    RESTRICTIONS_PATH = "/register/ssb/searchResults/getRestrictions"
    DESCRIPTION_PATH = "/register/ssb/searchResults/getCourseDescription"

    def __init__(self, blob_storage: BlobStorage):
        self.blob_storage = blob_storage

    async def extract_to_blob(
            self,
            term_code: str,
            page_size: int = 500,
            subject: str | None = None,
    ) -> dict[str, Any]:

        logger.info("loris_extraction_started", term_code=term_code, subject=subject)

        timeout = httpx.Timeout(60.0, connect=10.0)
        limits = httpx.Limits(max_connections=40, max_keepalive_connections=20)

        offset = 0
        total_count: int | None = None
        all_raw_data = []
        detail_failures = 0

        async with httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=timeout,
                limits=limits,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
        ) as client:
            await self._reset_session(client)
            await self._select_term(client, term_code)

            while True:
                payload = await self._fetch_results_page(
                    client=client, term_code=term_code, page_offset=offset, page_size=page_size, subject=subject,
                )

                if total_count is None:
                    total_count = int(payload.get("totalCount") or 0)

                sections = payload.get("data") or []
                if not sections:
                    break

                logger.info("fetching_loris_details", offset=offset, total=total_count, batch_size=len(sections))
                req_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SECTIONS)

                async def process_section(section: dict) -> dict | None:
                    nonlocal detail_failures
                    crn = str(section.get("courseReferenceNumber") or "").strip()
                    if not crn:
                        return None

                    async with req_semaphore:
                        details = await asyncio.gather(
                            self._post_detail(client, self.PREREQ_PATH, term_code, crn),
                            self._post_detail(client, self.COREQ_PATH, term_code, crn),
                            self._post_detail(client, self.RESTRICTIONS_PATH, term_code, crn),
                            self._post_detail(client, self.DESCRIPTION_PATH, term_code, crn)
                        )

                    detail_failures += sum(detail is None for detail in details)
                    prereq_html, coreq_html, restrictions_html, description_html = (detail or "" for detail in details)
                    return {
                        "section": section,
                        "prereq_html": prereq_html,
                        "coreq_html": coreq_html,
                        "restrictions_html": restrictions_html,
                        "description_html": description_html,
                    }

                tasks = [process_section(sec) for sec in sections]
                results = await asyncio.gather(*tasks)

                for res in results:
                    if res:
                        all_raw_data.append(res)

                offset += page_size
                if total_count is not None and offset >= total_count:
                    break

        json_bytes = json.dumps(all_raw_data).encode("utf-8")
        blob_key = loris_term_blob_key(term_code)

        await self.blob_storage.upload(blob_key, json_bytes, "application/json")

        if detail_failures:
            # Those sections were stored with an empty prerequisite/corequisite/restriction/description.
            logger.warning("loris_detail_fetches_failed", term_code=term_code, failures=detail_failures)
        logger.info("loris_extraction_finished", term_code=term_code, sections=len(all_raw_data),
                    detail_fetch_failures=detail_failures)

        return {
            "term_code": term_code,
            "blob_key": blob_key,
            "sections_extracted": len(all_raw_data),
            "detail_fetch_failures": detail_failures,
        }

    async def _reset_session(self, client: httpx.AsyncClient) -> None:
        init_resp = await client.get("/register/ssb/term/termSelection?mode=search")
        init_resp.raise_for_status()
        reset_resp = await client.post(self.RESET_PATH)
        reset_resp.raise_for_status()

    async def _select_term(self, client: httpx.AsyncClient, term_code: str) -> None:
        response = await client.post(self.TERM_SEARCH_PATH, data={"term": term_code})
        response.raise_for_status()

    async def _fetch_results_page(self, client: httpx.AsyncClient, term_code: str, page_offset: int, page_size: int, subject: str | None) -> dict[str, Any]:
        params = {"txt_term": term_code, "pageOffset": page_offset, "pageMaxSize": page_size, "sortColumn": "subjectDescription", "sortDirection": "asc"}
        if subject:
            params["txt_subject"] = subject
        response = await client.get(self.SEARCH_RESULTS_PATH, params=params)
        response.raise_for_status()
        return response.json()

    async def _post_detail(self, client: httpx.AsyncClient, path: str, term_code: str, crn: str) -> str | None:
        """A section detail's HTML, or None if it could not be fetched (counted by the caller).

        Connection errors are retried (LORIS drops connections under load); HTTP errors are not.
        """
        for attempt in range(DETAIL_ATTEMPTS):
            try:
                response = await client.post(path, data={"term": term_code, "courseReferenceNumber": crn})
                response.raise_for_status()
                return response.text
            except httpx.RequestError as e:
                if attempt == DETAIL_ATTEMPTS - 1:
                    logger.warning("loris_detail_fetch_failed", path=path, crn=crn, error_type=type(e).__name__, error=str(e))
                    return None
                await asyncio.sleep(DETAIL_RETRY_DELAY_SECONDS)
            except httpx.HTTPStatusError as e:
                logger.warning("loris_detail_fetch_failed", path=path, crn=crn, error_type=type(e).__name__, error=str(e))
                return None
        return None