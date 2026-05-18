"""Persistent provider config for `fmb`.

Stores per-domain credentials at `$XDG_CONFIG_HOME/fmb/providers.json`
(falling back to `~/.config/fmb/providers.json`). Schema:

    {
      "gitlab": [
        {"domain": "gitlab.com", "token": "glpat-..."},
        {"domain": "gitlab.corp.example", "token": "glpat-...",
         "api_base": "https://gitlab.corp.example/api/v4"}
      ]
    }

`api_base` is optional; when absent the runtime derives
`https://<domain>/api/v4`.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from typing import Any


PROVIDERS = ("gitlab",)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "fmb"
    return Path.home() / ".config" / "fmb"


def providers_path() -> Path:
    return config_dir() / "providers.json"


def load_providers() -> dict[str, list[dict[str, str]]]:
    path = providers_path()
    if not path.exists():
        return {}
    try:
        with path.open("r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path}: invalid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: top-level must be an object")
    out: dict[str, list[dict[str, str]]] = {}
    for provider, entries in data.items():
        if not isinstance(entries, list):
            raise SystemExit(f"{path}: {provider!r} must be a list")
        norm: list[dict[str, str]] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict) or "domain" not in entry or "token" not in entry:
                raise SystemExit(
                    f"{path}: {provider!r}[{i}] must be an object with 'domain' and 'token'"
                )
            e: dict[str, str] = {
                "domain": str(entry["domain"]),
                "token": str(entry["token"]),
            }
            if "api_base" in entry and entry["api_base"]:
                e["api_base"] = str(entry["api_base"])
            norm.append(e)
        out[provider] = norm
    return out


def save_providers(data: dict[str, list[dict[str, str]]]) -> Path:
    path = providers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _entry_for_domain(domain: str) -> dict[str, str] | None:
    for entries in load_providers().values():
        for entry in entries:
            if entry["domain"] == domain:
                return entry
    return None


def token_for_domain(domain: str) -> str | None:
    entry = _entry_for_domain(domain)
    return entry["token"] if entry else None


def api_base_for(domain: str) -> str | None:
    entry = _entry_for_domain(domain)
    if entry is None:
        return None
    return entry.get("api_base")


def render_masked(data: dict[str, list[dict[str, str]]]) -> str:
    masked: dict[str, list[dict[str, str]]] = {}
    for provider, entries in data.items():
        out_entries: list[dict[str, str]] = []
        for e in entries:
            row = {"domain": e["domain"], "token": "*" * 8}
            if "api_base" in e:
                row["api_base"] = e["api_base"]
            out_entries.append(row)
        masked[provider] = out_entries
    return json.dumps(masked, indent=2) + "\n"


def cmd_list() -> int:
    data = load_providers()
    if not data:
        print(f"(no providers configured at {providers_path()})")
        return 0
    print(f"# {providers_path()}")
    print(render_masked(data), end="")
    return 0


def _upsert(
    provider: str, domain: str, token: str, api_base: str | None
) -> tuple[Path, bool]:
    data = load_providers()
    entries = data.setdefault(provider, [])
    updated = False
    for entry in entries:
        if entry["domain"] == domain:
            entry["token"] = token
            if api_base:
                entry["api_base"] = api_base
            elif "api_base" in entry:
                del entry["api_base"]
            updated = True
            break
    if not updated:
        new_entry: dict[str, str] = {"domain": domain, "token": token}
        if api_base:
            new_entry["api_base"] = api_base
        entries.append(new_entry)
    return save_providers(data), updated


def cmd_add(
    provider: str | None,
    domain: str | None,
    token: str | None,
    api_base: str | None,
) -> int:
    """Add or update a provider. All-absent → interactive prompts.
    All-of-(provider,domain,token) present → non-interactive (api_base optional).
    Any other partial combination is a usage error."""
    required = (provider, domain, token)
    supplied = [v for v in required if v is not None]
    if len(supplied) not in (0, 3):
        raise SystemExit(
            "fmb-config providers add: pass either no positional args (interactive) "
            "or at least <provider> <domain> <token> (with optional <api_base>)"
        )

    if not supplied:
        provider = _prompt_choice("Provider", PROVIDERS)
        default_domain = "gitlab.com"
        raw_domain = input(f"Domain [{default_domain}]: ").strip()
        domain = raw_domain or default_domain
        raw_api = input("API base URL (optional, blank to derive): ").strip()
        api_base = raw_api or None
        token = getpass.getpass("Token (hidden): ").strip()
        if not token:
            raise SystemExit("token required")
    else:
        assert provider is not None and domain is not None and token is not None
        if provider not in PROVIDERS:
            raise SystemExit(
                f"unknown provider {provider!r}; expected one of: {', '.join(PROVIDERS)}"
            )
        if not domain:
            raise SystemExit("domain must be non-empty")
        if not token:
            raise SystemExit("token must be non-empty")

    path, updated = _upsert(provider, domain, token, api_base)
    action = "updated" if updated else "added"
    print(f"{action} {provider}/{domain} in {path}")
    return 0


def _prompt_choice(label: str, choices: tuple[str, ...]) -> str:
    suffix = f" [{'/'.join(choices)}]"
    while True:
        val = input(f"{label}{suffix}: ").strip()
        if val in choices:
            return val
        print(f"  expected one of: {', '.join(choices)}")
