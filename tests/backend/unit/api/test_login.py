from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api.routes.identity import callback


@pytest.mark.asyncio
async def test_oauth_state_mismatch_rejected_before_store_access():
    store = SimpleNamespace(consume=AsyncMock())
    request = SimpleNamespace(query_params={"state": "good", "code": "test"},
        cookies={"gg_oidc_state": "bad"}, app=SimpleNamespace(state=SimpleNamespace(
            auth_mode="oidc", oauth_transaction_store=store)))
    with pytest.raises(HTTPException) as exc:
        await callback(request)
    assert exc.value.status_code == 400
    store.consume.assert_not_called()


@pytest.mark.asyncio
async def test_consumed_oauth_state_cannot_replay():
    store = SimpleNamespace(consume=AsyncMock(return_value=None))
    request = SimpleNamespace(query_params={"state": "same", "code": "test"},
        cookies={"gg_oidc_state": "same"}, app=SimpleNamespace(state=SimpleNamespace(
            auth_mode="oidc", oauth_transaction_store=store)))
    with pytest.raises(HTTPException) as exc:
        await callback(request)
    assert exc.value.status_code == 400
    store.consume.assert_awaited_once_with("same")
