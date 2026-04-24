"""CLI for ftl-merge: merge PRs and reconcile beliefs."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def run(cmd, *, check=True, capture=True, cwd=None):
    """Run a command and return stdout.

    cmd can be a list of args or a string (split on whitespace).
    """
    if isinstance(cmd, str):
        cmd = cmd.split()
    result = subprocess.run(
        cmd, capture_output=capture, text=True, cwd=cwd
    )
    if check and result.returncode != 0:
        print(f"Error running: {' '.join(cmd)}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip() if capture else None


def parse_beliefs_from_issue(issue_body):
    """Extract belief IDs from issue body.

    Looks for patterns like:
    - `belief-id` in backticks
    - ## Belief\\n\\n`belief-id`
    - belief-id after "Belief:" or "Beliefs:"
    """
    beliefs = set()
    # Match backtick-wrapped belief IDs (kebab-case identifiers)
    for match in re.finditer(r"`([a-z][a-z0-9-]+(?:-[a-z0-9]+)+)`", issue_body):
        candidate = match.group(1)
        # Filter out things that aren't belief IDs
        if candidate.startswith(("src-", "tests-", "http")):
            continue
        beliefs.add(candidate)
    return sorted(beliefs)


def get_issue_for_pr(repo, pr_number):
    """Get the issue number a PR closes."""
    body = run(["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "body", "-q", ".body"])
    # Look for "Closes #N" or "Fixes #N"
    match = re.search(r"(?:closes|fixes|resolves)\s+#(\d+)", body, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def get_issue_body(repo, issue_number):
    """Get issue body text."""
    return run(["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "body", "-q", ".body"])


def merge_pr(repo, pr_number):
    """Merge a PR. Returns True on success, False on conflict."""
    result = subprocess.run(
        ["gh", "pr", "merge", str(pr_number), "--repo", repo, "--merge"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "not mergeable" in result.stderr.lower() or "conflict" in result.stderr.lower():
            return False
        print(f"Error merging PR #{pr_number}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return True


def load_network(cwd=None):
    """Load the reasons network as JSON."""
    result = subprocess.run(
        ["reasons", "export"],
        capture_output=True, text=True, cwd=cwd,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def has_outlist(belief_id, network_data):
    """Check if a belief has any outlist justifications (GATE belief)."""
    node = network_data.get("nodes", {}).get(belief_id)
    if not node:
        return False
    for j in node.get("justifications", []):
        if j.get("outlist"):
            return True
    return False


def retract_beliefs(beliefs, pr_number, cwd=None):
    """Retract beliefs using reasons CLI, skipping GATE beliefs.

    GATE beliefs have outlist justifications and should flip IN
    automatically via TMS propagation when their outlist nodes go OUT.
    Explicitly retracting them sets _retracted metadata which prevents
    propagation from restoring them.
    """
    network_data = load_network(cwd=cwd)
    if not network_data:
        print("  ERROR: Could not load network — skipping all retractions.", file=sys.stderr)
        print("  Run 'reasons retract' manually after fixing the issue.", file=sys.stderr)
        return
    for belief_id in beliefs:
        if has_outlist(belief_id, network_data):
            print(f"  Skip (GATE belief, will propagate): {belief_id}")
            continue
        result = subprocess.run(
            ["reasons", "retract", belief_id, "--reason", f"Fixed in PR #{pr_number}"],
            capture_output=True, text=True, cwd=cwd,
        )
        if result.returncode == 0:
            print(f"  Retracted: {belief_id}")
        else:
            print(f"  Skip (not found or already OUT): {belief_id}")


def export_beliefs():
    """Regenerate beliefs.md and network.json."""
    run(["reasons", "export-markdown", "-o", "beliefs.md"])
    from pathlib import Path
    network_json = run(["reasons", "export"])
    Path("network.json").write_text(network_json + "\n")
    print("  Updated beliefs.md and network.json")


def pull_repo(repo_path):
    """Pull latest from remote."""
    run(["git", "pull"], cwd=repo_path)


def cmd_merge(args):
    """Merge PRs and reconcile beliefs."""
    repo = args.repo
    pr_numbers = []
    for part in args.prs.split(","):
        part = part.strip().lstrip("#")
        if "-" in part:
            start, end = part.split("-", 1)
            pr_numbers.extend(range(int(start), int(end) + 1))
        else:
            pr_numbers.append(int(part))

    expert_dir = args.expert_dir
    code_dir = args.code_dir

    for pr_num in pr_numbers:
        print(f"\n=== PR #{pr_num} ===")

        # Step 1: Merge
        print(f"Merging PR #{pr_num}...")
        if not merge_pr(repo, pr_num):
            print(f"  CONFLICT — PR #{pr_num} is not mergeable.")
            if args.skip_conflicts:
                print("  Skipping (--skip-conflicts)")
                continue
            else:
                print("  Fix conflicts and re-run, or use --skip-conflicts")
                sys.exit(1)
        print(f"  Merged.")

        # Step 2: Find linked issue and beliefs
        if args.auto_retract:
            issue_num = get_issue_for_pr(repo, pr_num)
            if issue_num:
                print(f"  Linked issue: #{issue_num}")
                issue_body = get_issue_body(repo, issue_num)
                beliefs = parse_beliefs_from_issue(issue_body)
                if beliefs:
                    print(f"  Found {len(beliefs)} belief(s) to retract: {', '.join(beliefs)}")
                    retract_beliefs(beliefs, pr_num, cwd=expert_dir)
                else:
                    print("  No beliefs found in issue body")
            else:
                print("  No linked issue found")

    # Step 3: Pull code
    if code_dir:
        print(f"\nPulling latest to {code_dir}...")
        pull_repo(code_dir)

    # Step 4: Export beliefs
    if args.auto_retract and expert_dir:
        print(f"\nExporting beliefs...")
        run(["reasons", "export-markdown", "-o", "beliefs.md"], cwd=expert_dir)
        network_json = run(["reasons", "export"], cwd=expert_dir)
        (Path(expert_dir) / "network.json").write_text(network_json + "\n")
        print("  Updated beliefs.md and network.json")

    # Step 5: Commit belief updates
    if args.auto_retract and expert_dir and args.commit:
        print(f"\nCommitting belief updates...")
        run(["git", "add", "beliefs.md", "network.json"], cwd=expert_dir)
        merged = ", ".join(f"#{n}" for n in pr_numbers)
        run(
            ["git", "commit", "-m", f"Retract beliefs for merged PRs: {merged}"],
            cwd=expert_dir,
        )
        if args.push:
            run(["git", "push"], cwd=expert_dir)
            print("  Pushed.")

    print(f"\nDone. Merged {len(pr_numbers)} PR(s).")


def main():
    parser = argparse.ArgumentParser(
        prog="ftl-merge",
        description="Merge PRs and reconcile beliefs",
    )
    parser.add_argument(
        "prs",
        help="PR numbers to merge (e.g., '58', '60-66', '58,59,60')",
    )
    parser.add_argument(
        "--repo", "-r",
        default="benthomasson/ftl2",
        help="GitHub repo (default: benthomasson/ftl2)",
    )
    parser.add_argument(
        "--code-dir", "-c",
        default=None,
        help="Local code repo to pull after merging",
    )
    parser.add_argument(
        "--expert-dir", "-e",
        default=None,
        help="Code-expert knowledge base directory",
    )
    parser.add_argument(
        "--auto-retract", "-a",
        action="store_true",
        help="Auto-retract beliefs linked to closed issues",
    )
    parser.add_argument(
        "--skip-conflicts",
        action="store_true",
        help="Skip PRs with merge conflicts instead of aborting",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit belief updates to expert repo",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push belief updates after committing",
    )

    args = parser.parse_args()
    cmd_merge(args)
