"""GitLab provider — talks to the REST API directly via stdlib."""

from __future__ import annotations

import os
import re
import sys
import threading
import time
import urllib.parse
from typing import Any

from .. import config, http, ui


TERMINAL_PIPELINE = {"success", "failed", "canceled", "skipped", "manual"}
TERMINAL_JOB = {"success", "failed", "canceled", "skipped", "manual"}

PIPELINE_WAIT_TIMEOUT = 60  # seconds to wait for pipeline to appear
PIPELINE_POLL = 3
TRACE_POLL = 1.5


class GitLabProvider:
    name = "gitlab"

    def __init__(self, host: str, project_path: str) -> None:
        self.host = host
        self.project_path = project_path
        self.token = config.token_for_domain(host) or os.environ.get("GITLAB_TOKEN")
        api_base = config.api_base_for(host) or f"https://{host}/api/v4"
        self.api_base = api_base.rstrip("/")
        self._project_encoded = urllib.parse.quote(project_path, safe="")
        self._project_url = f"{self.api_base}/projects/{self._project_encoded}"

    @classmethod
    def matches(cls, remote_url: str) -> bool:
        from . import parse_remote  # avoid circular import at module top
        try:
            host, _ = parse_remote(remote_url)
        except SystemExit:
            return False
        if host == "gitlab.com":
            return True
        if host.startswith("gitlab."):
            return True
        if config.token_for_domain(host):
            # Domain was explicitly registered as a gitlab provider in config.
            return True
        return False

    # -- API helpers ------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.token:
            raise SystemExit(
                f"no token for {self.host}. Configure it with: "
                f"fmb-config providers add gitlab {self.host} <token>"
            )
        return http.request_json(
            f"{self._project_url}{path}", token=self.token, params=params
        )

    def _find_pipeline(self, sha: str) -> dict[str, Any] | None:
        items = self._get(
            "/pipelines",
            params={"sha": sha, "order_by": "updated_at", "sort": "desc", "per_page": 1},
        )
        return items[0] if items else None

    def _get_pipeline(self, pipeline_id: int) -> dict[str, Any]:
        return self._get(f"/pipelines/{pipeline_id}")

    def _list_jobs(self, pipeline_id: int) -> list[dict[str, Any]]:
        return self._get(f"/pipelines/{pipeline_id}/jobs", params={"per_page": 100})

    def _get_job(self, job_id: int) -> dict[str, Any]:
        return self._get(f"/jobs/{job_id}")

    def _trace_url(self, job_id: int) -> str:
        return f"{self._project_url}/jobs/{job_id}/trace"

    # -- main watch -------------------------------------------------------

    def watch(self, commit_sha: str) -> int:
        log_file, log_path = ui.open_run_log()
        renderer = ui.StatusRenderer(log_file=log_file, log_path=log_path)
        sys.stdout.write(f"waiting for pipeline for {commit_sha[:12]}...\n")
        sys.stdout.flush()

        traced: dict[int, threading.Thread] = {}
        trace_stop: dict[int, threading.Event] = {}
        printed_final: set[int] = set()

        try:
            pipeline = self._wait_for_pipeline(commit_sha)
            if pipeline is None:
                renderer.write_note(
                    f"no pipeline appeared for {commit_sha[:12]} within "
                    f"{PIPELINE_WAIT_TIMEOUT}s; CI may be disabled. The push succeeded."
                )
                return 0

            pipeline_id = pipeline["id"]
            renderer.write_note(f"pipeline #{pipeline_id}  {pipeline.get('web_url', '')}")

            while True:
                pipeline = self._get_pipeline(pipeline_id)
                jobs = self._list_jobs(pipeline_id)
                renderer.render(pipeline, jobs)

                for job in jobs:
                    jid = job["id"]
                    status = job["status"]
                    if status == "running" and jid not in traced:
                        stop = threading.Event()
                        trace_stop[jid] = stop
                        t = threading.Thread(
                            target=self._stream_job_trace,
                            args=(job, renderer, stop),
                            daemon=True,
                        )
                        traced[jid] = t
                        t.start()

                if pipeline["status"] in TERMINAL_PIPELINE:
                    break
                time.sleep(PIPELINE_POLL)

            # Stop all streaming threads.
            for stop in trace_stop.values():
                stop.set()
            for t in traced.values():
                t.join(timeout=5)

            # Re-render final status before printing any missed traces.
            jobs = self._list_jobs(pipeline_id)
            renderer.render(pipeline, jobs)
            renderer.detach()

            # For jobs we never streamed (e.g. went pending → success between
            # polls), fetch the full trace once so the user still sees output.
            for job in jobs:
                jid = job["id"]
                if jid in traced or jid in printed_final:
                    continue
                if job["status"] not in TERMINAL_JOB:
                    continue
                printed_final.add(jid)
                self._print_full_trace(job, renderer)

            final = pipeline["status"]
            renderer.write_note(f"pipeline {final}")
            return 0 if final == "success" else 1
        finally:
            for stop in trace_stop.values():
                stop.set()
            renderer.detach()
            log_file.close()
            print(f"ci output saved to: {log_path}")

    def _wait_for_pipeline(self, sha: str) -> dict[str, Any] | None:
        deadline = time.monotonic() + PIPELINE_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            pl = self._find_pipeline(sha)
            if pl is not None:
                return pl
            time.sleep(2)
        return None

    def _stream_job_trace(
        self, job: dict[str, Any], renderer: "ui.StatusRenderer", stop: threading.Event
    ) -> None:
        jid = job["id"]
        name = job["name"]
        url = self._trace_url(jid)
        offset = 0
        carry = ""  # incomplete trailing line carried to next poll
        while not stop.is_set():
            try:
                text, new_offset = http.request_text_range(
                    url, token=self.token, byte_offset=offset
                )
            except http.APIError:
                # Trace endpoint sometimes 404s briefly when a job is starting.
                time.sleep(TRACE_POLL)
                continue
            if text:
                offset = new_offset
                buf = carry + text
                lines = buf.split("\n")
                carry = lines[-1]
                for line in lines[:-1]:
                    renderer.print_log(name, line)
            try:
                status = self._get_job(jid)["status"]
            except http.APIError:
                status = None
            if status in TERMINAL_JOB:
                # One more flush in case the final bytes arrived after our last read.
                try:
                    text, _ = http.request_text_range(
                        url, token=self.token, byte_offset=offset
                    )
                except http.APIError:
                    text = ""
                if text:
                    buf = carry + text
                    lines = buf.split("\n")
                    carry = lines[-1]
                    for line in lines[:-1]:
                        renderer.print_log(name, line)
                if carry:
                    renderer.print_log(name, carry)
                return
            time.sleep(TRACE_POLL)

    def _print_full_trace(self, job: dict[str, Any], renderer: "ui.StatusRenderer") -> None:
        url = self._trace_url(job["id"])
        try:
            text, _ = http.request_text_range(url, token=self.token, byte_offset=0)
        except http.APIError:
            return
        if not text.strip():
            return
        name = job["name"]
        for line in text.rstrip("\n").split("\n"):
            renderer.print_log(name, line)
