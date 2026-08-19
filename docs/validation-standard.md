# Validation Standard

A publication is blocked if any blocking check fails.

## Knowledge checks - blocking
- IDs are unique and sequential; published IDs are never reused.
- Every referenced source, case or toolbox entity exists.
- The five required issue slots are present exactly once for all new normal issues from ISSUE-005 onward.
- Existing toolbox entities are reused instead of duplicated.
- Published case and issue paths remain immutable.

## Research checks - blocking
- Deep Dive has at least one Tier A primary source.
- Every case has an authoritative technical source.
- Important numerical claims trace to a cited source.
- Proprietary brands are named only when explicitly documented.
- Facts/findings/interpretations are distinguished where needed.
- Evidence gaps are recorded.

## Figure checks - blocking
For ISSUE-005 onward:
- Deep Dive has at least two meaningful SVG technical figures and every other case at least one.
- SVG parses and has `viewBox`, title and description.
- No unsupported dimensions or external dependencies.
- Labels are readable at publication size.
- Technical content agrees with the cited source material.

## PDF checks - blocking
For ISSUE-005 onward:
- The scheduled publisher generates the PDF locally and visually inspects the exact binary before creating the handoff readiness manifest.
- The Casebook Finalizer reconstructs that binary from text-safe base64 chunks and verifies the declared byte size and SHA-256 before `issue.yml` may register it.
- The validated PDF is committed inside the issue package; `issue.yml` may never point to an absent or hash-invalid file.
- Exactly 3 or 4 A4 pages. Three pages are preferred when comfortable; four pages require a recorded non-empty `page_count_override_reason` and are preferred over visual compression.
- Searchable text; embedded fonts; live source hyperlinks.
- No clipping, overlap or unreadable elements.
- Minimum body 8.5 pt, secondary 8 pt, sources/captions 7 pt.
- Normal layout should target the larger sizes and spacing in `templates/magazine-style.md`; minimum sizes are not a pagination strategy.
- No large unexplained dead space that indicates layout failure.
- Figures remain legible when viewed at normal page scale.
- Reject a three-page issue if it stays on three pages only by materially tightening body leading, source text, diagram scale, module spacing or closing-synthesis space relative to the established magazine character. Use four pages instead.
- A four-page issue must use the extra page deliberately; reject a thin overflow page with large avoidable dead zones.

### Scheduled-publisher pre-handoff checks
Before writing `.handoff/manifest.json`, render every PDF page to an image and inspect hierarchy, clipping, overlap, source legibility, diagram legibility, typography and dead-space usage. Explicitly check whether the design is visually compressed merely to preserve three pages. Record `visual_inspection.passed: true` only after those checks pass.

### Finalizer mechanical checks
The GitHub Action independently blocks finalization unless:
- decoded PDF/JPEG byte sizes and SHA-256 values exactly match the handoff manifest;
- PDF/JPEG file signatures are valid;
- PDF parser tools open the PDF;
- page count agrees with the handoff and `issue.yml`;
- every page is A4 within the configured tolerance;
- searchable-text extraction exceeds the configured minimum content threshold;
- live URI annotations are at least the number of issue slots;
- every font reported by `pdffonts` is embedded;
- Markdown, source snapshots and listed SVG assets exist.

The mechanical checks complement rather than replace visual inspection.

## Post-finalization publication checks - blocking
Before any publication PR is approved or auto-merged:
- The associated Casebook Finalizer run completed successfully for the current publication branch state.
- `issue.yml` records `status: published`, the final page count, PDF/preview filenames, byte sizes and SHA-256 hashes.
- The finalized PDF and preview exist on the branch at exactly the sizes declared by `issue.yml`.
- `catalog/issues.json` records the issue as `published`; draft catalog state may not be merged with a finalized issue.
- Any temporary/pre-finalization note that now contradicts published state has been removed or normalized.
- `.handoff/` no longer exists after successful finalization.
- The pull request is mergeable.

For issue numbers above `publication.supervised_through_issue`, these checks are the auto-merge gate. Any failure leaves the PR unmerged and requires an error report instead of consumer-mode publication.

## Binary handoff integrity - blocking
For ISSUE-005 onward:
- Direct connected-GitHub binary writes are not an accepted publication path.
- Base64 chunk files are temporary transport data under the issue's `.handoff/` directory.
- Every chunk is at most 16,000 ASCII characters.
- Symlinked handoff directories, manifests, chunk files, or `issue.yml` inputs are rejected by the finalizer.
- `manifest.json` is written last and is the only readiness signal.
- A partial handoff without `manifest.json` is not a publication failure and must remain inert.
- Handoff chunks are removed only after successful finalization.

## Legacy backfill exception
ISSUE-001 through ISSUE-004 pre-date the repository publisher. Their historical records may be less complete than the live publication contract. Any missing historical binary PDF, source snapshot or original figure asset must be declared explicitly in `issue.yml` using `legacy_backfill: true` and an archival-status field. A legacy manifest must never claim that an absent file exists.

This exception is archival only. It cannot be used by ISSUE-005 or later.

## Link health - warning only
A transiently unavailable external URL does not invalidate otherwise verified source metadata.

## Failure behaviour
Do not register a partial package as published and never merge it to `main`. A source package or diagnostic handoff may remain on its publication branch for repair, but `issue.yml` must not claim absent/invalid generated artifacts. Report the failed stage and preserve `main` unchanged.
