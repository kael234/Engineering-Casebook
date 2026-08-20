# Deterministic Engineering Casebook Publisher Design

Date: 2026-08-20
Status: Proposed

## 1. Purpose

Replace the fragile ChatGPT-to-GitHub binary handoff with a deterministic repository-owned rendering pipeline.

The intended steady state is:

1. The Thursday 00:15 ChatGPT research task prepares and commits the verified editorial source package.
2. GitHub Actions renders and mechanically validates the PDF and preview using trusted code from `main`.
3. The Thursday 05:00 ChatGPT publisher task performs visual review, publication approval, merge policy, and user delivery.
4. A failed stage leaves durable, inspectable state and is resumed on the next run.

The system must recover ISSUE-007 and support ISSUE-008 onward without base64 chunk transport, temporary PDF-generation code inside scheduled tasks, or manual GitHub maintenance.

## 2. Problem Statement

The current publication design assigns one scheduled ChatGPT run all of the following responsibilities:

- reconstructing a page-layout implementation from prose guidance;
- generating a fixed-layout A4 magazine;
- rendering and visually inspecting pages;
- transporting PDF/JPEG bytes through a text-oriented connector;
- triggering and monitoring GitHub Actions;
- finalizing metadata;
- managing pull requests and merge policy;
- delivering the result to the user.

This design failed for ISSUE-007 before the first durable binary checkpoint.

The repository has no deterministic magazine renderer. Its current executable scripts only validate and reconstruct binaries that have already been generated elsewhere. Documentation also contains conflicting instructions: the publisher skill prefers raw Git blobs, while the validation standard still describes base64 chunk transport as the normal path.

The connected GitHub blob action accepts string content encoded as UTF-8 or base64; it does not accept an arbitrary local binary file path. This makes the documented “raw bytes with no encoding step” connector procedure impossible as written.

The result is a pipeline with too many transient stages and no durable record of where a scheduled publisher stopped.

## 3. Goals

The implementation must:

- render Casebook PDFs deterministically from committed `issue.md`, `issue.yml`, SVG assets, and snapshots;
- run inside GitHub Actions using trusted renderer code from `main`;
- commit PDF and preview directly through a normal Git checkout;
- eliminate binary handoff data for all new publication runs;
- preserve a durable intermediate state after successful rendering but before visual approval;
- reuse the existing mechanical PDF checks where practical;
- retain human or ChatGPT visual inspection before an issue becomes `published`;
- leave supervised ISSUE-007 open for human approval;
- allow ISSUE-008 and later issues to be merged automatically after visual review and all blocking checks;
- make every failure observable through workflow logs, PR state, and repository metadata;
- keep the recurring workflow understandable enough for a small personal project.

## 4. Non-Goals

This change will not:

- replace the research and editorial task with a fully automated LLM workflow;
- generate or revise engineering facts inside GitHub Actions;
- infer missing source material;
- silently rewrite committed editorial content to make a page fit;
- delete the existing Finalizer and rescue tools immediately;
- promise that mechanical checks alone can replace visual review.

The old handoff tools remain available for historical recovery, but they are no longer the normal publication path.

## 5. Approaches Considered

### 5.1 Keep the current ChatGPT renderer and repair blob transport

This would preserve the present division of responsibility and clarify that GitHub’s `create_blob` request may base64-encode bytes as API transport while Git stores the decoded raw blob.

Rejected as the primary design because transport is not the only failure. Every scheduled run would still have to invent and debug a magazine renderer in a temporary environment. A better byte pipe does not fix the absence of a deterministic build system.

### 5.2 Move the full publication process into GitHub Actions

GitHub Actions would render, validate, mark published, create/update the PR, and merge consumer-mode issues.

Rejected because GitHub Actions cannot perform the required editorial visual judgement or deliver the finished issue to the ChatGPT task conversation. Treating mechanical heuristics as visual approval would weaken the existing quality standard.

