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

## Wayfinding operations

Used by `/wayfinder`. The map is one issue; its decision tickets are child issues.

- **Map**: create an issue labelled `wayfinder:map`. Tickets use `wayfinder:<type>` (`research`, `prototype`, `grilling`, or `task`).
- **Child ticket**: link it as a GitHub sub-issue. If sub-issues are unavailable, add it to a task list in the map and put `Part of #<map>` in the child body.
- **Blocking**: prefer native dependencies: `gh api --method POST repos/minh-dng/gdbminer/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Fetch the database ID with `gh api repos/minh-dng/gdbminer/issues/<blocker> --jq .id`; it is not the issue number or node ID. If dependencies are unavailable, use `Blocked by: #<n>, #<n>` in the child body.
- **Frontier**: read the map's open children; exclude assigned tickets and those with open blockers (`issue_dependencies_summary.blocked_by > 0`, or open issues in the fallback line). Select the first remaining ticket in map order.
- **Claim**: assign the ticket with `gh issue edit <n> --add-assignee @me` before other writes.
- **Resolve**: comment with the answer, close the ticket, then add a short summary and link to the map's Decisions-so-far. Keep the decision itself in the ticket.
