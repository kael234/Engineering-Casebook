# Casebook Finalizer Design

## Purpose

Add a small GitHub Actions finalization subsystem that solves the proven binary-transfer failure between the scheduled ChatGPT publisher and GitHub without moving research, editorial work, figure creation, PDF generation, or visual inspection out of the scheduled publisher.

The user-facing goal is simple: reliably produce complete Engineering Casebook PDF issues from the existing scheduled workflow, preserve the repository as the canonical knowledge layer, and keep Issues 005–007 supervised through pull requests.

## Problem Statement

The ISSUE-005 diagnostic proved that the scheduled publisher can successfully read the repository, research and verify cases, create canonical records and SVG figures, compose the magazine, generate a valid three-page A4 PDF locally, verify searchable text and source links, render all pages for visual inspection, and generate a preview image.

The failure occurs only when arbitrary binary PDF/JPEG bytes are persisted through the connected GitHub write path. Text and SVG writes succeed; attempted binary blob transfer truncates the payload.

The finalizer therefore treats GitHub text writes as the transport and reconstructs the original binary artifacts inside GitHub Actions.

## Scope

### In scope

- A transport-safe text handoff format for generated PDF and preview binaries.
- A GitHub Actions workflow that finalizes publication branches.
- Exact byte-size and SHA-256 integrity verification before reconstructed binaries are accepted.
- Mechanical PDF validation that complements the scheduled publisher's visual inspection.
- Safe update of `issue.yml` only after valid binary files exist.
- Removal of temporary handoff chunks after successful finalization.
- Commit of finalized binary artifacts back to the same publication branch.
- Manual dispatch support for rescuing the existing ISSUE-005 branch.
- Automatic push-triggered finalization for future `publish/issue-*` branches.
- Draft PR creation by the connected scheduled publisher, not by the write-capable GitHub Actions token.

### Out of scope

- Moving web research into GitHub Actions.
- Calling an LLM from GitHub Actions.
- Rebuilding or redesigning the editorial workflow.
- Replacing the scheduled publisher's local PDF renderer.
- Automatic merging of any publication PR.
- Running workflows from fork pull requests with write permissions.
- Adding repository secrets or personal access tokens.
- Creating a general-purpose binary transport mechanism for unrelated repository files.

## Architecture

The publishing system is split at the binary persistence boundary.

### Scheduled ChatGPT publisher owns

1. Repository bootstrap and ID allocation.
2. Case discovery and source verification.
3. Canonical case/source/toolbox records.
4. SVG technical figures.
5. Issue Markdown, snapshots, and draft `issue.yml`.
6. Local PDF generation.
7. Local PDF rendering and visual inspection.
8. Creation of a transport-safe handoff containing base64 text chunks and integrity metadata.
9. Commit of all text/source publication material to `publish/issue-###-YYYY-MM-DD`.
10. Creation of a supervised draft PR through the connected GitHub app after the handoff readiness manifest is committed.

The draft PR may temporarily contain only the source package and handoff. It is not eligible for merge until the Casebook Finalizer check succeeds and the binary artifacts have been committed to the branch.

### GitHub Actions finalizer owns

1. Handoff schema and path validation.
2. Base64 reconstruction of PDF and preview artifacts.
3. Exact byte-size and SHA-256 verification.
4. Mechanical PDF checks.
5. Atomic placement of reconstructed binaries in the issue directory.
6. Final `issue.yml` update after valid binaries exist.
7. Cleanup of handoff files.
8. Commit and push to the same publication branch.

The finalizer never opens, approves, or merges pull requests.

## Handoff Contract

Each issue uses a temporary handoff directory inside the normal publication write boundary:

`issues/<ISSUE-DIRECTORY>/.handoff/`

This keeps scheduled publisher writes within `issues/` and does not grant the publisher new infrastructure write authority.

### Chunk files

Each binary artifact is encoded using standard RFC 4648 base64 with no compression and split into text files containing at most 16,000 ASCII characters each.

Example paths:

```text
issues/ISSUE-005-nothing-is-secondary/.handoff/pdf.part001.b64
issues/ISSUE-005-nothing-is-secondary/.handoff/pdf.part002.b64
issues/ISSUE-005-nothing-is-secondary/.handoff/preview.part001.b64
```

Chunk filenames are ordered explicitly in the manifest. The finalizer never discovers, evaluates, or sorts arbitrary filenames supplied by directory contents.

### Manifest-last rule

The scheduled publisher MUST commit every chunk before writing:

`issues/<ISSUE-DIRECTORY>/.handoff/manifest.json`

