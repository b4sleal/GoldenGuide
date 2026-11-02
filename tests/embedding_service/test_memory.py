"""Memory observations use current RSS and preserve document response bodies."""

from unittest.mock import Mock

import pytest

from embedding_service.api import memory


def test_reads_current_not_peak_rss(tmp_path):
    status = tmp_path / "status"
    status.write_text("VmHWM:\t9000 kB\nVmRSS:\t1234 kB\n", encoding="ascii")
    assert memory.read_rss_kib(status) == 1234
    assert memory.read_rss_kib(tmp_path / "missing") is None
    status.write_text("Name:\tpython\n", encoding="ascii")
    assert memory.read_rss_kib(status) is None


@pytest.mark.parametrize("rss", [1234, None])
async def test_samples_document_responses_and_throttles_info(monkeypatch, rss):
    log = Mock()
    monkeypatch.setattr(memory, "logger", log)
    monkeypatch.setattr(memory, "read_rss_kib", lambda: rss)
    ticks = iter([0, 20, 60])
    monkeypatch.setattr(memory, "monotonic", lambda: next(ticks))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"vectors": []}'})

    async def receive():
        return {"type": "http.request", "body": b""}

    middleware = memory.MemoryObservationMiddleware(app, info_interval_seconds=60)
    for path in ["/embed/documents", "/sparse/documents", "/embed/documents"]:
        messages = []

        async def send(message):
            messages.append(message)

        await middleware({"type": "http", "path": path}, receive, send)
        assert messages[1]["body"] == b'{"vectors": []}'
        assert messages[0]["headers"] == (
            [(b"x-embedding-rss-kib", b"1234")] if rss is not None else []
        )
    assert log.debug.call_count == 3
    assert log.info.call_count == 2


@pytest.mark.parametrize("path,status", [("/health", 200), ("/embed/query", 200), ("/embed/documents", 401)])
async def test_does_not_sample_other_routes_or_auth_failures(monkeypatch, path, status):
    sample = Mock()
    monkeypatch.setattr(memory, "read_rss_kib", sample)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": status, "headers": []})

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        pass

    await memory.MemoryObservationMiddleware(app, 60)({"type": "http", "path": path}, receive, send)
    sample.assert_not_called()
