"""Tiny urllib-based HTTP helper for talking to provider APIs."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30


class APIError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"{status} {url}: {body[:500]}")
        self.status = status
        self.url = url
        self.body = body


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)


def _open(
    url: str,
    *,
    method: str,
    token: str | None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    headers = {"User-Agent": "fmb/0.1"}
    if token:
        headers["PRIVATE-TOKEN"] = token
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise APIError(e.code, url, body) from e
    except urllib.error.URLError as e:
        raise APIError(0, url, str(e.reason)) from e


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    full = _build_url(url, params)
    _, body, _ = _open(full, method=method, token=token)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def request_text_range(
    url: str,
    *,
    token: str | None = None,
    byte_offset: int = 0,
) -> tuple[str, int]:
    """Fetch `url` as text starting at `byte_offset`. Returns (new_text, new_offset).

    Uses HTTP Range when possible; if the server ignores Range and returns 200
    with the full body, slice in Python.
    """
    headers = {"Range": f"bytes={byte_offset}-"} if byte_offset > 0 else None
    try:
        status, body, _ = _open(url, method="GET", token=token, extra_headers=headers)
    except APIError as e:
        # 416 = range past end-of-resource; treat as "no new bytes".
        if e.status == 416:
            return "", byte_offset
        raise
    text = body.decode("utf-8", errors="replace")
    if status == 200 and byte_offset > 0:
        # Server didn't honor Range; slice client-side.
        text = text[byte_offset:] if byte_offset <= len(text) else ""
        new_offset = byte_offset + len(text.encode("utf-8"))
    elif status == 206:
        new_offset = byte_offset + len(body)
    else:
        new_offset = len(body)
    return text, new_offset
