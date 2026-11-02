"""Use-case wiring: settings, chat, ingestion/embedding jobs, and scraping jobs.

Jobs and scraping services are Factories (fresh per run: they hold per-run state); stateless
services shared by requests are Singletons.
"""
from dependency_injector import containers, providers

from backend.application.services.jobs.execution import JobExecution
from backend.application.services.jobs.job_submit import JobSubmissionService
from backend.application.services.jobs.registry import JobRegistry, build_job_handlers
from backend.application.services.simple_scraping.service import (
    AsyncCrawlerRunner,
)
from backend.application.use_cases.chatbot.chat_turn import ChatTurn
from backend.application.use_cases.chatbot.context_resolver import (
    RAGContextResolver,
)
from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.application.use_cases.chatbot.rag_chatbot import (
    RagChatbot,
)
from backend.application.use_cases.chatbot.retrieval_orchestrator import (
    AcademicRetrievalOrchestrator,
)
from backend.application.use_cases.ingestion.course_terms import (
    CourseTermEmbeddingSource,
)
from backend.application.use_cases.ingestion.courses import (
    CourseEmbeddingSource,
)
from backend.application.use_cases.ingestion.embedding_job import (
    EmbeddingJob,
)
from backend.application.use_cases.ingestion.ingest_knowledge import (
    KnowledgeIngestor,
)
from backend.application.use_cases.ingestion.upload_doc import (
    DocumentUploadService,
)
from backend.application.use_cases.ingestion.wlu_pages import (
    WluPageEmbeddingSource,
)
from backend.application.use_cases.scraping.academic_calendar.crawl.audit import (
    AcademicCalendarCrawlAuditService,
)
from backend.application.use_cases.scraping.academic_calendar.crawl.job import (
    AcademicCalendarCrawlJob,
)
from backend.application.use_cases.scraping.academic_calendar.profile import (
    AcademicCalendarProfile,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.audit import (
    AcademicCalendarAuditService,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.job import (
    AcademicCalendarPersistenceJob,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.persistence import (
    AcademicCalendarPersistenceService,
)
from backend.application.use_cases.scraping.websites.crawl.job import (
    WebsiteCrawlJob,
)
from backend.application.use_cases.scraping.websites.scrape.job import (
    WebsitePersistenceJob,
)
from backend.application.use_cases.scraping.websites.scrape.persistence import (
    WebsitePersistenceService,
)
from backend.application.use_cases.scraping.wlu_registration.jobs import (
    RegistrationJobs,
)
from backend.application.use_cases.scraping.wlu_registration.persistence import (
    WLURegistrationPersistence,
)
from backend.application.use_cases.scraping.wlu_registration.scrape import (
    WLURegistrationScraper,
)
from backend.application.use_cases.settings.settings_cache import (
    SettingsCacheService,
)
from backend.application.use_cases.settings.settings_service import (
    SettingsService,
)
from backend.core.di.wiring.router import RouterContainer
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.settings.jobs import JobExecutionMode
from backend.infra.jobs.in_process_launcher import InProcessJobLauncher
from backend.infra.jobs.procrastinate_app import (
    build_procrastinate_app,
    register_worker_tasks,
)
from backend.infra.jobs.procrastinate_launcher import ProcrastinateJobLauncher
from backend.infra.jobs.thread_compute import ThreadComputeExecutor


class ServiceContainer(containers.DeclarativeContainer):
    persistence = providers.DependenciesContainer()
    ml = providers.DependenciesContainer()

    ai_behavior = providers.Dependency()
    catalog = providers.Dependency()
    jobs = providers.Dependency()

    # CPU-bound job steps (HTML parsing) run here, off the event loop.
    compute_executor = providers.Singleton(ThreadComputeExecutor)

    settings_cache_service = providers.Singleton(
        SettingsCacheService,
        cache=persistence.app_cache,
    )

    settings_service = providers.Singleton(
        SettingsService,
        app_db=persistence.app_db,
        cache=settings_cache_service,
        runtime_defaults=ai_behavior.provided.runtime_defaults,
    )

    # WLU vocabulary lookups, shared by question extraction and scraping.
    lexicon_resolver = providers.Singleton(
        WluLexiconResolver,
        lexicon_profile=catalog.provided.text_enrichment.wlu_lexicon,
    )

    router = providers.Container(
        RouterContainer,
        school_db=persistence.school_db,
        cache=persistence.app_cache,
        llm=ml.llm_orchestrator,
        settings=settings_service,
        retrieval_profiles=catalog.provided.profiles.retrieval_profiles,
        lexicon_resolver=lexicon_resolver,
        institution=catalog.provided.institution,
        router_settings=catalog.provided.router,
    )

    rag_context_resolver = providers.Singleton(
        RAGContextResolver,
        router=router.retrieval_profile_router,
        embedding_orchestrator=ml.embedding_orchestrator,
        sparse_vectorizer_orchestrator=ml.sparse_vectorizer_orchestrator,
        vector_store=persistence.app_vector_store,
        blob_storage=persistence.app_blob_storage,
        reranker_orchestrator=ml.reranker_orchestrator,
        school_db=persistence.school_db,
        institution=catalog.provided.institution,
        snippet_settings=catalog.provided.chat.source_snippet,
    )

    academic_retrieval_orchestrator = providers.Singleton(
        AcademicRetrievalOrchestrator,
        query_router=router.query_router,
        factual_retriever=router.structured_retriever,
        rag_context_resolver=rag_context_resolver,
        retrieval_router=router.retrieval_profile_router
    )

    rag_chatbot = providers.Singleton(
        RagChatbot,
        context_resolver=academic_retrieval_orchestrator,
        llm_strategy=ml.llm_orchestrator,
        settings_service=settings_service,
        term_resolver=router.academic_term_resolver,
    )

    conversation_history = providers.Singleton(
        ConversationHistory,
        app_db=persistence.app_db,
        institution=catalog.provided.institution,
    )

    chat_turn = providers.Singleton(
        ChatTurn,
        chatbot=rag_chatbot,
        app_db=persistence.app_db,
        history=conversation_history,
        history_settings=catalog.provided.chat.conversation_history,
    )

    knowledge_service = providers.Singleton(
        KnowledgeIngestor,
        vector_collections=catalog.provided.profiles.vector_collection,
        vector_store=persistence.app_vector_store,
        embedding_orchestrator=ml.embedding_orchestrator,
        sparse_vectorizer_orchestrator=ml.sparse_vectorizer_orchestrator,
        text_splitter_orchestrator=ml.text_splitter_orchestrator,
    )

    document_uploader = providers.Singleton(
        DocumentUploadService,
        blob_storage=persistence.app_blob_storage,
        app_db=persistence.app_db,
        knowledge_service=knowledge_service,
    )

    # One tracked embedding job per source table (fresh / update / retry, as the import jobs).
    course_embedding_job = providers.Factory(
        EmbeddingJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        knowledge_service=knowledge_service,
        source=providers.Singleton(CourseEmbeddingSource),
    )

    course_term_embedding_job = providers.Factory(
        EmbeddingJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        knowledge_service=knowledge_service,
        source=providers.Singleton(CourseTermEmbeddingSource),
    )

    wlu_page_embedding_job = providers.Factory(
        EmbeddingJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        knowledge_service=knowledge_service,
        source=providers.Singleton(WluPageEmbeddingSource),
    )

    crawler_runner = providers.Factory(
        AsyncCrawlerRunner,
        school_db=persistence.school_db,
        blob_storage=persistence.app_blob_storage,
        compute=compute_executor,
    )

    academic_calendar_profile = providers.Factory(
        AcademicCalendarProfile,
    )

    academic_calendar_crawl_audit_service = providers.Factory(
        AcademicCalendarCrawlAuditService,
        school_db=persistence.school_db,
    )

    academic_calendar_crawl_job = providers.Factory(
        AcademicCalendarCrawlJob,
        app_db=persistence.app_db,
        runner=crawler_runner,
        profile=academic_calendar_profile,
        audit_service=academic_calendar_crawl_audit_service,
    )

    academic_calendar_persistence_service = providers.Factory(
        AcademicCalendarPersistenceService,
        school_db=persistence.school_db,
        blob_storage=persistence.app_blob_storage,
        lexicon_profile=catalog.provided.text_enrichment.wlu_lexicon,
        lexicon_resolver=lexicon_resolver,
        profile=academic_calendar_profile,
        compute=compute_executor,
    )

    academic_calendar_audit_service = providers.Factory(
        AcademicCalendarAuditService,
        school_db=persistence.school_db,
    )

    academic_calendar_persistence_job = providers.Factory(
        AcademicCalendarPersistenceJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        persistence_service=academic_calendar_persistence_service,
        audit_service=academic_calendar_audit_service,
    )

    website_crawl_job = providers.Factory(
        WebsiteCrawlJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        runner=crawler_runner,
        catalog=catalog.provided.scraping,
    )

    website_persistence_service = providers.Factory(
        WebsitePersistenceService,
        school_db=persistence.school_db,
        blob_storage=persistence.app_blob_storage,
        compute=compute_executor,
    )

    website_persistence_job = providers.Factory(
        WebsitePersistenceJob,
        app_db=persistence.app_db,
        school_db=persistence.school_db,
        persistence_service=website_persistence_service,
        catalog=catalog.provided.scraping,
    )

    wlu_registration_scraper = providers.Factory(
        WLURegistrationScraper,
        blob_storage=persistence.app_blob_storage,
    )

    wlu_registration_persistence = providers.Factory(
        WLURegistrationPersistence,
        school_db=persistence.school_db,
        blob_storage=persistence.app_blob_storage,
        lexicon_resolver=lexicon_resolver,
        compute=compute_executor,
    )

    registration_jobs = providers.Factory(
        RegistrationJobs,
        app_db=persistence.app_db,
        scraper=wlu_registration_scraper,
        persistence=wlu_registration_persistence,
    )

    # ---- Running jobs (docs/backend/architecture.md#background-jobs) ------------------------------
    # The registry receives each job's Factory (`.provider`), not an instance, so every run gets a
    # fresh job: jobs hold per-run state.
    job_registry = providers.Singleton(
        JobRegistry,
        handlers=providers.Callable(
            build_job_handlers,
            academic_calendar_crawl_job=academic_calendar_crawl_job.provider,
            academic_calendar_persistence_job=academic_calendar_persistence_job.provider,
            website_crawl_job=website_crawl_job.provider,
            website_persistence_job=website_persistence_job.provider,
            registration_jobs=registration_jobs.provider,
            course_embedding_job=course_embedding_job.provider,
            course_term_embedding_job=course_term_embedding_job.provider,
            wlu_page_embedding_job=wlu_page_embedding_job.provider,
        ),
    )
    job_execution = providers.Singleton(
        JobExecution,
        app_db=persistence.app_db,
        registry=job_registry,
        heartbeat_seconds=jobs.provided.heartbeat_seconds,
    )
    # Procrastinate on the app database. The API only defers by task name; the worker process uses
    # procrastinate_worker_app, the same App with the run_job task registered.
    procrastinate_app = providers.Singleton(
        build_procrastinate_app,
        db=catalog.provided.active.db["app"],
        worker=jobs.provided.worker,
    )
    procrastinate_worker_app = providers.Singleton(
        register_worker_tasks, app=procrastinate_app, executor=job_execution,
    )
    # Where submitted jobs run (system.jobs.execution): endpoints return a run id at once either way.
    # in_process: tasks in this process (development). worker: queued for worker containers.
    job_launcher = providers.Selector(
        jobs.provided.execution,
        **{
            JobExecutionMode.IN_PROCESS: providers.Singleton(InProcessJobLauncher, execution=job_execution),
            JobExecutionMode.WORKER: providers.Singleton(ProcrastinateJobLauncher, app=procrastinate_app),
        },
    )
    job_submission = providers.Singleton(
        JobSubmissionService,
        app_db=persistence.app_db,
        launcher=job_launcher,
    )
