# Data Model

## Stable identifiers
`ISSUE-###`, `CASE-###`, `SRC-####`, `PROD-###`, `SYS-###`, `INT-###`, `FM-###`, `NOTE-###`. Numeric width may grow; IDs are never reused.

## Case
Canonical case front matter stores identity, revision, first issue, case role/type, outcome, evidence grade, disciplines, lifecycle stages, source IDs, toolbox relations, figure IDs, related cases and tags. Body contains engineering narrative and evidence gaps.

## Issue
A frozen publication manifest stores issue identity, date, revision, page count, five case slots, snapshot paths and final PDF metadata.

## Toolbox
- Products: exact proprietary identities only.
- Systems: generic engineering/construction systems.
- Interventions: reusable response patterns.
- Failure modes: physical/mechanical failure mechanisms.
- Notebook: calculations, checks, field triggers, specification lessons and decision aids.

## Source
Stores title, organisation/authors, publication date, authority tier, URL/DOI, access date/status and redistribution status.

## Snapshot rule
Each issue retains the exact case/source/figure presentation used at publication so later canonical corrections do not rewrite history.
