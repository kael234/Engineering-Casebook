# Engineering Casebook Publisher

Use this skill for every scheduled or manual Casebook research, review, or delivery run.

## 1. Read before acting
Read current `main` `AGENTS.md`, `casebook.yml`, the editorial/source/diagram/validation standards, `templates/magazine-style.md`, catalogs, recent issues and relevant toolbox records.

The repository is durable state. Chat memory is not authoritative.

## 2. Resolve the active issue from integrated state
Inspect merged `main`, open publication PRs, active `publish/issue-*` branches and catalogs. Take the highest issue/case/source/toolbox identifiers present anywhere in legitimate publication state.

If the highest issue is unfinished, resume it. Do not allocate beyond it. The issue states are:

1. **Draft editorial package.** Continue only the missing research/editorial work. Do not generate a PDF.
2. **Draft, editorially complete, awaiting render.** Verify the source package and inspect the `Casebook Deterministic Publisher` workflow. Do not generate or transport a binary from ChatGPT.
3. **Rendered.** PDF/preview exist with exact hashes and mechanical validation; perform visual publication review.
4. **Published.** Apply remaining supervision/merge/delivery work, or move to the next identifier only when predecessor ordering permits.

Never duplicate identifiers or silently rewrite committed, verified editorial content.

## 3. Research and editorial handoff
Research roughly 10-15 real candidates and select exactly five normal slots: Deep Dive; Site Problem; Detail/Product/Robustness; Structural/Civil Engineering Win; Geotechnical/Site Engineering Win. Avoid duplicates and excessive disciplinary repetition; at least one case should transfer readily to ordinary building/site work.

Open authoritative primary technical sources before writing. Verify dates, geometry, numerical claims, mechanism, product identity and stated reasons for intervention. Record evidence gaps and distinguish documented fact, investigator/author finding and engineering interpretation. Never invent missing dimensions, loads, reinforcement, soil parameters, brands, breaches or motives.

Build canonical case/source/toolbox records, catalog/relations updates, SVG figures (Deep Dive at least two; every other case at least one), `issue.md`, frozen snapshots and draft `issue.yml` on the publication branch.

Compose three or four declared pages using explicit `## PAGE N - ...` markers. Readability outranks three-page count. Four pages require a specific `page_count_override_reason`.

The research/editorial run ends after committing and verifying the source package. It does not generate a PDF, preview, `.handoff/`, Finalizer run, publication approval or merge.

## 4. Deterministic rendering boundary
The trusted GitHub Actions workflow `Casebook Deterministic Publisher` owns normal PDF generation.

It:
- executes renderer code and HTML/CSS from `main`;
- checks out the selected publication branch separately as data;
- renders the committed page sections and SVGs;
- generates the preview;
- runs mechanical checks;
- commits only the issue directory;
- records `status: rendered`, artifact hashes/sizes, mechanical pass and `visual_review: pending`;
- uploads rendered pages as workflow diagnostics;
- creates a draft PR if needed.

ChatGPT must not create normal-path raw blobs, base64 chunks, handoff manifests, temporary renderer code, or PDF/JPEG Contents-API writes.

If an editorially complete issue is still `draft`, inspect the workflow result. Report the first failed job/step and durable branch state. Do not manufacture publication success.

Finalizer/blob/rescue instructions in `docs/casebook-finalizer.md` are legacy recovery only for an already-existing handoff.

## 5. Visual publication review for `status: rendered`
Fetch the exact branch PDF and preview whose paths, sizes and SHA-256 hashes are recorded in `issue.yml`.

Verify those hashes/sizes. Render every PDF page to images and inspect:
- page count and A4 format;
- hierarchy and apparent typography;
- clipping or overlap;
- body/source/caption readability;
- figure scale and label legibility;
- spacing and module separation;
- dead-space use;
- whether a three-page edition is visibly compressed;
- whether a four-page edition has a thin avoidable overflow page.

Compare with the established Casebook visual rhythm, preferably original-quality Issue 004 where accessible.

If visual review fails, leave `status: rendered`, report the exact page/module defect, and preserve the binary for diagnosis. Do not rewrite technical content merely to make a layout pass; return the issue to the editorial stage with a specific requested pagination/layout correction.

## 6. Promote a passing render to published
After the exact rendered binary passes visual review:

1. Re-read the branch head and fail if it moved unexpectedly.
2. Update `issue.yml` to `status: published`.
3. Set `render.visual_review: passed` while preserving renderer and mechanical metadata.
4. Normalize the note to state deterministic render, mechanical validation and visual review passed.
5. Update the matching `catalog/issues.json` record to `published`.
6. Re-read `issue.yml`, catalog and artifacts; verify exact agreement.
7. Confirm `.handoff/` is absent and the PR is mergeable.

Normal publication approval changes only controlled publication metadata. It never regenerates the binary.

## 7. Supervision and consumer mode
Read `publication.supervised_through_issue` from current `casebook.yml`.

### Supervised issue
For an issue at or below the threshold:
- leave the PR open and unmerged;
- deliver the finished branch PDF for human review;
- clearly state that publication is mechanically and visually approved but awaiting supervised merge.

### Consumer-mode issue
For an issue above the threshold, only after every source, render, visual, metadata, hash and mergeability gate passes:
- mark the draft PR ready;
- re-check branch head and mergeability;
- merge to `main`;
- verify `main` contains the exact artifacts and published metadata;
- deliver the PDF from `main`.

Any uncertainty, failed workflow, visual defect, metadata mismatch, branch movement or merge conflict fails closed.

## 8. Delivery
Begin successful delivery with `Engineering Casebook ### is ready` and include:
- prominent clickable PDF link;
- five case titles/slots;
- important toolbox additions;
- evidence gaps/cautions;
- deterministic renderer and visual-review status;
- PR/merge/supervision status.

If rendering or review is pending/failed, report that exact state instead of success. Do not ask the user to perform routine GitHub maintenance.
