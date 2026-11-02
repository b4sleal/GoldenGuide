"""The request guard and SPLADE settings reject configurations that would break the memory bound."""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from embedding_service.api.limits import build_text_limit
from goldenguide_common.contracts.embedding_models import SpladeSparseVectorizerSettings

SPLADE = {
    "name": "splade",
    "provider": "splade",
    "model_name": "prithivida/Splade_PP_en_v1",
    "max_length": 512,
    "max_batch_tokens": 8192,
    "pooling_chunk_size": 128,
    "max_concurrent_inferences": 1,
    "dtype": "float32",
    "device": "cuda",
    "runtime": "gpu",
}


def test_requests_within_the_limit_pass_and_larger_ones_get_413():
    enforce = build_text_limit(2)
    enforce(["a", "b"])
    with pytest.raises(HTTPException) as error:
        enforce(["a", "b", "c"])
    assert error.value.status_code == 413


def test_splade_settings_accept_the_configured_shape():
    assert SpladeSparseVectorizerSettings.model_validate(SPLADE).max_batch_tokens == 8192


@pytest.mark.parametrize(
    "override",
    [
        {"max_batch_tokens": 511},
        {"max_batch_tokens": 0},
        {"max_concurrent_inferences": 0},
        {"pooling_chunk_size": 0},
        {"dtype": "int8"},
    ],
)
def test_splade_settings_reject_unbounded_or_invalid_limits(override):
    with pytest.raises(ValidationError):
        SpladeSparseVectorizerSettings.model_validate({**SPLADE, **override})