### 5.3 Hybrid deterministic render plus ChatGPT visual approval

Recommended.

GitHub Actions owns deterministic rendering, preview generation, mechanical validation, and binary commits. The scheduled ChatGPT publisher owns visual inspection, final publication status, merge policy, and delivery.

This removes the unreliable parts from ChatGPT while preserving the judgement-dependent parts.

## 6. Publication States

The issue lifecycle becomes explicit:

- `draft`: editorial source package is incomplete or no successful render exists.
- `rendered`: PDF and preview exist, hashes/sizes are recorded, and mechanical validation passed; visual publication review remains outstanding.
- `published`: visual review passed, catalog state agrees, and the issue is ready for supervised review or consumer-mode merge.

A `rendered` issue is durable progress, not a failed publication.

The 05:00 publisher resumes the highest existing issue in `rendered` state before considering a new identifier.

## 7. Repository Components

### 7.1 `scripts/render_casebook.py`

Responsibilities:

- read and validate `issue.yml`;
- split `issue.md` into explicit `PAGE N` sections;
- require the number and order of page sections to match `page_count`;
- convert the committed Markdown into controlled HTML;
- resolve issue-relative SVG assets safely;
- convert bare source URLs into live hyperlinks;
- render an A4 PDF with WeasyPrint;
- fail if the produced page count differs from `issue.yml`;
- emit deterministic diagnostic information such as source word count and generated page count.

It does not update repository metadata.

### 7.2 `scripts/publish_casebook_render.py`

Responsibilities:

- validate publication branch and issue identity;
- verify the complete editorial package and listed assets;
- call `render_casebook.py` into a temporary directory;
- generate `preview.jpg` from page 1 using Poppler;
- call the existing `casebook_finalizer.validate_pdf` mechanical checks;
- verify JPEG signature and dimensions;
- compute exact byte sizes and SHA-256 hashes;
- atomically move the PDF and preview into the issue directory;
- update `issue.yml` to `status: rendered` with PDF/preview metadata and render metadata;
- remove obsolete `.handoff/` state if present;
- leave `catalog/issues.json` as draft until visual approval;
- return a stable issue ID and summary for workflow logs.

### 7.3 `templates/magazine.html`

A minimal trusted HTML shell containing:

- document metadata;
- issue title and issue number;
- one explicit page wrapper per committed `PAGE N` section;
- page-specific classes for deep dive, problems from practice, engineering wins, and synthesis;
- a footer with issue/page numbering.

### 7.4 `templates/magazine.css`

A deterministic A4 magazine stylesheet implementing the current design standard:

- A4 portrait pages;
- warm-white background;
- dark navy/charcoal text;
- one warm accent colour;
- DejaVu or Liberation serif/sans fonts installed by the workflow and embedded by WeasyPrint;
- 9-9.5 pt body target;
- 8.5-9 pt secondary target;
- 7.5-8 pt source/caption target;
- explicit page breaks at page markers;
- two-column magazine flow where appropriate;
- controlled heading hierarchy;
- styled `YOU ARE THE ENGINEER`, `Engineer’s Notebook`, evidence-boundary, source, Thread, Takeaway, and Archive Recall modules;
- SVG figures sized for teaching rather than decoration;
- `break-inside: avoid` rules for figures, headings, and short modules.

The stylesheet must not hide overflow. Content that creates an extra page fails the render rather than being clipped.

### 7.5 `requirements-publisher.txt`

Pinned Python dependencies for the renderer and tests. Expected categories:

- WeasyPrint;
- Python-Markdown;
- Jinja2;
- PyYAML;
- Pillow.

Exact versions will be pinned during implementation after compatibility testing on the GitHub runner image.

### 7.6 `.github/workflows/casebook-publisher.yml`

Trusted workflow code lives on `main`.

Triggers:

