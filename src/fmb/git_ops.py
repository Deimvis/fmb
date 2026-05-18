"""Thin wrappers around the `git` CLI."""

from __future__ import annotations

import subprocess


class GitError(SystemExit):
    """A `git` invocation failed. Carries stderr in the message."""


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    res = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and res.returncode != 0:
        stderr = res.stderr.strip() or res.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {stderr}")
    return res


def ensure_repo() -> None:
    res = _run("rev-parse", "--is-inside-work-tree", check=False)
    if res.returncode != 0 or res.stdout.strip() != "true":
        raise GitError("not inside a git work tree")


def add_all() -> None:
    _run("add", "-A")


def commit(message: str) -> None:
    _run("commit", "--allow-empty", "--allow-empty-message", "-m", message)


def push() -> None:
    """Push current branch. If no upstream is set, set it to origin/<branch>."""
    res = _run("push", check=False)
    if res.returncode == 0:
        # Forward git's stderr (push progress) so the user sees it.
        if res.stderr:
            print(res.stderr, end="")
        return
    stderr = res.stderr or ""
    if "has no upstream branch" in stderr or "no upstream branch" in stderr:
        branch = current_branch()
        res2 = _run("push", "-u", "origin", branch, check=False)
        if res2.returncode != 0:
            raise GitError(f"git push -u origin {branch} failed: {res2.stderr.strip()}")
        if res2.stderr:
            print(res2.stderr, end="")
        return
    raise GitError(f"git push failed: {stderr.strip()}")


def head_sha() -> str:
    return _run("rev-parse", "HEAD").stdout.strip()


def remote_url(name: str = "origin") -> str:
    return _run("remote", "get-url", name).stdout.strip()


def current_branch() -> str:
    return _run("symbolic-ref", "--short", "HEAD").stdout.strip()
