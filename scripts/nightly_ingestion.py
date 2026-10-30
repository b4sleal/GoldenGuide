"""Start tracked ingestion jobs and wait for their outcomes; bearer key is read from stdin.

Uses only the standard library so Actions needs no backend dependencies or database access.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_PREFIX = "/api/v1/admin"
FINAL_STATUSES = {"success", "partial_success", "failed", "cancelled"}
SITES = {"wlu", "students_wlu", "scholars_wlu"}
MAX_RESPONSE_BYTES = 1_048_576


class WorkflowError(Exception):
    """A safe, actionable workflow failure message."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the machine credential through an HTTP redirect.
        return None


class JobClient:
    def __init__(
        self,
        base_url: str,
        key: str,
        job_timeout: float,
        poll_seconds: float,
        total_timeout: float,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise WorkflowError(
                "Base URL must be an HTTPS origin without credentials, path, query or fragment"
            )
        if not key or any(c.isspace() for c in key):
            raise WorkflowError("A service key must be supplied on stdin")
        if min(job_timeout, poll_seconds, total_timeout) <= 0:
            raise WorkflowError("Timeouts and polling interval must be positive")
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.job_timeout = job_timeout
        self.poll_seconds = poll_seconds
        self.deadline = time.monotonic() + total_timeout
        self.opener = build_opener(NoRedirect())

    def request(self, method: str, path: str, deadline: float) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkflowError(
                "Polling deadline exceeded; the server job may still be running"
            )
        request = Request(
            self.base_url + path,
            method=method,
            data=b"" if method == "POST" else None,
            headers={
                "Authorization": f"Bearer {self.key}",
                "Accept": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=min(30, remaining)) as response:
                expected = 202 if method == "POST" else 200
                if response.status != expected:
                    raise WorkflowError(
                        f"{method} returned HTTP {response.status}; expected {expected}"
                    )
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise WorkflowError(
                f"{method} returned HTTP {exc.code}; submission is never automatically retried"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise WorkflowError(
                f"{method} connection failed; the server job may still be running"
            ) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise WorkflowError("API response exceeded the size limit")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise WorkflowError("API returned invalid JSON") from None
        if not isinstance(data, dict):
            raise WorkflowError("API response must be an object")
        return data

    def run(self, route: str, **params: str | int) -> None:
        deadline = min(self.deadline, time.monotonic() + self.job_timeout)
        path = f"{API_PREFIX}/{route}?{urlencode(params)}"
        accepted = self.request("POST", path, deadline)
        run_id = accepted.get("run_id")
        if type(run_id) is not int or run_id <= 0:
            raise WorkflowError("Submission returned an invalid run id")
        status_path = f"{API_PREFIX}/jobs/{run_id}"
        if accepted.get("status_url") != status_path:
            raise WorkflowError("Submission returned an unexpected status URL")
        print(f"Started {route}: run {run_id}", flush=True)
        while True:
            status = self.request("GET", status_path, deadline)
            state = status.get("status")
            if status.get("run_id") != run_id or state not in FINAL_STATUSES | {
                "queued",
                "running",
            }:
                raise WorkflowError(f"Invalid status response for run {run_id}")
            if status.get("finished") is not (state in FINAL_STATUSES):
                raise WorkflowError(f"Inconsistent completion state for run {run_id}")
            if state in FINAL_STATUSES:
                print(f"Finished {route}: run {run_id} {state}", flush=True)
                if state != "success":
                    raise WorkflowError(
                        f"Run {run_id} ended with {state}; subsequent jobs were not started"
                    )
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkflowError(
                    f"Polling deadline exceeded for run {run_id}; it may still be running"
                )
            time.sleep(min(self.poll_seconds, remaining))


def run_pipeline(
    client: JobClient, sites: list[str], terms: list[str], crawl_mode: str
) -> None:
    # Validate all inputs before the first state-changing request.
    if any(site not in SITES for site in sites) or any(
        not re.fullmatch(r"\d{6}", term) for term in terms
    ):
        raise WorkflowError("Unknown website or invalid six-digit registration term")
    if crawl_mode not in {"fresh", "update", "retry"}:
        raise WorkflowError("Invalid crawl mode")
    client.run("sources/academic-calendar/discover", mode=crawl_mode, concurrency=4)
    client.run("sources/academic-calendar/import", mode="update")
    for site in sites:
        client.run(
            "sources/websites/discover", site=site, mode=crawl_mode, concurrency=4
        )
        client.run("sources/websites/import", site=site, mode="update")
    if not terms:
        print("Registration refresh skipped: no LORIS terms configured", flush=True)
    for term in terms:
        client.run("sources/registration/export", term_code=term)
        client.run("sources/registration/import", term_code=term)
    for source in ["courses", "course-terms", "pages"]:
        client.run(f"indexing/{source}/sync", mode="update")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--sites", default="wlu students_wlu scholars_wlu")
    parser.add_argument(
        "--terms",
        default="",
        help="Space-separated LORIS term codes; empty skips registration",
    )
    parser.add_argument(
        "--crawl-mode", choices=["fresh", "update", "retry"], default="fresh"
    )
    parser.add_argument("--job-timeout-seconds", type=float, default=7200)
    parser.add_argument("--total-timeout-seconds", type=float, default=18000)
    parser.add_argument("--poll-seconds", type=float, default=15)
    args = parser.parse_args()
    try:
        client = JobClient(
            args.base_url,
            sys.stdin.read().strip(),
            args.job_timeout_seconds,
            args.poll_seconds,
            args.total_timeout_seconds,
        )
        run_pipeline(client, args.sites.split(), args.terms.split(), args.crawl_mode)
    except WorkflowError as exc:
        print(f"Nightly ingestion failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