`manifest.json` is the readiness signal. Automatic finalization is triggered only by a push that includes this manifest path. Partial chunk uploads without a manifest are inert.

### Handoff manifest schema

The manifest is JSON with exactly these top-level keys:

- `schema_version`: integer, exactly `1`.
- `issue_id`: string matching `^ISSUE-[0-9]{3}$`.
- `issue_dir`: repository-relative issue directory.
- `visual_inspection`: object with exactly `passed` and `page_count`.
- `artifacts`: array containing exactly one PDF artifact and exactly one JPEG preview artifact.

Each artifact contains exactly:

- `role`: `pdf` or `preview`.
- `output`: filename only, never a path.
- `media_type`: `application/pdf` for PDF or `image/jpeg` for preview.
- `byte_size`: positive integer not exceeding 20 MiB.
- `sha256`: exactly 64 lowercase hexadecimal characters.
- `chunks`: ordered non-empty array of unique chunk filenames.

Unknown top-level or artifact keys are rejected so the manifest cannot quietly acquire executable or path-like behaviour later.

## Handoff Security and Validation Rules

The finalizer rejects the handoff before decoding if any of the following is true:

- `schema_version` is not exactly `1`.
- `issue_id` does not match `^ISSUE-[0-9]{3}$`.
- `issue_dir` is absolute, contains `..`, or does not match `^issues/ISSUE-[0-9]{3}-[a-z0-9-]+$`.
- The issue-directory numeric ID does not equal `issue_id`.
- The target branch does not match `^publish/issue-[0-9]{3}-[0-9]{4}-[0-9]{2}-[0-9]{2}$`.
- The branch issue number does not equal `issue_id`.
- A chunk filename is absolute, contains `/`, contains `\\`, contains `..`, or does not match `^(pdf|preview)\.part[0-9]{3}\.b64$`.
- A chunk file contains more than 16,000 ASCII characters.
- The handoff directory, readiness manifest, a chunk file, or `issue.yml` is a symlink.
- An output contains `/`, `\\`, `..`, or an unexpected extension.
- The PDF role does not use `.pdf` and `application/pdf`.
- The preview role does not use `.jpg` or `.jpeg` and `image/jpeg`.
- A declared byte size is non-positive or exceeds 20 MiB.
- A SHA-256 value is not exactly 64 lowercase hexadecimal characters.
- `visual_inspection.passed` is not exactly `true`.
- `visual_inspection.page_count` is not `3` or `4`.
- Chunks or outputs are duplicated.
- Required keys are missing or unknown keys are present.

Only ordinary files inside the manifest's own `.handoff` directory may be read as chunks. Only the declared PDF and preview filenames inside the same issue directory may be written as reconstructed binaries.

Manifest values are passed as structured arguments to Python and Git commands; they are never evaluated as shell code.

## Binary Reconstruction

For each artifact, the finalizer:

1. Reads chunk files in manifest order as ASCII text.
2. Rejects characters outside the RFC 4648 base64 alphabet plus ASCII whitespace.
3. Rejects any chunk containing more than 16,000 characters.
4. Concatenates the chunk text.
5. Decodes with strict base64 validation after whitespace removal.
6. Verifies exact decoded byte count.
7. Verifies SHA-256.
8. Verifies file magic:
   - PDF begins with `%PDF-`.
   - JPEG begins with `FF D8 FF` and ends with `FF D9`.
9. Writes to a temporary file in the issue directory.
10. Runs validation against the temporary artifact.
11. Atomically replaces the target output only after validation succeeds.

This permits ISSUE-005 to replace the known truncated diagnostic PDF/JPEG blobs safely. Existing valid binaries with the expected SHA-256 are accepted idempotently rather than rewritten.

## PDF Mechanical Validation

The GitHub runner complements, but does not replace, the scheduled publisher's visual inspection.

The workflow installs `poppler-utils` from the Ubuntu package repository and uses `pdfinfo`, `pdftotext`, and `pdffonts`.

Blocking mechanical checks are:

- The PDF passes the handoff size, SHA-256, and `%PDF-` checks.
- Poppler tools open the PDF successfully.
- Page count equals `visual_inspection.page_count` and the issue manifest's `page_count`.
- Normal issues have exactly 3 pages.
- A 4-page issue is accepted only when `issue.yml` contains `page_count: 4` and a non-empty top-level `page_count_override_reason`.
- Every page width is within ±2.0 points of 595.28 points and every page height is within ±2.0 points of 841.89 points.
- `pdftotext` extraction contains at least 1,800 whitespace-delimited words and at least 10,000 non-whitespace characters.
- URI extraction reports at least as many `http://` or `https://` link annotations as there are issue slots; ISSUE-005+ normal issues therefore require at least 5 URI annotations.
- Every font row reported by `pdffonts` has `emb` equal to `yes`.
- Every SVG path listed by `issue.yml` exists.
- The Markdown path and every snapshot path listed by `issue.yml` exist.
- The handoff manifest records successful local visual inspection.

