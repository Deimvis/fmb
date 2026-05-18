# fmb

Fast commit + push + watch CI.

```
fmb [message words ...]
```

Stages everything (`git add -A`), commits with the joined positional args as
the message (empty message is allowed), pushes to the upstream of the current
branch (or `origin <branch>` if no upstream is set), then watches the CI
pipeline for the just-pushed commit. Only the `git` CLI is required at runtime.

GitLab is the only provider supported right now; the codebase is structured
so other providers can be added.

## Install

```
pip install -e .
```

This installs two console scripts: `fmb` and `fmb-config`.

## Configure providers

Tokens and (optional) API base URLs are stored at
`$XDG_CONFIG_HOME/fmb/providers.json` (falling back to
`~/.config/fmb/providers.json`), file mode `0600`.

```
fmb-config providers add                                        # interactive
fmb-config providers add gitlab gitlab.com glpat-xxxxxxxxxxxx   # non-interactive
fmb-config providers add gitlab gitlab.corp.example glpat-xxx https://gitlab.corp.example/api/v4
fmb-config providers                                            # list (masked)
```

If no entry is configured for the remote host, `fmb` falls back to
`GITLAB_TOKEN` from the environment.

## Notes

- The commit is created with `--allow-empty --allow-empty-message`, so
  re-running `fmb` on a clean tree still produces a (empty) commit, pushes,
  and re-watches CI. Run with arguments only when you mean to commit changes.
- Exit code matches the final pipeline status: `0` for `success`, non-zero
  otherwise.
