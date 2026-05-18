"""Provider abstraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class UnsupportedProviderError(SystemExit):
    """Raised when no registered provider matches the remote URL."""


@runtime_checkable
class Provider(Protocol):
    name: str

    @classmethod
    def matches(cls, remote_url: str) -> bool: ...

    def watch(self, commit_sha: str) -> int:
        """Watch CI for `commit_sha`. Returns an exit code."""
        ...
