"""Provider registry + remote-URL based detection."""

from __future__ import annotations

import re
import urllib.parse

from .base import Provider, UnsupportedProviderError
from .gitlab import GitLabProvider


_REGISTRY: list[type[Provider]] = [GitLabProvider]


_SSH_RE = re.compile(r"^(?:ssh://)?(?:[^@]+@)([^:/]+)[:/](.+?)(?:\.git)?/?$")


def parse_remote(remote_url: str) -> tuple[str, str]:
    """Return `(host, project_path)` for a git remote URL.

    Handles `https://host/group/project(.git)` and `git@host:group/project(.git)`.
    """
    m = _SSH_RE.match(remote_url)
    if m:
        return m.group(1), m.group(2)
    parsed = urllib.parse.urlparse(remote_url)
    if not parsed.hostname:
        raise SystemExit(f"could not parse remote URL: {remote_url}")
    path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return parsed.hostname, path.rstrip("/")


def detect(remote_url: str) -> Provider:
    host, project_path = parse_remote(remote_url)
    for cls in _REGISTRY:
        if cls.matches(remote_url):
            return cls(host=host, project_path=project_path)
    raise UnsupportedProviderError(
        f"no provider supports remote host {host!r} yet "
        f"(remote_url={remote_url}). Only GitLab is supported right now."
    )


__all__ = ["detect", "parse_remote", "Provider", "UnsupportedProviderError"]
