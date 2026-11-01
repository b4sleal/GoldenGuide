"""Pure tests: no environment access, network services or exporter startup."""
import pytest
from pydantic import ValidationError

from goldenguide_common.logging.bootstrap import _parse_bool
from goldenguide_common.logging.settings import TelemetrySettings


def test_sampling_ratio_is_bounded():
    with pytest.raises(ValidationError):
        TelemetrySettings(sample_ratio=1.2)


def test_production_requires_collector():
    with pytest.raises(ValidationError):
        TelemetrySettings(environment="production")


def test_boolean_parsing_is_explicit():
    assert _parse_bool("X", "true") is True
    assert _parse_bool("X", "false") is False
    with pytest.raises(ValueError):
        _parse_bool("X", "maybe")
