# Issue tracker: GitHub

Issues and specs for this repository live in GitHub Issues. Use `gh` from this checkout; it infers `minh-dng/gdbminer` from the `origin` remote.

## Common operations

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."`
- Close: `gh issue close <number> --comment "..."`

When a skill says to publish to the issue tracker, create a GitHub issue. When it asks for a relevant ticket, run `gh issue view <number> --comments`.

## Pull requests as a triage surface

**PRs as a request surface: no.** Triage applies to issues only. Change this setting if external pull requests should enter the triage queue.
