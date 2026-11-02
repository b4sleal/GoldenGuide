"""SPLADE equivalence eval: the GPU adapter against fastembed's ONNX SPLADE on the same texts.

Rerun after changing the SPLADE model, `dtype` or pooling (configs/catalogs/providers/ml_local.yml).
Run inside the GPU embedding image (it has both libraries and the configured settings); the image
does not contain tests/, so mount it:

    docker compose --env-file .env.prod run --rm --no-deps -v ./tests:/app/tests \
        local-embedding-gpu python -m tests.eval.splade_equivalence [--page-text tests/page.txt]

Exit 0 when every text's vectors agree within the thresholds: vectors already stored in Qdrant
(fastembed) stay compatible with new ones. Exit 1 lists the texts that disagree. Read-only.
"""

import argparse
import asyncio
import math
import sys
from pathlib import Path

from fastembed import SparseTextEmbedding

from embedding_service.models.vectorizer.splade import SpladeSparseVectorizer
from goldenguide_common.config.env_reader import EnvSecretReader
from goldenguide_common.config.loader import ConfigLoader

SAMPLES = [
    "CP164 Data Structures I: prerequisite CP104 with a minimum grade of C-.",
    "Registration for the Winter 2027 term opens in November through LORIS.",
    "The Academic Calendar lists program requirements, course descriptions and regulations.",
    "Students may appeal a final grade within 30 days of its release.",
]
MIN_COSINE = 0.999
MIN_TOP_TERM_OVERLAP = 0.95
TOP_TERMS = 32


def as_dict(indices, values) -> dict[int, float]:
    return {int(index): float(value) for index, value in zip(indices, values, strict=True)}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    dot = sum(value * b.get(index, 0.0) for index, value in a.items())
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm if norm else float(a == b)


def top_terms(vector: dict[int, float]) -> set[int]:
    return set(sorted(vector, key=vector.get, reverse=True)[:TOP_TERMS])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page-text", type=Path, help="Also compare chunks of this UTF-8 page")
    parser.add_argument("--model-key", default="splade")
    args = parser.parse_args()

    settings = ConfigLoader(EnvSecretReader()).load_local_embedding_config().local_sparse_vectorizer[args.model_key]
    texts = list(SAMPLES)
    if args.page_text:
        content = args.page_text.read_text(encoding="utf-8")
        texts += [content[start:start + 1500] for start in range(0, len(content), 1500)][:64]

    reference = SparseTextEmbedding(model_name=settings.model_name, providers=["CUDAExecutionProvider"])
    expected = [as_dict(e.indices, e.values) for e in reference.embed(texts, batch_size=4)]
    actual = [as_dict(v.indices, v.values) for v in asyncio.run(SpladeSparseVectorizer(settings).vectorize_documents(texts))]

    failures = 0
    for number, (old, new) in enumerate(zip(expected, actual, strict=True)):
        similarity = cosine(old, new)
        overlap = len(top_terms(old) & top_terms(new)) / max(len(top_terms(old)), 1)
        if similarity < MIN_COSINE or overlap < MIN_TOP_TERM_OVERLAP:
            failures += 1
            print(f"text {number}: cosine={similarity:.5f} top{TOP_TERMS}_overlap={overlap:.3f}")
    print(f"{len(texts) - failures}/{len(texts)} texts equivalent "
          f"(cosine >= {MIN_COSINE}, top-{TOP_TERMS} overlap >= {MIN_TOP_TERM_OVERLAP})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
