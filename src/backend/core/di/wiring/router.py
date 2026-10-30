"""Query-router wiring: entity extraction (matcher order), term resolution, LLM planning and the
structured retrievers.
"""
from dependency_injector import containers, providers

from backend.application.services.chatbot.retrieval_router import (
    RetrievalProfileRouter,
)
from backend.application.services.router.compilation.course_compiler import (
    CourseQueryCompiler,
)
from backend.application.services.router.compilation.course_term_compiler import (
    CourseTermQueryCompiler,
)
from backend.application.services.router.extraction.entity_extractor import (
    PreLLMExtractor,
)
from backend.application.services.router.extraction.entity_lookup_cache import (
    EntityLookupCache,
)
from backend.application.services.router.extraction.matchers.course_matcher import (
    CourseCodeMatcher,
)
from backend.application.services.router.extraction.matchers.department_hint_matcher import (
    DepartmentHintMatcher,
)
from backend.application.services.router.extraction.matchers.instructor_matcher import (
    InstructorMatcher,
)
from backend.application.services.router.extraction.matchers.lexicon_matcher import (
    LexiconEntityMatcher,
)
from backend.application.services.router.extraction.matchers.room_matcher import (
    RoomMatcher,
)
from backend.application.services.router.planning.llm.llm_planner import (
    LLMQueryPlanner,
)
from backend.application.services.router.retrieval.course_retriever import (
    CourseRetriever,
)
from backend.application.services.router.retrieval.course_term_retriever import (
    CourseTermRetriever,
)
from backend.application.services.router.retrieval.program_retriever import (
    ProgramRetriever,
)
from backend.application.services.router.retrieval.structured_retriever import (
    StructuredRetriever,
)
from backend.application.services.router.router import (
    QueryRouter,
)
from backend.domain.entities.wlu.academic_term import (
    AcademicTermResolver,
    institution_clock,
)


class RouterContainer(containers.DeclarativeContainer):
    school_db = providers.Dependency()
    cache = providers.Dependency()
    llm = providers.Dependency()
    settings = providers.Dependency()
    retrieval_profiles = providers.Dependency()
    institution = providers.Dependency()
    router_settings = providers.Dependency()
    # Shared with scraping, so it is built by the parent container and passed in.
    lexicon_resolver = providers.Dependency()

    retrieval_profile_router = providers.Singleton(
        RetrievalProfileRouter,
        retrieval_profiles=retrieval_profiles,
    )

    entity_lookup_cache = providers.Singleton(
        EntityLookupCache,
        school_db=school_db,
        cache=cache,
        institution=institution,
        settings=router_settings.provided.entity_lookup_cache,
    )

    # Order matters: an earlier matcher claims its span first (a valid course code is never a room).
    pre_llm_extractor = providers.Singleton(
        PreLLMExtractor,
        entity_cache=entity_lookup_cache,
        matchers=providers.List(
            providers.Singleton(CourseCodeMatcher, lexicon_resolver=lexicon_resolver),
            providers.Singleton(RoomMatcher),
            providers.Singleton(InstructorMatcher),
            providers.Singleton(LexiconEntityMatcher, lexicon_resolver=lexicon_resolver),
            providers.Singleton(DepartmentHintMatcher, lexicon_resolver=lexicon_resolver),
        ),
    )

    # "Today" is the institution's local date (configured timezone).
    academic_term_resolver = providers.Singleton(
        AcademicTermResolver,
        clock=providers.Callable(institution_clock, timezone=institution.provided.zone),
    )

    llm_planner = providers.Singleton(
        LLMQueryPlanner,
        llm=llm,
        settings=settings,
        retrieval_router=retrieval_profile_router,
        term_resolver=academic_term_resolver,
    )

    # Entities extracted once, then the LLM plans retrieval.
    query_router = providers.Singleton(
        QueryRouter,
        extractor=pre_llm_extractor,
        llm_planner=llm_planner,
    )


    course_query_compiler = providers.Singleton(
        CourseQueryCompiler,
        institution=institution,
    )

    course_term_query_compiler = providers.Singleton(
        CourseTermQueryCompiler,
        term_resolver=academic_term_resolver,
    )

    course_retriever = providers.Singleton(
        CourseRetriever,
        school_db=school_db,
        compiler=course_query_compiler,
    )

    course_term_retriever = providers.Singleton(
        CourseTermRetriever,
        school_db=school_db,
        compiler=course_term_query_compiler,
        institution=institution,
    )

    program_retriever = providers.Singleton(
        ProgramRetriever,
        school_db=school_db,
    )

    structured_retriever = providers.Singleton(
        StructuredRetriever,
        # One retriever per RetrievalSource; a duplicate fails at startup.
        retrievers=providers.List(course_retriever, course_term_retriever, program_retriever),
    )
