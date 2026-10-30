"""Retrieval evaluation against the live stack: does each question's answering page reach the answer model?

    docker compose exec -w /app backend python -m tests.eval.retrieval_eval
    docker compose exec -w /app backend python -m tests.eval.retrieval_eval --show "What are the important dates"
    docker compose exec -w /app backend python -m tests.eval.retrieval_eval --ask "What are the important dates"

For every case in retrieval_cases.yml it runs the same search the chat uses (the configured retrieval
profile), then reports where the expected page first appears among the context chunks, before and after
the cross-encoder rerank, and how long each question took. "hit" = the page is in the first
CONTEXT_CHUNKS chunks, the ones the answer model actually receives. --show prints those chunks (title
and opening text) for one question. --ask runs the full chat pipeline for one question and prints the
answer, its tables and sources, and its timings (this one calls the LLMs).

This is an evaluation, not a unit test: it needs Postgres, Qdrant and the embedding service running,
and its numbers move with the data. Run it before and after any retrieval change.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

from backend.application.services.chatbot.reranking import drop_duplicate_chunks, rerank_hits
from backend.core.startup.runtime import build_container
from goldenguide_common.logging.telemetry import shutdown_telemetry

CASES = Path(__file__).with_name("retrieval_cases.yml")
CONTEXT_CHUNKS = 8  # RAGContextResolver.resolve_context(top_k=8): chunks that reach the answer model.


def page_of(url: str | None) -> str:
    # Pages imported before query strings were dropped can still carry ?ref=...: same page.
    return (url or "").split("?", 1)[0]


def first_rank(hits, expected_urls: set[str]) -> int | None:
    """1-based position of the first chunk from an expected page, or None if absent."""
    expected = {page_of(url) for url in expected_urls}
    for rank, hit in enumerate(hits, start=1):
        if page_of((hit.payload or {}).get("url")) in expected:
            return rank
    return None


def in_context(hits, expected_urls: set[str]) -> int:
    """How many of the chunks the answer model receives come from an expected page (coverage)."""
    expected = {page_of(url) for url in expected_urls}
    return sum(page_of((hit.payload or {}).get("url")) in expected for hit in hits[:CONTEXT_CHUNKS])


def describe(rank: int | None, coverage: int) -> str:
    if rank is None:
        return "miss      "
    return f"#{rank:<3} {'hit ' if rank <= CONTEXT_CHUNKS else 'late'} {coverage}/{CONTEXT_CHUNKS}"


def elapsed_ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


async def search_and_rerank(resolver, profile, question: str) -> tuple[list, list, int, int]:
    """(candidates, reranked, search_ms, rerank_ms) for one question."""
    started = time.perf_counter()
    candidates = drop_duplicate_chunks(await resolver.search_candidates(question, profile))
    search_ms = elapsed_ms(started)
    started = time.perf_counter()
    reranked = await rerank_hits(question, candidates, profile.vector_retrieval.rerank, resolver.reranker)
    return candidates, reranked, search_ms, elapsed_ms(started)


async def evaluate(resolver, profile, cases) -> int:
    hits_before = hits_after = covered_before = covered_after = 0
    started = time.perf_counter()
    for case in cases:
        expected = set(case["expected_urls"])
        candidates, reranked, search_ms, rerank_ms = await search_and_rerank(resolver, profile, case["question"])

        before, after = first_rank(candidates, expected), first_rank(reranked, expected)
        cover_before, cover_after = in_context(candidates, expected), in_context(reranked, expected)
        hits_before += before is not None and before <= CONTEXT_CHUNKS
        hits_after += after is not None and after <= CONTEXT_CHUNKS
        covered_before += cover_before
        covered_after += cover_after
        print(f"search {describe(before, cover_before)} | rerank {describe(after, cover_after)} | "
              f"{search_ms:>5} + {rerank_ms:>5} ms | {case['question']}")

    total = len(cases)
    print(f"\nanswer receives the right page: search only {hits_before}/{total}, with rerank {hits_after}/{total}")
    print(f"answer chunks from the right page: search only {covered_before}/{total * CONTEXT_CHUNKS}, "
          f"with rerank {covered_after}/{total * CONTEXT_CHUNKS}")
    print(f"{total} questions in {elapsed_ms(started) / 1000:.1f} s")
    return 0 if hits_after == total else 1


async def show(resolver, profile, question: str) -> None:
    candidates, reranked, search_ms, rerank_ms = await search_and_rerank(resolver, profile, question)
    print(f"search {search_ms} ms, rerank {rerank_ms} ms")
    for label, hits in (("SEARCH ONLY", candidates), ("WITH RERANK", reranked)):
        print(f"\n== {label}: first {CONTEXT_CHUNKS} chunks the answer model would receive")
        for rank, hit in enumerate(hits[:CONTEXT_CHUNKS], start=1):
            payload = hit.payload or {}
            text = " ".join(payload.get("text", "").split())
            print(f"{rank}. [{hit.score:.3f}] {payload.get('title')}\n   {text[:160]}")


def print_table(event: dict) -> None:
    print(f"\n\n[{event['title']}]")
    for row in [event["columns"], *event["rows"]]:
        print(" | ".join(str(cell) for cell in row))
    print()


async def ask(chatbot, question: str) -> int:
    """Run the full chat pipeline (the same events the browser receives) and print the answer."""
    print(f"Q: {question}\n\nA: ", end="", flush=True)
    started = time.perf_counter()
    first_text_ms = None
    sources: list[dict] = []
    async for line in chatbot.ask(question):
        event = json.loads(line)
        if event["type"] == "text":
            first_text_ms = first_text_ms if first_text_ms is not None else elapsed_ms(started)
            print(event["text"], end="", flush=True)
        elif event["type"] == "citation":
            print(f"[{', '.join(map(str, event['source_nums']))}]", end="", flush=True)
        elif event["type"] == "table":
            print_table(event)
        elif event["type"] == "sources":
            sources = event["sources"]

    print("\n\nSources:")
    for number, source in enumerate(sources, start=1):
        print(f"  {number}. {source['title']}  {source.get('url') or ''}")
    print(f"\nfirst text after {first_text_ms} ms, answer complete in {elapsed_ms(started)} ms")
    return 0


async def main(question: str | None, ask_question: str | None) -> int:
    container = build_container()
    try:
        if ask_question:
            return await ask(container.services.rag_chatbot(), ask_question)
        resolver = container.services.rag_context_resolver()
        # The same profile the chat routes ordinary questions to.
        profile = resolver.router.route_question(question or "")
        if question:
            await show(resolver, profile, question)
            return 0
        cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
        print(f"profile={profile.name} collection={profile.vector_collection.key} cases={len(cases)}\n")
        return await evaluate(resolver, profile, cases)
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate retrieval against retrieval_cases.yml.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--show", metavar="QUESTION", help="print the context chunks for one question")
    modes.add_argument("--ask", metavar="QUESTION", help="answer one question end to end and print the answer")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.show, args.ask)))
