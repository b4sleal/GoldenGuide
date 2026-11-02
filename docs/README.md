# GoldenGuide documentation

The [project README](../README.md) is the short overview. These pages are the full reference. Every page
says at the top who it is for, so the set can later be split into developer and operator guides.

## Start here

| I want to... | Read |
| --- | --- |
| Run GoldenGuide on my machine | [Getting started](backend/getting-started.md) |
| Understand how it is built | [Architecture](backend/architecture.md), then [Chat pipeline](backend/chat-pipeline.md) |
| Make sense of the terms (LORIS, CRN, retrieval profile...) | [Glossary](backend/glossary.md) |
| Change the code | [Getting started](backend/getting-started.md) (editor setup, day-to-day), [Testing](backend/testing.md), [Configuration](backend/configuration.md), and the [contributor rules](#contributor-rules) |
| Deploy it or look after it | [Environments](backend/environments.md), then [Operations](backend/operations.md) |
| Check how it is secured | [Security](backend/security.md) |
| Work on data collection and indexing | [Ingestion](backend/ingestion.md), [Nightly ingestion](backend/nightly-ingestion.md) |
| Call the API | [HTTP API](backend/api.md) |
| Read the whole design in one document | [Software design document](sdd/GoldenGuide-SDD.pdf) ([LaTeX source](sdd/GoldenGuide-SDD.tex)) |

## All pages

| Page | For | Read it to learn |
| --- | --- | --- |
| [Getting started](backend/getting-started.md) | Developers | Install with only Docker, configure, start, load data, editor setup, day-to-day workflow |
| [Architecture](backend/architecture.md) | Developers, reviewers | Services, data stores, hexagonal layers, provider registries, domain model, failure semantics, scaling, repository layout |
| [Chat pipeline](backend/chat-pipeline.md) | Developers | How a question becomes an answer: extraction, LLM plan, compilers, structured and semantic retrieval, reranking, streaming |
| [Ingestion](backend/ingestion.md) | Developers, operators | Collecting WLU sources, jobs and retries, chunking, enrichment and embedding |
| [Nightly ingestion](backend/nightly-ingestion.md) | Operators | Scheduled collection and indexing with GitHub Actions; recovery |
| [Configuration](backend/configuration.md) | Developers, operators | Layered YAML, catalogs and profiles, runtime settings, secrets, environment variables |
| [Security](backend/security.md) | Developers, operators, reviewers | Access policy, sign-in, Keycloak and Microsoft Entra, service keys, rate limits, fail-closed rules |
| [HTTP API](backend/api.md) | Developers, integrators | Endpoints, job responses, errors, the NDJSON chat stream contract |
| [Observability](backend/observability.md) | Operators, developers | Logs, traces, Grafana, useful timings |
| [Testing](backend/testing.md) | Developers | Unit, integration and evaluation tests; running them with only Docker; the CI gate |
| [Docker](backend/docker.md) | Developers, operators | Compose files and profiles, images, separate machines, resource limits, disk cleanup |
| [Environments](backend/environments.md) | Everyone who deploys | Development, staging and production: env files, hostnames and tunnels, Keycloak, deploying production |
| [Operations](backend/operations.md) | Operators | Health checks, deploys, rollback, backups, secret rotation, troubleshooting, accounts and ownership |
| [Glossary](backend/glossary.md) | Everyone | University, retrieval and operations terms |
| [Embedding memory plan](backend/plans/embedding-memory-plan.md) | Developers | Proposed plan: bounded memory when embedding very large pages (temporary page) |

## Frontend

| Page | For | Read it to learn |
| --- | --- | --- |
| [Frontend architecture](frontend/architecture.md) | Developers, reviewers | Stack and why, source layout, answer streaming, routing, API access, serving, tests |
| [Frontend interaction design](frontend/ux.md) | Developers, designers, reviewers | Layout, loading and status messages, answers, unfinished answers, accessibility |
| [Frontend roadmap](frontend/roadmap.md) | Developers, reviewers | Planned features, open questions, decision log |
| [Frontend README](../frontend/README.md) | Developers | Setup, commands, serving, updating a running frontend |
