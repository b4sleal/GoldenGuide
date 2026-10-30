"""The Actions client waits for real completion and never replays an uncertain POST."""

import ast
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from scripts import nightly_ingestion
from scripts.nightly_ingestion import JobClient, NoRedirect, WorkflowError, run_pipeline


def response(data, status=200):
    raw = io.BytesIO(json.dumps(data).encode())
    raw.status = status
    return raw


def client_with(*responses):
    client = JobClient("https://example.com", "secret-test-key", 10, 0.001, 20)
    client.opener = SimpleNamespace(open=Mock(side_effect=responses))
    return client


ACCEPTED = {"run_id": 5, "status_url": "/api/v1/admin/jobs/5"}


def test_client_syntax_is_compatible_with_ubuntu_runner_python():
    ast.parse(Path(nightly_ingestion.__file__).read_text(), feature_version=(3, 12))


def test_poll_until_success(capsys):
    client = client_with(
        response(ACCEPTED, 202),
        response({"run_id": 5, "status": "running", "finished": False}),
        response({"run_id": 5, "status": "success", "finished": True}),
    )
    client.run("indexing/pages/sync", mode="update")
    calls = client.opener.open.call_args_list
    assert [call.args[0].method for call in calls] == ["POST", "GET", "GET"]
    assert "secret-test-key" not in capsys.readouterr().out


@pytest.mark.parametrize("state", ["partial_success", "failed", "cancelled"])
def test_unsuccessful_terminal_status_fails(state):
    client = client_with(
        response(ACCEPTED, 202),
        response({"run_id": 5, "status": state, "finished": True}),
    )
    with pytest.raises(WorkflowError, match=state):
        client.run("sources/websites/discover", site="wlu")


@pytest.mark.parametrize(
    "error",
    [
        URLError("secret-test-key"),
        HTTPError("https://example.com", 409, "secret-test-key", {}, None),
    ],
)
def test_submission_failures_are_not_retried_and_errors_are_safe(error):
    client = client_with(error)
    with pytest.raises(WorkflowError) as exc:
        client.run("indexing/pages/sync")
    assert client.opener.open.call_count == 1
    assert "secret-test-key" not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/jobs/5",
        "//evil.com/jobs/5",
        "/api/v1/admin/jobs/4",
        "/api/v1/admin/jobs/5?key=x",
    ],
)
def test_unexpected_status_urls_are_rejected_before_bearer_can_be_sent(url):
    client = client_with(response({**ACCEPTED, "status_url": url}, 202))
    with pytest.raises(WorkflowError, match="status URL"):
        client.run("indexing/pages/sync")
    assert client.opener.open.call_count == 1


def test_redirects_are_not_followed():
    assert (
        NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.com")
        is None
    )


def test_deadline_expires_without_another_submission():
    client = client_with()
    client.deadline = 0
    with pytest.raises(WorkflowError, match="deadline"):
        client.run("indexing/pages/sync")
    client.opener.open.assert_not_called()


def test_pipeline_order_and_input_validation_before_any_network_request():
    client = SimpleNamespace(run=Mock())
    run_pipeline(client, ["wlu"], ["202609"], "fresh")
    assert [c.args[0] for c in client.run.call_args_list] == [
        "sources/academic-calendar/discover",
        "sources/academic-calendar/import",
        "sources/websites/discover",
        "sources/websites/import",
        "sources/registration/export",
        "sources/registration/import",
        "indexing/courses/sync",
        "indexing/course-terms/sync",
        "indexing/pages/sync",
    ]
    client.run.reset_mock()
    with pytest.raises(WorkflowError):
        run_pipeline(client, ["wlu"], ["invalid"], "fresh")
    client.run.assert_not_called()


def test_pipeline_stops_after_a_failed_stage():
    client = SimpleNamespace(run=Mock(side_effect=WorkflowError("partial_success")))
    with pytest.raises(WorkflowError):
        run_pipeline(client, ["wlu"], [], "fresh")
    assert client.run.call_count == 1
