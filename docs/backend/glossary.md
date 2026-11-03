# Glossary

> **Audience:** everyone, especially anyone new to the university's systems or to retrieval-augmented generation.

## Wilfrid Laurier University terms

| Term | Meaning |
| --- | --- |
| **Academic Calendar** | The university's official catalogue of courses, programs and regulations, published per academic year. The source for course descriptions, prerequisites and credits |
| **LORIS** | The registration system (built on Ellucian Banner). The source for what is offered in a given term: sections, times, rooms, instructors, seats |
| **CRN** | Course Reference Number: identifies one section in one term |
| **Term code** | `YYYYMM`, where the month is the term's start: `01` Winter, `05` Spring/Summer, `09` Fall. `202609` is Fall 2026 |
| **Course** | A course as the Academic Calendar describes it, for one academic year (for example `CP264`). Stable |
| **Course term** | One term's offering of a course, as LORIS lists it: a section with its own CRN, meetings and instructors. It can differ from the calendar entry. The two are never merged |
| **Academic year** | `YYYY/YYYY`, for example `2026/2027` |
| **Academic level** | Undergraduate or graduate: which Academic Calendar a course or calendar page belongs to (each year has one of each). Pages that apply to every student, such as tuition or important dates, have none |

## How GoldenGuide answers

| Term | Meaning |
| --- | --- |
| **RAG** | Retrieval-augmented generation: the answer model writes only from evidence the system retrieved |
| **Structured retrieval** | Answering factual questions with typed database queries (PostgreSQL) instead of searching text |
| **Semantic search** | Finding text by meaning in the vector store (Qdrant), used for policies and open questions |
| **Dense / sparse / multi-vector** | Three ways to turn text into vectors: by meaning (MiniLM), by weighted terms (SPLADE), and per token (ColBERT). Combined in hybrid search |
| **Reranker** | A model that reads the question and each candidate together and reorders the results |
| **Retrieval profile** | A named bundle of vector collection, search settings, evidence budget and answer model, plus optional fallback profiles |
| **Entity masking** | Replacing recognised courses and departments in the question with placeholders (`[COURSE1]`) before the model plans the query, so it cannot invent one |
| **Evidence budget** | The token limit for database records in the prompt. Records use the richest rendering that fits: detailed, compact or minimal |
| **NDJSON stream** | The chat response format: one JSON object per line, ending with an explicit `ok` or `error` event |

## Running it

| Term | Meaning |
| --- | --- |
| **Job run / batch** | A tracked unit of ingestion work and its pieces. Modes: `fresh` (everything), `update` (what changed), `retry` (what failed) |
| **Worker** | The container that runs queued jobs (Procrastinate queue on PostgreSQL), separate from the API so jobs never slow chat |
| **Provision** | The one-shot job that applies database migrations and creates buckets and vector collections before the API starts |
| **Compose profile** | A label that selects which containers a Compose command starts (for example `all`, `all-dev`, `embedding-gpu`) |
| **Compose project** | The prefix Compose puts on containers, networks and volumes. Each environment has its own, which keeps their data apart |
| **Service key** | A bearer key for machines (such as the nightly workflow) with only the scopes it needs. The server stores only its hash |
| **OIDC** | OpenID Connect: the standard sign-in protocol. Keycloak is the identity provider today; Microsoft Entra ID is a possible later one |
| **Port / adapter** | Hexagonal architecture terms: a port is an interface the core defines; an adapter is the code that implements it for one technology |
| **Fail closed** | When security state is unavailable, deny access instead of allowing it |