Visual criteria such as clipping, overlap, label legibility, hierarchy, and dead-space usage remain the scheduled publisher's responsibility because they require page-image inspection.

## `issue.yml` Finalization

`issue.yml` must not point to PDF or preview output files until those files have been reconstructed and validated.

After successful reconstruction, the finalizer changes only controlled top-level publication metadata and generated-artifact blocks. It preserves all unrelated issue metadata, slot mappings, snapshots, and assets.

The finalizer:

- sets `status: published`;
- sets `original_format: magazine_v3`;
- if top-level `diagnostic` exists, sets it to `false`;
- if the ISSUE-005 diagnostic failure `note` exists, replaces it with `note: Binary artifacts finalized and mechanically validated by GitHub Actions.`;
- adds or replaces a `pdf` block containing `path`, `sha256`, and `byte_size`;
- adds or replaces a `preview` block containing `path`, `sha256`, and `byte_size`.

The implementation uses a small dependency-free top-level YAML scalar/block editor rather than adding a general YAML package solely for this controlled mutation. Tests must prove unrelated content is preserved byte-for-byte except for the controlled keys and blocks.

## Workflow Trust Boundary

Finalizer code is always executed from the repository's canonical `main` branch, never from the publication branch being finalized.

The workflow uses two separate checkouts:

1. `main` is checked out read-only into a tooling directory and supplies `scripts/casebook_finalizer.py`.
2. The target publication branch is checked out into a separate worktree directory and is treated as publication data.

The workflow invokes the main-branch finalizer script with the publication worktree as an explicit path argument. It never imports Python modules, executes shell scripts, or executes binaries from the publication branch.

This rule applies both to manual ISSUE-005 rescue and automatic future runs.

## Workflow Triggers

The workflow is stored at:

`.github/workflows/casebook-finalizer.yml`

It supports two entry paths.

### Automatic future path

A `push` to branches matching `publish/issue-*` triggers finalization only when the pushed changes include a path matching:

`issues/**/.handoff/manifest.json`

Future publication branches created from `main` after this subsystem is merged inherit the workflow.

### ISSUE-005 rescue path

`workflow_dispatch` accepts one required `target_branch` input.

The workflow itself runs from `main`, validates the target-branch pattern, checks out `main` as tooling and the requested publication branch as data, locates exactly one ready handoff manifest in the publication worktree, and finalizes that issue.

This avoids rebasing ISSUE-005 merely to make infrastructure files exist on its older branch.

## Commit and Pull Request Behavior

After all checks pass, the workflow:

1. Deletes the issue's `.handoff/` directory.
2. Stages only the finalized issue directory.
3. Verifies that no path outside that issue directory is staged.
4. Commits with message `build: finalize ISSUE-###`.
5. Pushes to the same publication branch.
6. Exits successfully.

The scheduled publisher uses the connected GitHub app to create the supervised draft PR after committing `manifest.json`. The finalizer requires no pull-request write permission. The draft PR automatically receives the finalizer's later commit because it points to the same branch.

For the one-off ISSUE-005 rescue, the draft PR may be opened manually through the connected GitHub app after the finalizer infrastructure is installed. No workflow opens or merges it.

## GitHub Actions Security Model

The repository is public, but the finalizer is intentionally designed without secrets.

### Required workflow permission

```yaml
permissions:
  contents: write
```

No pull-request, issue, package, deployment, ID-token, or other write permission is requested.

### Explicit security constraints

- No repository or environment secrets.
- No personal access token.
- No `pull_request` or `pull_request_target` execution path for the write-capable finalizer.
- No execution of code from fork pull requests with a write-capable token.
- No dynamic downloading or execution of scripts specified by issue content.
- Publication-branch content is data only; executable finalizer code always comes from `main`.
- No shell evaluation of manifest values.
- Manifest paths are validated before filesystem use.
- Handoff and manifest inputs must be ordinary files/directories, not symlinks.
- Publication branches must match the strict branch pattern.
- `workflow_dispatch` is limited by normal GitHub repository permissions.
- Pushes inside forks do not trigger write-capable runs in the upstream repository.
- The workflow uses only the ephemeral built-in `GITHUB_TOKEN` scoped to this repository and job.
- Third-party Actions are avoided. GitHub-owned checkout tooling may be used and is pinned to a reviewed immutable commit SHA during implementation.

