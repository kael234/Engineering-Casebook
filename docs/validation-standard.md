# Validation Standard

A publication is blocked if any blocking check fails.

## Knowledge checks — blocking
- IDs are unique and sequential; published IDs are never reused.
- Every referenced source, case or toolbox entity exists.
- The five required issue slots are present exactly once for all new normal issues from ISSUE-005 onward.
- Existing toolbox entities are reused instead of duplicated.
- Published case and issue paths remain immutable.

## Research checks — blocking
- Deep Dive has at least one Tier A primary source.
- Every case has an authoritative technical source.
- Important numerical claims trace to a cited source.
- Proprietary brands are named only when explicitly documented.
- Facts/findings/interpretations are distinguished where needed.
- Evidence gaps are recorded.

## Figure checks — blocking
For ISSUE-005 onward:
- Deep Dive has at least two meaningful SVG technical figures and every other case at least one.
- SVG parses and has `viewBox`, title and description.
- No unsupported dimensions or external dependencies.
- Labels are readable at publication size.
- Technical content agrees with the cited source material.

## PDF checks — blocking
For ISSUE-005 onward:
- The generated PDF is committed inside the issue package; a manifest may not point to an absent file.
- Normally exactly 3 A4 pages; a fourth requires a recorded override reason.
- Searchable text; embedded fonts; live source hyperlinks.
- No clipping, overlap or unreadable elements.
- Minimum body 8.5 pt, secondary 8 pt, sources/captions 7 pt.
- No large unexplained dead space that indicates layout failure.
- Figures remain legible when viewed at normal page scale.

## Legacy backfill exception
ISSUE-001 through ISSUE-004 pre-date the repository publisher. Their historical records may be less complete than the live publication contract. Any missing historical binary PDF, source snapshot or original figure asset must be declared explicitly in `issue.yml` using `legacy_backfill: true` and an archival-status field. A legacy manifest must never claim that an absent file exists.

This exception is archival only. It cannot be used by ISSUE-005 or later.

## Link health — warning only
A transiently unavailable external URL does not invalidate otherwise verified source metadata.

## Failure behaviour
Do not commit a partial publication package. Report the failed stage and preserve `main` unchanged.
