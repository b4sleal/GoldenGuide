"""Recursive dictionary merge."""
import copy


def deep_merge_dicts(base: dict, updates: dict) -> dict:
    """Return a new dict with `updates` merged into `base`, recursing into nested dicts.

    Example: {"llm": {"model": "a", "temp": 0}} + {"llm": {"temp": 1}} -> {"llm": {"model": "a", "temp": 1}}
    A plain dict.update() would replace the whole "llm" dict and lose "model".
    Lists and other values are replaced, not merged. Neither input is modified.
    """
    result = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
