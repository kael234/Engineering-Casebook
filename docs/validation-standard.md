# Validation Standard

A publication is blocked if any blocking check fails.

## Knowledge checks — blocking
- IDs are unique and sequential; published IDs are never reused.
- Every referenced source, case or toolbox entity exists.
- The five required issue slots are present exactly once for all normal issues from ISSUE-005 onward.
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
- Technical content agrees with cited source material.

## Deterministic render checks — blocking
The repository-owned `Casebook Deterministic Publisher` is the normal binary-generation path.

Before it records `status: rendered`, the workflow must verify:
- `issue.yml`, issue Markdown, both snapshots and every listed SVG exist inside the issue directory;
- committed `PAGE N` markers are unique, contiguous and equal the declared `page_count`;
- image paths cannot escape the issue directory and resolve only to local SVG files;
- the renderer produces exactly 3 or 4 A4 pages as declared;
- four pages have a non-empty `page_count_override_reason`;
- searchable-text extraction contains at least 1,800 words and 10,000 non-whitespace characters;
- live URI annotations are at least the number of issue slots;
- every font reported by `pdffonts` is embedded;
- preview JPEG is valid and practically sized;
- exact PDF/preview byte sizes and SHA-256 values are written to `issue.yml`;
- `render.mechanical_validation` is `passed` and `render.visual_review` is `pending`;
- `catalog/issues.json` remains draft until visual review;
- obsolete `.handoff/` state is absent after a successful render.

A failed render must not change the issue PDF, preview, metadata or stale recovery state. Workflow logs and uploaded page diagnostics identify the first failed gate.

## Visual publication review — blocking
The 05:00 publisher reviews the exact branch PDF whose hash is recorded in `issue.yml`.

Render every page to an image and reject:
- clipping or overlap;
- unreadable body, source or caption text;
- weak hierarchy or module separation;
- diagrams whose labels or mechanism are illegible at normal page scale;
- a visibly compressed three-page issue that should use four pages;
- a thin fourth-page overflow with large avoidable dead zones;
- large unexplained dead space indicating layout failure;
- artifact hashes/sizes that do not match `issue.yml`.

Minimum typography remains body 8.5 pt, secondary 8 pt, sources/captions 7 pt. The normal targets in `templates/magazine-style.md` are the design standard; minimums are not a pagination strategy.

Only after this review passes may the publisher:
- set `status: published`;
- set `render.visual_review: passed`;
- update `catalog/issues.json` to `published`;
- normalize stale notes;
- apply supervised or consumer-mode merge policy.

## Post-publication checks — blocking
Before a PR is approved or auto-merged:
- the current branch PDF/preview exist at declared paths, sizes and SHA-256 hashes;
- `issue.yml` and `catalog/issues.json` both record `published`;
- visual review is recorded as passed;
- `.handoff/` is absent;
- the PR is mergeable;
- the PR head did not move after validation.

For issue numbers above `publication.supervised_through_issue`, these checks are the auto-merge gate. Any failure leaves the PR unmerged and requires an error report.

## Legacy binary-handoff recovery
The Casebook Finalizer, raw-blob adapter, base64 chunks and Handoff Rescue remain supported only for an already-existing historical handoff. They are not accepted as the normal path for a new issue.

Legacy recovery remains fail-closed: exact byte size/hash, signatures, page mechanics, references, and explicit prior visual inspection are required. A partial handoff without a valid readiness manifest remains inert.

## Legacy backfill exception
ISSUE-001 through ISSUE-004 pre-date the repository publisher. Missing historical binaries or source assets must be declared explicitly using `legacy_backfill: true` and archival-status metadata. This exception cannot be used by ISSUE-005 or later.

## Link health — warning only
A transiently unavailable external URL does not invalidate otherwise verified source metadata.

## Failure behaviour
Never register a partial package as published and never merge it to `main`. Preserve durable source or `rendered` state, report the first failed stage, and leave canonical `main` unchanged.
