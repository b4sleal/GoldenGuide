"""History changes are same-origin only: another site can't delete or rate through the browser's cookie."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api.routes.chat import conversation_messages


class AllowAll:
    """Rate-limit store that always allows, so the request reaches the same-origin check."""

    async def consume(self, key, *, limit, window_seconds):
        return SimpleNamespace(allowed=True, retry_after_seconds=0)


@pytest.mark.parametrize(("method", "path"), [
    ("DELETE", "/api/v1/chat/conversations/00000000-0000-0000-0000-000000000000"),
    ("PUT", "/api/v1/chat/messages/1/feedback"),
])
def test_cross_site_history_changes_are_refused(app, method, path):
    with TestClient(app) as client:
        app.state.rate_limit_store = AllowAll()  # After startup, so startup can't replace it.
        response = client.request(method, path, json={"rating": "up"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_history_http_response_includes_rendered_content_without_internal_diagnostics(app):
    content = {"version": 1, "blocks": [
        {"type": "text", "text": "Sections"},
        {"type": "citation", "source_nums": [1], "urls": ["https://loris.wlu.ca"]},
        {"type": "table", "title": "Sections", "columns": ["Section"], "rows": [["A"]]},
    ]}
    history = SimpleNamespace(messages=AsyncMock(return_value=[{
        "id": 2, "position": 2, "role": "assistant", "content": "Sections", "status": "complete",
        "created_at": datetime.now(UTC), "answer_content": content,
        "sources": [{"title": "LORIS", "url": "https://loris.wlu.ca", "internal": "secret"}],
        "query_plan": {"internal": "plan"}, "trace_id": "private", "error_message": "private",
    }]))
    route = next(route for route in app.routes if getattr(route, "endpoint", None) == conversation_messages)
    dependency = next(item.call for item in route.dependant.dependencies if item.name == "history")
    app.dependency_overrides[dependency] = lambda: history

    with TestClient(app) as client:
        app.state.rate_limit_store = AllowAll()
        response = client.get(f"/api/v1/chat/conversations/{uuid4()}/messages")

    assert response.status_code == 200
    [message] = response.json()
    assert message["answer_content"] == content
    assert message["sources"][0]["title"] == "LORIS"
    assert not {"query_plan", "trace_id", "error_message"} & message.keys()
    assert "internal" not in message["sources"][0]
