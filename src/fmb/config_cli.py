"""`fmb-config` entrypoint."""

from __future__ import annotations

import argparse
import sys

from . import config


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = argparse.ArgumentParser(
        prog="fmb-config", description="manage fmb configuration"
    )
    sub = parser.add_subparsers(dest="topic", required=True)

    providers = sub.add_parser("providers", help="manage provider credentials")
    providers_actions = providers.add_subparsers(dest="action")
    add = providers_actions.add_parser(
        "add",
        help=(
            "add or update a provider. With no positional args, prompts "
            "interactively. With provider/domain/token, runs non-interactively."
        ),
    )
    add.add_argument("provider", nargs="?", choices=config.PROVIDERS)
    add.add_argument("domain", nargs="?", help="e.g. gitlab.com or gitlab.corp.example")
    add.add_argument("token", nargs="?", help="auth token")
    add.add_argument(
        "api_base",
        nargs="?",
        help="optional API base URL, e.g. https://gitlab.corp.example/api/v4",
    )
    providers_actions.add_parser("list", help="list configured providers (tokens masked)")

    args = parser.parse_args(argv)
    if args.topic != "providers":
        sys.exit(2)
    if args.action in (None, "list"):
        sys.exit(config.cmd_list())
    if args.action == "add":
        sys.exit(config.cmd_add(args.provider, args.domain, args.token, args.api_base))
    sys.exit(2)


if __name__ == "__main__":
    main()