- `schedule` at Thursday 00:00 UTC, equivalent to Thursday 04:00 in Seychelles;
- `workflow_dispatch` with an optional `target_branch`;
- same-repository publication PR events where useful;
- publication-branch source pushes as an opportunistic path, with scheduled execution as the reliable fallback.

The scheduled render intentionally occurs before the 05:00 ChatGPT publisher task.

Permissions:

- `contents: write`;
- `pull-requests: write` only if PR creation/update is performed in the workflow.

Security boundary:

1. Check out trusted tooling from `main` with credentials disabled.
2. Check out the selected publication branch separately as data with write credentials.
3. Execute only scripts from the trusted checkout.
4. Validate that the target branch matches `publish/issue-###-YYYY-MM-DD`.
5. Commit only the selected issue directory and, where explicitly required, controlled publication metadata paths.

Branch selection on scheduled runs:

1. list `publish/issue-*` branches;
2. inspect the highest issue number;
3. select the highest issue that is not already `published`;
4. require a complete source package;
5. no-op cleanly if no renderable issue exists.

Workflow steps:

1. select and validate target branch;
2. check out trusted tooling and publication data;
3. install pinned Python dependencies, Poppler, and deterministic fonts;
4. render PDF and preview;
5. run mechanical validation;
6. render all pages to PNG diagnostics;
7. upload a contact-sheet/PNG workflow artifact for diagnosis;
8. commit PDF, preview, and `status: rendered` metadata to the publication branch;
9. create or update a draft PR to `main` if one does not already exist;
10. write a clear workflow summary containing artifact paths, hashes, page count, and next required state.

The workflow does not mark the issue `published` and does not merge it.

## 8. Visual Approval and 05:00 Publisher Task

The 05:00 ChatGPT publisher becomes a review and delivery task rather than a PDF-generation task.

It must:

1. inspect the highest unfinished publication branch;
2. if the branch is `draft`, report that rendering has not completed and inspect the associated workflow failure;
3. if the branch is `rendered`, fetch the exact PDF from the branch;
4. render every page to images and visually inspect hierarchy, clipping, overlap, apparent typography, figure legibility, source legibility, spacing, and dead-space use;
5. verify PDF/preview hashes and sizes against `issue.yml`;
6. change `issue.yml` to `status: published` only after visual review passes;
7. update `catalog/issues.json` to `published` and normalize stale notes;
8. verify the PR remains mergeable;
9. for supervised issues, leave the PR open and deliver the PDF;
10. for consumer-mode issues, mark the PR ready, merge it, verify `main`, and deliver the PDF.

If visual review fails, the task leaves the branch in `rendered` state and reports the exact layout defect. It does not delete the generated artifact or pretend the issue is published.

## 9. Rendering Model

The committed `PAGE N` markers are authoritative pagination boundaries.

The renderer does not rebalance editorial content across pages. This keeps the editorial package durable and makes rendering deterministic.

Within each page, HTML/CSS may flow content into columns and avoid splitting protected modules. If a page overflows and produces an extra PDF page, rendering fails with a message identifying the declared and actual page counts.

The research/editorial workflow remains responsible for assigning content to three or four pages. The renderer is responsible for consistently implementing that decision.

## 10. Mechanical and Diagnostic Validation

The implementation reuses the existing Finalizer checks for:

- page count;
- A4 dimensions;
- searchable text thresholds;
- live URI annotations;
- embedded fonts;
- required Markdown, snapshots, and SVG assets.

Additional renderer checks:

- each expected `PAGE N` marker appears exactly once;
- page numbering is contiguous;
- image references stay inside the issue directory;
- every referenced SVG parses before rendering;
- the PDF contains no extra page caused by overflow;
- preview JPEG has valid markers and practical dimensions;
- render output is written to a temporary directory before atomic replacement.

The workflow saves rendered PNG pages as Actions artifacts so a failed or questionable render has inspectable evidence.

## 11. Error Handling

The workflow fails closed.

