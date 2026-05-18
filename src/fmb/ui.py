"""Terminal rendering helpers for the pipeline status block."""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, TextIO


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def is_tty() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


_GLYPHS_TTY = {
    "success": "✓",
    "failed": "✗",
    "running": "●",
    "pending": "○",
    "created": "○",
    "waiting_for_resource": "○",
    "preparing": "○",
    "canceled": "⊘",
    "skipped": "⊘",
    "manual": "⏸",
    "scheduled": "⏱",
}
_GLYPHS_ASCII = {
    "success": "OK",
    "failed": "XX",
    "running": "**",
    "pending": "..",
    "created": "..",
    "waiting_for_resource": "..",
    "preparing": "..",
    "canceled": "--",
    "skipped": "--",
    "manual": "[]",
    "scheduled": "..",
}


def _glyph(status: str) -> str:
    table = _GLYPHS_TTY if is_tty() else _GLYPHS_ASCII
    return table.get(status, "?")


class StatusRenderer:
    """Renders a status block in place when stdout is a tty.

    All writes (status block + log lines) go through this object so they
    can be interleaved cleanly: log lines erase the previous status block,
    print themselves, then leave it to the next render() to redraw.
    """

    def __init__(self, log_file: TextIO | None = None, log_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._height = 0  # lines currently occupied by the status block
        self._tty = is_tty()
        self._log_file = log_file
        self.log_path = log_path
        self._last_status_lines: list[str] = []  # last rendered status, for the log

    def _erase_block(self) -> None:
        if not self._tty or self._height == 0:
            return
        # Move cursor up `height` lines, clear each.
        sys.stdout.write("\x1b[" + str(self._height) + "F")  # CSI n F = up + col 1
        sys.stdout.write("\x1b[0J")  # clear from cursor to end of screen
        self._height = 0

    def _log_lines(self, lines: list[str]) -> None:
        if self._log_file is None:
            return
        for line in lines:
            self._log_file.write(_strip_ansi(line) + "\n")
        self._log_file.flush()

    def render(self, pipeline: dict[str, Any], jobs: list[dict[str, Any]]) -> None:
        with self._lock:
            self._erase_block()
            lines = _format_block(pipeline, jobs, tty=self._tty)
            for line in lines:
                sys.stdout.write(line + "\n")
            sys.stdout.flush()
            self._height = len(lines) if self._tty else 0
            # Only append a status snapshot to the log when it changed; otherwise
            # the file fills up with identical blocks between polls.
            if lines != self._last_status_lines:
                self._log_lines(["--- status ---", *lines])
                self._last_status_lines = lines

    def print_log(self, job_name: str, line: str) -> None:
        with self._lock:
            self._erase_block()
            content = line if self._tty else _strip_ansi(line)
            sys.stdout.write(f"[{job_name}] {content}\n")
            sys.stdout.flush()
            self._log_lines([f"[{job_name}] {line}"])

    def write_note(self, line: str) -> None:
        """Write a one-off line (e.g. final pipeline status) to both stdout and the log."""
        with self._lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            self._log_lines([line])

    def detach(self) -> None:
        """Stop tracking the status block in place; subsequent output appends."""
        with self._lock:
            self._height = 0


def open_run_log() -> tuple[TextIO, Path]:
    """Open a fresh log file in the system temp dir for this fmb run."""
    fd, name = tempfile.mkstemp(prefix="fmb-ci-", suffix=".log")
    path = Path(name)
    f = os.fdopen(fd, "w", encoding="utf-8")
    return f, path


def _format_block(
    pipeline: dict[str, Any], jobs: list[dict[str, Any]], *, tty: bool
) -> list[str]:
    head = (
        f"pipeline #{pipeline.get('id', '?')} {_glyph(pipeline.get('status', ''))} "
        f"{pipeline.get('status', '')}  {pipeline.get('web_url', '')}"
    )
    rows = [head]
    name_w = max((len(j["name"]) for j in jobs), default=0)
    stage_w = max((len(j.get("stage", "")) for j in jobs), default=0)
    for j in jobs:
        rows.append(
            f"  {j.get('stage', ''):<{stage_w}}  "
            f"{j['name']:<{name_w}}  {_glyph(j['status'])} {j['status']}"
        )
    return rows
