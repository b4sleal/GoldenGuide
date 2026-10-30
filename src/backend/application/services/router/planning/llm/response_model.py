"""Lenient parsing of the LLM's retrieval plan: the one place untrusted LLM JSON enters the domain.

LLMs sometimes write one value where the schema has a list ("term": "winter"), one object where it
has a list of objects ("requests": {...}), or null for an object. LLMPlanResponse repairs exactly
those shapes, driven by the domain model's own field types, before normal validation; the domain
models stay pure data and strict everywhere else.
"""
import types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, model_validator

from backend.domain.entities.retrieval_plan import PreLLMExtraction

SCALARS = (str, int, float)


def unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """(inner annotation, whether None is allowed) for `X | None`."""
    if get_origin(annotation) in (Union, types.UnionType):
        inner = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(inner) == 1:
            return inner[0], len(inner) != len(get_args(annotation))
    return annotation, False


def is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def lenient_value(annotation: Any, value: Any) -> Any:
    """`value` wrapped in a list where `annotation` expects one, recursing into nested models."""
    annotation, _ = unwrap_optional(annotation)
    origin = get_origin(annotation)

    if origin is list:
        (item,) = get_args(annotation)
        # Booleans are never lists: "year": true stays invalid.
        if isinstance(value, dict) or (isinstance(value, SCALARS) and not isinstance(value, bool)):
            value = [value]
        if is_model(item) and isinstance(value, list):
            return [lenient_object(item, element) for element in value]
        return value

    if origin is dict and isinstance(value, dict):
        _, item = get_args(annotation)
        return {key: lenient_object(item, element) for key, element in value.items()} if is_model(item) else value

    if is_model(annotation):
        return lenient_object(annotation, value)

    return value


def lenient_object(model: type[BaseModel], data: Any) -> Any:
    """`data` reshaped to `model`'s field types; anything else is left for validation to judge."""
    if not isinstance(data, dict):
        return data

    result = dict(data)
    for name, field in model.model_fields.items():
        if name not in result:
            continue
        _, nullable = unwrap_optional(field.annotation)
        if result[name] is None and not nullable and field.default_factory is not None:
            del result[name]  # null for a required object: use its default (empty filters, empty plan).
            continue
        result[name] = lenient_value(field.annotation, result[name])
    return result


class LLMPlanResponse(PreLLMExtraction):
    """PreLLMExtraction as parsed from LLM output. Same JSON schema; lenient input shapes."""

    @model_validator(mode="before")
    @classmethod
    def lenient_shapes(cls, data: Any) -> Any:
        return lenient_object(PreLLMExtraction, data)
