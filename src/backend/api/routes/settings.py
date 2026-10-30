"""Administrator endpoints for runtime AI settings (prompts, models, retrieval choices)."""
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Body, Depends

from backend.api.auth import require_scope
from backend.application.use_cases.settings.settings_service import SettingsService
from backend.core.di.container import AppContainer
from backend.domain.entities.auth.principal import Scope
from backend.domain.settings.ai_behavior import RuntimeDefaultsCatalog

router = APIRouter(dependencies=[Depends(require_scope(Scope.SETTINGS_WRITE))])


@router.get("/", response_model=RuntimeDefaultsCatalog)
@inject
async def get_settings(
        service: SettingsService = Depends(Provide[AppContainer.services.settings_service]),
):
    """Return the effective settings (YAML defaults merged with saved overrides)."""
    return await service.get()


@router.patch("/", response_model=RuntimeDefaultsCatalog)
@inject
async def update_settings(
        updates: dict[str, Any] = Body(..., description="Partial settings; nested keys are deep-merged."),
        service: SettingsService = Depends(Provide[AppContainer.services.settings_service]),
):
    """Deep-merge a partial update into the current settings, validate, save, and return the result.

    Known issue in the application layer: an invalid update currently surfaces as HTTP 500,
    because SettingsService raises ValueError/ValidationError instead of InvalidInputError (422).
    That is fixed in SettingsService, not here, so every caller gets the right behavior.
    """
    return await service.save(updates)
