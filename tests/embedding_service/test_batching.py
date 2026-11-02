"""Token-budget batches bound padded tokens and cover every text exactly once."""

import pytest

from embedding_service.models.batching import token_budget_batches


def padded_tokens(batch: list[int], counts: list[int]) -> int:
    return len(batch) * max(counts[index] for index in batch)


@pytest.mark.parametrize(
    "counts",
    [[5, 512, 40, 512, 7, 300, 12, 512], [512] * 20, [3] * 100, [1]],
)
def test_every_batch_fits_and_every_text_appears_once(counts):
    batches = token_budget_batches(counts, max_batch_tokens=1024)

    assert sorted(index for batch in batches for index in batch) == list(range(len(counts)))
    assert all(padded_tokens(batch, counts) <= 1024 for batch in batches)


def test_short_texts_share_a_batch_and_long_texts_split():
    assert token_budget_batches([10] * 50, max_batch_tokens=1024) == [list(range(50))]
    assert len(token_budget_batches([512] * 6, max_batch_tokens=1024)) == 3


def test_text_at_the_budget_gets_its_own_batch():
    assert token_budget_batches([1024, 1], max_batch_tokens=1024) == [[1], [0]]


def test_empty_input_has_no_batches():
    assert token_budget_batches([], max_batch_tokens=1024) == []


def test_non_positive_budget_is_rejected():
    with pytest.raises(ValueError, match="positive"):
        token_budget_batches([1], max_batch_tokens=0)
