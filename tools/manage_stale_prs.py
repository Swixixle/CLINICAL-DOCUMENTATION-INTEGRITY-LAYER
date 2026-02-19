#!/usr/bin/env python3
"""
Script to identify and optionally close stale Copilot PRs.

This script helps manage failed or abandoned Copilot PRs that are marked as [WIP]
and haven't had activity in a configurable number of days.

Usage:
    # Dry run (list stale PRs without closing)
    python tools/manage_stale_prs.py --dry-run
    
    # Close stale PRs older than 7 days
    python tools/manage_stale_prs.py --days 7
    
    # Close specific PR numbers
    python tools/manage_stale_prs.py --pr-numbers 42,43,44
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any


def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage stale Copilot PRs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List stale PRs without closing them (default)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Consider PRs stale if no activity in this many days (default: 7)",
    )
    parser.add_argument(
        "--pr-numbers",
        type=str,
        help="Comma-separated list of specific PR numbers to close (e.g., '42,43,44')",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Actually close the stale PRs (requires GitHub CLI 'gh' to be installed and authenticated)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="Swixixle/CLINICAL-DOCUMENTATION-INTEGRITY-LAYER",
        help="GitHub repository (default: Swixixle/CLINICAL-DOCUMENTATION-INTEGRITY-LAYER)",
    )
    return parser.parse_args()


def get_open_prs(repo: str) -> List[Dict[str, Any]]:
    """Fetch open PRs using GitHub CLI."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--json",
                "number,title,updatedAt,author,isDraft,labels",
                "--limit",
                "100",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching PRs: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: GitHub CLI 'gh' not found. Please install it from https://cli.github.com/",
            file=sys.stderr,
        )
        sys.exit(1)


def is_stale_pr(pr: Dict[str, Any], days_threshold: int) -> bool:
    """Determine if a PR is stale based on criteria."""
    # Must have [WIP] in title
    if "[WIP]" not in pr["title"]:
        return False

    # Must be from Copilot (case-insensitive check)
    # In this repository, GitHub Copilot PRs use the login "Copilot"
    author_login = pr["author"]["login"].lower()
    if author_login not in ("copilot", "github-copilot[bot]", "copilot[bot]"):
        return False

    # Check last update time
    updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
    threshold_date = datetime.now(timezone.utc) - timedelta(days=days_threshold)

    return updated_at < threshold_date


def close_pr(repo: str, pr_number: int, comment: str) -> bool:
    """Close a PR with a comment."""
    import subprocess

    try:
        # Add comment
        subprocess.run(
            [
                "gh",
                "pr",
                "comment",
                str(pr_number),
                "--repo",
                repo,
                "--body",
                comment,
            ],
            check=True,
            capture_output=True,
        )

        # Close PR
        subprocess.run(
            ["gh", "pr", "close", str(pr_number), "--repo", repo],
            check=True,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error closing PR #{pr_number}: {e.stderr}", file=sys.stderr)
        return False


def main():
    args = parse_args()

    # Get open PRs
    print(f"Fetching open PRs from {args.repo}...")
    all_prs = get_open_prs(args.repo)
    print(f"Found {len(all_prs)} open PRs\n")

    # Filter to specific PR numbers if provided
    if args.pr_numbers:
        target_numbers = [int(n.strip()) for n in args.pr_numbers.split(",")]
        target_prs = [pr for pr in all_prs if pr["number"] in target_numbers]
        print(f"Targeting specific PRs: {target_numbers}")
    else:
        # Filter to stale PRs
        target_prs = [pr for pr in all_prs if is_stale_pr(pr, args.days)]
        print(f"Found {len(target_prs)} stale [WIP] Copilot PRs")

    if not target_prs:
        print("No PRs to process.")
        return

    # Display PRs
    print("\n" + "=" * 80)
    print("PRs to be closed:")
    print("=" * 80)
    for pr in target_prs:
        print(f"\nPR #{pr['number']}: {pr['title']}")
        print(f"  Last updated: {pr['updatedAt']}")
        print(f"  Author: {pr['author']['login']}")
        print(f"  URL: https://github.com/{args.repo}/pull/{pr['number']}")

    # Close PRs if requested
    if args.close:
        print("\n" + "=" * 80)
        print("Closing PRs...")
        print("=" * 80)

        close_comment = (
            "Closing this stale [WIP] PR as it appears to be abandoned or superseded. "
            "If this PR should remain open, please reopen it and remove the [WIP] prefix."
        )

        for pr in target_prs:
            print(f"\nClosing PR #{pr['number']}...", end=" ")
            if close_pr(args.repo, pr["number"], close_comment):
                print("✓ Closed")
            else:
                print("✗ Failed")
    else:
        print("\n" + "=" * 80)
        print("DRY RUN MODE - No PRs were closed")
        print("To actually close these PRs, run with --close flag")
        print("=" * 80)


if __name__ == "__main__":
    main()
