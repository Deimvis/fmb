"""`fmb` entrypoint: commit, push, watch CI."""

from __future__ import annotations

import sys

from . import git_ops, providers


USAGE = """\
usage: fmb [message words ...]

Stages all changes, commits with the joined positional args as the message
(empty message allowed), pushes to origin, then watches the CI pipeline for
the resulting commit. Only GitLab is supported right now.

Configure provider tokens with:
  fmb-config providers add gitlab <domain> <token> [api_base]
"""


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        sys.exit(0)

    message = " ".join(argv)

    git_ops.ensure_repo()
    git_ops.add_all()
    git_ops.commit(message)
    git_ops.push()

    sha = git_ops.head_sha()
    remote_url = git_ops.remote_url("origin")
    provider = providers.detect(remote_url)
    sys.exit(provider.watch(sha))


if __name__ == "__main__":
    main()
