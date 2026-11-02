"""Token-budget batching: bound inference memory by padded tokens, not by text count."""

from collections.abc import Sequence


def token_budget_batches(token_counts: Sequence[int], max_batch_tokens: int) -> list[list[int]]:
    """Group text indices so each batch's padded size (texts x longest text) fits the budget.

    Texts are packed shortest first to minimise padding; callers restore input order with the
    returned indices. A text longer than the budget gets a batch of its own, so callers must
    truncate texts to at most ``max_batch_tokens`` tokens to keep the bound.
    """
    if max_batch_tokens <= 0:
        raise ValueError("max_batch_tokens must be positive")
    batches: list[list[int]] = []
    current: list[int] = []
    for index in sorted(range(len(token_counts)), key=token_counts.__getitem__):
        # Sorted ascending, so this text is the longest in the batch it joins.
        if current and (len(current) + 1) * token_counts[index] > max_batch_tokens:
            batches.append(current)
            current = []
        current.append(index)
    if current:
        batches.append(current)
    return batches
