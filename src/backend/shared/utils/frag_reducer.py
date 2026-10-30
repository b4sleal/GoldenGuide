"""Combine partial records ("fragments") that describe the same entity into one record each."""
from collections.abc import Callable, Hashable, Iterable

from pydantic import BaseModel

from backend.shared.utils.deep_merge import deep_merge_dicts


def reduce_fragments[T: BaseModel](
        model_class: type[T],
        fragments: Iterable[T],
        key_func: Callable[[T], Hashable | None],
) -> list[T]:
    """Merge fragments that share a key; the result has one model per key, in first-seen order.

    Example: two scraped fragments for CP317, one with a description and one with prerequisites,
    become one CP317 record with both. Later fragments win for fields set in both.
    Fields that are None are skipped, so a fragment never erases a value another fragment supplied.
    Fragments whose key is None are dropped (they cannot be matched to an entity).
    """
    merged_map: dict[Hashable, dict] = {}

    for fragment in fragments:
        key = key_func(fragment)
        if key is None:
            continue

        raw_dict = fragment.model_dump(exclude_none=True)
        if key in merged_map:
            merged_map[key] = deep_merge_dicts(merged_map[key], raw_dict)
        else:
            merged_map[key] = raw_dict

    # Re-validate each merged dict, so the combined record must still satisfy the model.
    return [model_class(**data) for data in merged_map.values()]


def dedupe_fragments[T: BaseModel](
        model_class: type[T],
        fragments: Iterable[T],
        fields: Iterable[str],
) -> list[T]:
    """reduce_fragments() keyed on a tuple of field values, e.g. fields=("course_code", "term")."""
    fields = tuple(fields)
    return reduce_fragments(
        model_class=model_class,
        fragments=fragments,
        key_func=lambda fragment: tuple(getattr(fragment, field) for field in fields),
    )