- Missing source package: no binary or metadata changes.
- Markdown/page-marker mismatch: no binary or metadata changes.
- WeasyPrint failure: no binary or metadata changes.
- Page overflow: no binary or metadata changes.
- Mechanical validation failure: no binary or metadata changes.
- Git branch moved unexpectedly: no push; re-read required.
- Commit contains a path outside the allowed render scope: refuse to push.
- Existing valid rendered artifact with matching hashes: no-op idempotently.

Every failure must identify the first failed stage in the workflow summary.

## 12. Testing Strategy

### Unit tests

Add tests for:

- parsing three-page and four-page issue Markdown;
- rejecting duplicate, missing, or out-of-order page markers;
- safe issue-relative asset resolution;
- URL linkification;
- `issue.yml` transition from `draft` to `rendered`;
- idempotent re-render behaviour;
- catalog remaining draft until visual approval;
- rendered metadata hash/size correctness;
- workflow branch-name validation.

### Integration tests

Use ISSUE-006 on `main` as a full repository fixture:

- render from its committed source package;
- require four A4 pages;
- require searchable text above the existing threshold;
- require at least five live source links;
- require embedded fonts;
- require all listed SVGs to load;
- require preview generation.

The test does not require byte-for-byte equality with the historical ISSUE-006 PDF. It validates the deterministic renderer contract.

### ISSUE-007 acceptance test

After infrastructure reaches `main`, run the workflow against `publish/issue-007-2026-08-19` and require:

- four A4 pages;
- a valid PDF and preview committed to the branch;
- `issue.yml` in `rendered` state with exact hashes and sizes;
- no `.handoff/` directory;
- PR #16 still draft and mergeable;
- successful visual review before `published` status.

## 13. Documentation Changes

Update:

- `skills/casebook-publisher/SKILL.md` to remove PDF generation and binary handoff from ChatGPT responsibilities;
- `docs/validation-standard.md` to make repository rendering the normal path and handoff validation legacy-only;
- `docs/casebook-finalizer.md` to label Finalizer/rescue as legacy recovery infrastructure;
- `templates/magazine-style.md` to reference the executable HTML/CSS template;
- `AGENTS.md` to define trusted render workflow write scope;
- `casebook.yml` to record the real Thursday schedule.

The documents must describe one normal publication path, not several competing paths.

## 14. Automation Changes

After implementation:

- keep `Casebook Research` at Thursday 00:15 Seychelles time;
- keep `Casebook Publisher` at Thursday 05:00 Seychelles time;
- rewrite the publisher task prompt so it reviews and publishes an existing `rendered` artifact instead of generating or transporting binaries;
- enable notifications for the Casebook tasks so success or failure is visible without opening the task manually.

## 15. ISSUE-007 Migration

1. Merge the deterministic publisher infrastructure into `main`.
2. Trigger the renderer for `publish/issue-007-2026-08-19` through PR synchronization/reopen, schedule, or manual dispatch.
3. Confirm PDF, preview, and `rendered` metadata are committed.
4. Visually inspect the exact branch PDF.
5. Mark ISSUE-007 `published`, update its catalog entry, and update PR #16.
6. Leave PR #16 open because ISSUE-007 is supervised.
7. Deliver the PDF to the user.
8. After user approval and merge, the next research run may allocate ISSUE-008 / CASE-033 onward.

## 16. Definition of Done

The architectural repair is complete when:

- deterministic renderer code and templates are on `main`;
- the render workflow passes its unit and integration tests;
- normal documentation no longer instructs ChatGPT to transport binary handoffs;
- ISSUE-007 has a mechanically valid four-page PDF and preview committed by GitHub Actions;
- ISSUE-007 has passed visual review and is presented for supervised approval;
- the 05:00 task can complete without generating a PDF or moving binary data through the GitHub connector;
- a failed render leaves actionable logs and durable source state;
- ISSUE-008 can follow the same path without new publication infrastructure.
