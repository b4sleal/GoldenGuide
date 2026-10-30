"""Group items into batches that stay under a byte limit."""
from collections.abc import Callable, Iterable, Iterator


def batch_by_size[T](
        items: Iterable[T],
        max_bytes: int,
        size_of: Callable[[T], int],
        overhead: int = 0,
) -> Iterator[list[T]]:
    """Yield lists of items whose total size (plus `overhead` per batch) is at most `max_bytes`.

    Used where a service rejects oversized requests, e.g. Qdrant's 32 MB request limit when
    upserting vectors. Order is preserved. An item that cannot fit even alone raises ValueError
    rather than being silently dropped or sent and rejected later.
    """
    # Step 1: the per-batch overhead (envelope/JSON framing) must leave room for at least some data.
    if max_bytes <= overhead:
        raise ValueError(f"max_bytes ({max_bytes}) must be greater than overhead ({overhead})")

    batch: list[T] = []
    current_bytes = overhead

    for item in items:
        # Step 2: measure the item and reject impossible ones loudly.
        item_bytes = size_of(item)
        if item_bytes < 0:
            raise ValueError("Item size cannot be negative")
        if item_bytes + overhead > max_bytes:
            raise ValueError(f"Item of {item_bytes} bytes exceeds the {max_bytes}-byte batch limit")

        # Step 3: if this item would overflow the current batch, emit the batch and start a new one.
        if batch and current_bytes + item_bytes > max_bytes:
            yield batch
            batch = []
            current_bytes = overhead

        batch.append(item)
        current_bytes += item_bytes

    # Step 4: emit the final, partially filled batch.
    if batch:
        yield batch