## Repository Files

The subsystem adds focused files with separate responsibilities:

- `.github/workflows/casebook-finalizer.yml` — events, permissions, separate tooling/data checkouts, runner setup, finalizer invocation, commit, and push.
- `scripts/casebook_finalizer.py` — handoff validation, reconstruction, integrity checks, PDF mechanical validation, controlled `issue.yml` update, and cleanup.
- `tests/test_casebook_finalizer.py` — dependency-free unit tests for schema/path validation, base64 reconstruction, hash/size checks, YAML mutation, transport-boundary safety, and failure behavior.
- `docs/casebook-finalizer.md` — operator documentation for the scheduled publisher handoff and manual ISSUE-005 rescue.
- `skills/casebook-publisher/SKILL.md` — publisher contract updated so binary artifacts use the text handoff rather than direct GitHub binary writes.
- `docs/validation-standard.md` — validation wording updated to recognize the finalizer boundary while preserving all existing blocking quality requirements.

## Failure Behavior

The finalizer is fail-closed.

If any validation step fails:

- no invalid decoded artifact replaces an existing path;
- `issue.yml` is not finalized;
- `.handoff/` remains intact for diagnosis;
- the workflow exits non-zero with a stage-specific message;
- the publication branch remains available for repair;
- `main` is never modified directly.

If binary reconstruction succeeds but a later mechanical PDF check fails, temporary decoded files are removed and the handoff remains.

If commit or push fails after local finalization, the job exits non-zero and GitHub retains the logs. A later manual dispatch is safe because finalization is idempotent.

## Idempotency

Repeated runs are safe.

- If an output already exists with the exact expected hash, it is accepted rather than regenerated.
- If an output exists with a different hash, it is replaced only after the handoff artifact validates completely.
- If no `.handoff/manifest.json` exists, the finalizer exits without changing publication data.
- If finalization already removed `.handoff/`, a manual rerun exits cleanly without changing files.

## ISSUE-005 Rollout

The existing `publish/issue-005-2026-08-18` branch is preserved. No research or editorial stages are repeated merely to test transport.

Rollout sequence:

1. Implement and review the finalizer on `infra/casebook-finalizer`.
2. Merge the finalizer infrastructure change to `main`.
3. Run a focused scheduled task on the existing ISSUE-005 branch that recreates the already-generated local PDF/preview, performs the same local visual inspection, and writes only the base64 chunks plus `manifest.json`.
4. Manually dispatch `Casebook Finalizer` from `main` with `target_branch=publish/issue-005-2026-08-18`.
5. Verify reconstructed PDF and preview hashes, workflow logs, final `issue.yml`, and the draft PR.
6. Review ISSUE-005 manually before merging, as already required.
7. Remove diagnostic-only files from the publication branch before merge, including `.publisher-diagnostic.md`, `.scheduled-github-smoke-test.txt`, and known truncated diagnostic binary blobs when they are replaced by valid finalizer outputs.
8. After ISSUE-005 proves the pipeline, simplify the recurring scheduled publisher prompt so repository rules and `skills/casebook-publisher/SKILL.md` remain the canonical workflow definition.

## Acceptance Criteria

The subsystem is accepted when all of the following are true:

1. The repository contains no new secrets or long-lived credentials.
2. A synthetic unit test reconstructs known bytes from multiple base64 chunks and rejects one-byte corruption.
3. Traversal attempts, symlinked transport inputs, invalid branch/issue paths, and chunks over 16,000 characters are rejected.
4. `issue.yml` is never updated to point to absent or hash-invalid binaries.
5. The ISSUE-005 handoff reconstructs the PDF and preview to the exact locally declared SHA-256 values.
6. ISSUE-005 passes the mechanical PDF checks in GitHub Actions.
7. The finalizer commits the valid binary files to `publish/issue-005-2026-08-18`.
8. The handoff directory is removed after success.
9. A single supervised draft PR exists for ISSUE-005.
10. No workflow merges ISSUE-005, ISSUE-006, or ISSUE-007 automatically.
11. A failed finalizer run leaves `main` unchanged and exposes a useful GitHub Actions failure log.

## Future Improvements

These are intentionally deferred until the transport/finalization path is proven:

- Reproducible PDF rebuilding entirely inside GitHub Actions.
- Automatic rendered-page visual regression checks.
- Release assets or GitHub Pages archive.
- Auto-merge policy for post-supervision issues.
- Broader repository CI for historical issue validation.
