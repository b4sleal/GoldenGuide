"""Infrastructure fixtures load verification policy from the application's YAML configuration."""
from pathlib import Path

import pytest
from omegaconf import OmegaConf

from backend.domain.settings.oidc import OIDCPolicy


@pytest.fixture
def oidc_policy():
    config = OmegaConf.load(Path(__file__).parents[4] / "configs/base/system_config.yml")
    return OIDCPolicy.model_validate(OmegaConf.to_container(config.system.oidc))
