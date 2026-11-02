"""Track LORIS export/import through the same one-shot lifecycle as other sources."""

from backend.application.services.jobs.one_shot import OneShotJobRunner
from backend.application.use_cases.scraping.wlu_registration.persistence import (
    WLURegistrationPersistence,
)
from backend.application.use_cases.scraping.wlu_registration.scrape import (
    WLURegistrationScraper,
)
from backend.domain.entities.jobs import JobMode, JobStatus, JobWorkResult
from backend.domain.ports.repositories.app.app_db import AppDB

# Job names (the duplicate-run lock key is "<name>:<term_code>").
REGISTRATION_EXPORT_JOB_NAME = "registration_export"
REGISTRATION_IMPORT_JOB_NAME = "registration_import"


class RegistrationJobs:
    def __init__(
        self,
        app_db: AppDB,
        scraper: WLURegistrationScraper,
        persistence: WLURegistrationPersistence,
    ) -> None:
        self.app_db = app_db
        self.scraper = scraper
        self.persistence = persistence

    async def export(
        self, run_id: int, term_code: str, page_size: int, subject: str | None
    ) -> dict:
        async def work() -> JobWorkResult:
            summary = await self.scraper.extract_to_blob(
                term_code=term_code, page_size=page_size, subject=subject
            )
            return JobWorkResult(
                summary=summary,
                status=JobStatus.PARTIAL_SUCCESS
                if summary["detail_fetch_failures"]
                else JobStatus.SUCCESS,
            )

        return await OneShotJobRunner(
            self.app_db, f"{REGISTRATION_EXPORT_JOB_NAME}:{term_code}"
        ).execute(
            run_id=run_id,
            mode=JobMode.FRESH,
            work=work,
        )

    async def import_term(self, run_id: int, term_code: str) -> dict:
        async def work() -> JobWorkResult:
            return JobWorkResult(
                summary=await self.persistence.ingest_from_blob(term_code=term_code)
            )

        return await OneShotJobRunner(
            self.app_db, f"{REGISTRATION_IMPORT_JOB_NAME}:{term_code}"
        ).execute(
            run_id=run_id,
            mode=JobMode.UPDATE,
            work=work,
        )
