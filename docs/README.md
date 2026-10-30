# GoldenGuide documentation

The [project README](../README.md) is the short overview. These pages are the full reference.

| Document | Read it to learn |
| --- | --- |
| [Software design document](sdd/GoldenGuide-SDD.pdf) ([LaTeX source](sdd/GoldenGuide-SDD.tex)) | The complete design in one document: requirements, architecture, design decisions with alternatives, collection, jobs, indexing, embedding service, question answering, security, data model, interfaces, sequence diagrams, quality attributes, deployment, verification, risks |
| [Getting started](getting-started.md) | Install with only Docker, configure, start, sign in, load data, CPU-only setup, day-to-day workflow |
| [Architecture](architecture.md) | Services, data stores, hexagonal layers, provider registries, domain model, failure semantics, scaling, repository layout |
| [Chat pipeline](chat-pipeline.md) | How a question becomes an answer: extraction, LLM plan, compilers, structured and semantic retrieval, reranking, streaming |
| [Ingestion](ingestion.md) | Collecting WLU sources, jobs and retries, chunking, enrichment and embedding |
| [Nightly ingestion](nightly-ingestion.md) | Scheduled collection and indexing with GitHub Actions; recovery |
| [Configuration](configuration.md) | Layered YAML, catalogs and profiles, runtime settings, secrets, environment variables |
| [Security](security.md) | Access policy, OIDC sign-in, Microsoft Entra, service keys, rate limits, fail-closed rules |
| [HTTP API](api.md) | Endpoints, job responses, errors, the NDJSON chat stream contract |
| [Observability](observability.md) | Logs, traces, Grafana, useful timings |
| [Testing](testing.md) | Unit, integration and evaluation tests; running them with only Docker; CI gate |
| [Docker](docker.md) | Compose files and profiles, images, separate machines, production and staging, environment files, resource limits, disk cleanup |

Contributor rules (for people and AI assistants alike):

| Document | Contents |
| --- | --- |
| [`agents/architecture.md`](agents/architecture.md) | Architecture contract: layers, invariants, failure semantics |
| [`agents/engineer.md`](agents/engineer.md) | Engineering standard |
| [`agents/rules.md`](agents/rules.md) | Detailed coding rules |
| [`agents/workflow.md`](agents/workflow.md) | Change workflow and approval gates |
