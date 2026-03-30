# ftl-merge

Merge PRs and reconcile beliefs — merge-and-reconcile workflow for code-expert knowledge bases.

## How to Run

Try these in order until one works:
1. `ftl-merge 58 --auto-retract` (if installed via `uv tool install`)
2. `uv run ftl-merge 58 --auto-retract` (if in the repo with pyproject.toml)
3. `uvx --from git+https://github.com/benthomasson/ftl-merge ftl-merge 58 --auto-retract` (fallback)

## What It Does

Automates the post-PR-merge workflow:
1. Merges PRs sequentially via `gh pr merge`
2. Finds linked issues by parsing "Closes #N" from PR body
3. Extracts belief IDs from issue body (backtick-wrapped kebab-case identifiers)
4. Retracts beliefs via `reasons retract` with audit trail
5. Pulls code to local repo
6. Exports beliefs — regenerates `beliefs.md` and `network.json`
7. Optionally commits and pushes belief updates

## Common Commands

### Merge a single PR
```bash
ftl-merge 58 -r benthomasson/ftl2
```

### Merge and auto-retract beliefs
```bash
ftl-merge 58 --auto-retract -c ~/git/faster-than-light2 -e ~/git/ftl2-expert
```

### Merge a range of PRs
```bash
ftl-merge 60-66 --auto-retract -c ~/git/faster-than-light2 -e ~/git/ftl2-expert
```

### Merge multiple PRs with commit and push
```bash
ftl-merge 58,59,60 --auto-retract -c ~/git/faster-than-light2 -e ~/git/ftl2-expert --commit --push
```

### Skip PRs with merge conflicts
```bash
ftl-merge 60-66 --auto-retract --skip-conflicts
```

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--repo` | `-r` | GitHub repo (default: `benthomasson/ftl2`) |
| `--code-dir` | `-c` | Local code repo to pull after merging |
| `--expert-dir` | `-e` | Code-expert knowledge base directory |
| `--auto-retract` | `-a` | Auto-retract beliefs linked to closed issues |
| `--skip-conflicts` | | Skip conflicting PRs instead of aborting |
| `--commit` | | Commit belief updates to expert repo |
| `--push` | | Push after committing |

## Natural Language

If the user says:
- "merge PR 58" → `ftl-merge 58`
- "merge and retract PR 58" → `ftl-merge 58 --auto-retract -c ~/git/faster-than-light2 -e ~/git/ftl2-expert`
- "merge PRs 60 through 66" → `ftl-merge 60-66 --auto-retract --skip-conflicts`
- "merge all anti-pattern PRs" → look up PR numbers first, then `ftl-merge N,N,N --auto-retract`
- "merge and push belief updates" → add `--commit --push`

## How Belief Linking Works

Issues filed from code-expert contain belief IDs in backticks in the issue body:

```markdown
## Belief

`circuit-breaker-zero-division-unguarded`
```

ftl-merge parses these and passes them to `reasons retract`. The retraction cascades automatically — derived beliefs that depended on the retracted belief update their status.

## Requirements

- [gh](https://cli.github.com/) — GitHub CLI (authenticated)
- [reasons](https://github.com/benthomasson/reasons) — Reason maintenance system (for `--auto-retract`)
