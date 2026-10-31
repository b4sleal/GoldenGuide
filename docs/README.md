# GoldenGuide documentation

The [project README](../README.md) is the short overview. These pages are the full reference. Every page
says at the top who it is for, so the set can later be split into developer and operator guides.

## Start here

| I want to... | Read |
| --- | --- |
| Run GoldenGuide on my machine | [Getting started](getting-started.md) |
| Understand how it is built | [Architecture](architecture.md), then [Chat pipeline](chat-pipeline.md) |
| Make sense of the terms (LORIS, CRN, retrieval profile...) | [Glossary](glossary.md) |
| Change the code | [Getting started](getting-started.md) (editor setup, day-to-day), [Testing](testing.md), [Configuration](configuration.md), and the [contributor rules](#contributor-rules) |
| Deploy it or look after it | [Environments](environments.md), then [Operations](operations.md) |
| Check how it is secured | [Security](security.md) |
| Work on data collection and indexing | [Ingestion](ingestion.md), [Nightly ingestion](nightly-ingestion.md) |
| Call the API | [HTTP API](api.md) |
| Read the whole design in one document | [Software design document](sdd/GoldenGuide-SDD.pdf) ([LaTeX source](sdd/GoldenGuide-SDD.tex)) |

## All pages

| Page | For | Read it to learn |
| --- | --- | --- |
| [Getting started](getting-started.md) | Developers | Install with only Docker, configure, start, load data, editor setup, day-to-day workflow |
| [Architecture](architecture.md) | Developers, reviewers | Services, data stores, hexagonal layers, provider registries, domain model, failure semantics, scaling, repository layout |
| [Chat pipeline](chat-pipeline.md) | Developers | How a question becomes an answer: extraction, LLM plan, compilers, structured and semantic retrieval, reranking, streaming |
| [Ingestion](ingestion.md) | Developers, operators | Collecting WLU sources, jobs and retries, chunking, enrichment and embedding |
| [Nightly ingestion](nightly-ingestion.md) | Operators | Scheduled collection and indexing with GitHub Actions; recovery |
| [Configuration](configuration.md) | Developers, operators | Layered YAML, catalogs and profiles, runtime settings, secrets, environment variables |
| [Security](security.md) | Developers, operators, reviewers | Access policy, sign-in, Keycloak and Microsoft Entra, service keys, rate limits, fail-closed rules |
| [HTTP API](api.md) | Developers, integrators | Endpoints, job responses, errors, the NDJSON chat stream contract |
| [Observability](observability.md) | Operators, developers | Logs, traces, Grafana, useful timings |
| [Testing](testing.md) | Developers | Unit, integration and evaluation tests; running them with only Docker; the CI gate |
| [Docker](docker.md) | Developers, operators | Compose files and profiles, images, separate machines, resource limits, disk cleanup |
| [Environments](environments.md) | Everyone who deploys | Development, staging and production: env files, hostnames and tunnels, Keycloak, deploying production |
| [Operations](operations.md) | Operators | Health checks, deploys, rollback, backups, secret rotation, troubleshooting, accounts and ownership |
| [Glossary](glossary.md) | Everyone | University, retrieval and operations terms |
