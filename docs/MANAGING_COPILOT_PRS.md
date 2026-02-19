# Managing Copilot PRs

This guide helps you manage Pull Requests created by GitHub Copilot, especially when dealing with failed or stale PRs.

## Understanding Copilot PR States

Copilot PRs can be in several states:

1. **[WIP] (Work in Progress)**: Active PRs where Copilot is still working
2. **Completed PRs** (no [WIP] prefix): PRs ready for review
3. **action_required**: CI failed and requires manual intervention
4. **Stale [WIP] PRs**: PRs that haven't been updated in days - likely failed or abandoned

## Identifying Stale PRs

A PR is considered "stale" if:
- Title contains `[WIP]`
- Created by Copilot
- No updates in 7+ days
- CI status shows `action_required` or `failure`

## Safe Cleanup Process

### Option 1: Manual Review and Closure

1. **Review each PR individually:**
   ```bash
   gh pr list --state open --author Copilot
   ```

2. **Check if the PR has useful changes:**
   ```bash
   gh pr diff <PR_NUMBER>
   ```

3. **Close with comment:**
   ```bash
   gh pr close <PR_NUMBER> --comment "Closing stale [WIP] PR"
   ```

### Option 2: Automated Cleanup Script

Use the provided script to identify and close stale PRs:

```bash
# Dry run - list stale PRs without closing
python tools/manage_stale_prs.py --dry-run

# Close stale PRs with no activity in 7+ days
python tools/manage_stale_prs.py --days 7 --close

# Close specific PR numbers
python tools/manage_stale_prs.py --pr-numbers 42,43,44 --close
```

**Prerequisites:**
- Install [GitHub CLI](https://cli.github.com/)
- Authenticate: `gh auth login`

### Option 3: GitHub Actions Automation

Add this workflow to `.github/workflows/close-stale-prs.yml`:

```yaml
name: Close Stale Copilot PRs

on:
  schedule:
    - cron: '0 0 * * 0'  # Run weekly on Sundays
  workflow_dispatch:  # Allow manual trigger

jobs:
  close-stale-prs:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      issues: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Close stale PRs
        uses: actions/stale@v9
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          days-before-stale: 7
          days-before-close: 0
          stale-pr-message: 'This [WIP] PR has had no activity for 7 days and appears to be abandoned. Closing automatically.'
          close-pr-message: 'Closed due to inactivity. Reopen if work should continue.'
          only-labels: 'WIP'
          exempt-pr-labels: 'keep-open,in-progress'
          stale-pr-label: 'stale'
```

## Current Stale PRs (as of Feb 2026)

The following PRs are identified as stale:

| PR # | Title | Status | Action |
|------|-------|--------|--------|
| #42 | [WIP] Complete remaining work on last task | Stale | Close |
| #43 | [WIP] Fix Copilot Action to prevent CI request spamming | Stale | Close |
| #44 | [WIP] Fix issues with instruction compliance | Stale | Close |
| #45 | [WIP] Update CI workflow to fix multiple Copilot issues | Stale | Close |
| #46 | [WIP] Add run outside Docker command to documentation | Stale | Close |
| #48 | [WIP] Address issues with failed PR requests | Active | Keep (current PR) |

### Recommended Actions

**Immediate cleanup (PRs #42-46):**
```bash
python tools/manage_stale_prs.py --pr-numbers 42,43,44,45,46 --close
```

**Or manually:**
```bash
for pr in 42 43 44 45 46; do
  gh pr close $pr --comment "Closing stale [WIP] PR - work appears to be abandoned or superseded"
done
```

## Preventing Future Buildup

1. **Monitor Copilot PRs regularly:**
   - Set up GitHub notifications for Copilot PRs
   - Review weekly with: `gh pr list --author Copilot`

2. **Enable automatic stale PR detection:**
   - Use the GitHub Actions workflow above
   - Configure to run weekly

3. **Close failed PRs quickly:**
   - Don't let [WIP] PRs linger more than 3-5 days
   - If Copilot stops updating a PR, close it and create a new issue

4. **Label system:**
   - Add `copilot-wip` label to active PRs
   - Add `keep-open` label to PRs that should persist
   - Add `failed` label to PRs that are definitively abandoned

## Recovery

If you accidentally close a PR that should stay open:

```bash
# Reopen PR
gh pr reopen <PR_NUMBER>

# Or restore from closed state
gh pr view <PR_NUMBER> --web
# Click "Reopen pull request" button
```

## Best Practices

1. **Don't leave [WIP] PRs open indefinitely** - Either complete them or close them
2. **Review Copilot PRs within 48 hours** - Catch issues early
3. **One task = One PR** - Don't try to fix multiple unrelated issues in one PR
4. **Clear the backlog** - Start fresh rather than trying to salvage failed PRs
5. **Document what went wrong** - Add comments explaining why a PR failed

## Safety Considerations

⚠️ **Before closing PRs:**
- Check if they have useful code changes
- Verify they aren't referenced by other PRs or issues
- Confirm they're truly abandoned (no recent comments/commits)

✅ **Safe to close if:**
- No activity in 7+ days
- CI status is `action_required` or `failure`
- No recent comments from human reviewers
- Changes are trivial or superseded by other PRs

❌ **Do NOT close if:**
- Has `keep-open` label
- Referenced in active issues
- Contains complex changes that would be hard to recreate
- Recent comments indicate work is ongoing
