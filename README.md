# ftl-merge

Merge-and-reconcile workflow: merge PRs, retract beliefs, regenerate specs.

## Quick Start

```bash
# Install
uv tool install git+https://github.com/benthomasson/ftl-merge

# Merge a single PR and auto-retract linked beliefs
ftl-merge 58 --auto-retract --code-dir ~/git/faster-than-light2 --expert-dir ~/git/ftl2-expert

# Merge multiple PRs
ftl-merge 60-66 --auto-retract -c ~/git/faster-than-light2 -e ~/git/ftl2-expert --commit --push

# Skip PRs with merge conflicts
ftl-merge 60-66 --auto-retract --skip-conflicts
```

## What It Does

1. **Merges PRs** sequentially via `gh pr merge`
2. **Finds linked issues** by parsing "Closes #N" from PR body
3. **Extracts belief IDs** from issue body (backtick-wrapped kebab-case identifiers)
4. **Retracts beliefs** via `reasons retract` with audit trail
5. **Pulls code** to local repo
6. **Exports beliefs** — regenerates `beliefs.md` and `network.json`
7. **Commits and pushes** belief updates to the expert repo

## Options

| Flag | Description |
|------|-------------|
| `--repo`, `-r` | GitHub repo (default: `benthomasson/ftl2`) |
| `--code-dir`, `-c` | Local code repo to pull after merging |
| `--expert-dir`, `-e` | Code-expert knowledge base directory |
| `--auto-retract`, `-a` | Auto-retract beliefs linked to closed issues |
| `--skip-conflicts` | Skip conflicting PRs instead of aborting |
| `--commit` | Commit belief updates to expert repo |
| `--push` | Push after committing |

## How Belief Linking Works

Issues filed from code-expert contain belief IDs in backticks:

```markdown
## Belief

`circuit-breaker-zero-division-unguarded`
```

ftl-merge parses these and passes them to `reasons retract`.

## Requirements

- [gh](https://cli.github.com/) — GitHub CLI
- [reasons](https://github.com/benthomasson/reasons) — Reason maintenance system (for `--auto-retract`)
