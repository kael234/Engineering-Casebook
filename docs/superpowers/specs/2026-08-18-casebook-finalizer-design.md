# Casebook Finalizer Design

## Purpose

Add a small GitHub Actions finalization subsystem that solves the proven binary-transfer failure between the scheduled ChatGPT publisher and GitHub without moving research, editorial work, figure creation, PDF generation, or visual inspection out of the scheduled publisher.

The user-facing goal is simple: reliably produce complete Engineering Casebook PDF issues from the existing scheduled workflow, preserve the repository as the canonical knowledge layer, and keep Issues 005–007 supervised through pull requests.

## Problem Statement

The diagnostic run for ISSUE-005 proved that the scheduled publisher can successfully:

- read the repository and publication rules;
- research and verify cases;
- create canonical case/source/toolbox records;
- create SVG technical figures;
- compose the issue Markdown and snapshots;
- generate a valid three-page A4 PDF locally;
- confirm searchable text and live source links;
- render all pages for visual inspection; and
- generate a preview image.

The failure occurs only when arbitrary binary PDF/JPEG bytes are persisted through the connected GitHub write path. Text and SVG writes succeed, while attempted binary blob transfer truncates the payload.

The finalizer therefore treats GitHub text writes as the transport and reconstructs the original binary artifacts inside GitHub Actions.

## Scope

### In scope

- A transport-safe text handoff format for generated PDF and preview binaries.
- A GitHub Actions workflow that finalizes publication branches.
- Exact byte-size and SHA-256 integrity verification before accepting reconstructed binaries.
- Mechanical PDF validation that complements the scheduled publisher's visual inspection.
- Safe update of `issue.yml` only after valid binary files exist.
- Removal of temporary handoff chunks after successful finalization.
- Commit of finalized binary artifacts back to the publication branch.
- Creation of a supervised draft pull request to `main` when one does not already exist.
- Manual dispatch support for rescuing the existing ISSUE-005 publication branch.
- Automatic push-triggered finalization for future `publish/issue-*` branches.

### Out of scope

- Moving web research into GitHub Actions.
- Calling an LLM from GitHub Actions.
- Rebuilding or redesigning the Casebook editorial workflow.
- Replacing the scheduled publisher's local PDF renderer.
- Automatic merging of any publication PR.
- Handling pull requests from forks with write permissions.
- Adding repository secrets or personal access tokens.
- Creating a general-purpose binary transport protocol for unrelated repository files.

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
8. Creation of a transport-safe handoff containing base64 text chunks, integrity metadata, and a finalization manifest.
9. Commit of all text/source publication material to `publish/issue-###-YYYY-MM-DD`.

### GitHub Actions finalizer owns

1. Handoff schema and path validation.
2. Base64 reconstruction of PDF and preview artifacts.
3. Exact byte-size and SHA-256 verification.
4. Mechanical PDF checks.
5. Atomic placement of reconstructed binaries in the issue directory.
6. Final manifest update after valid binaries exist.
7. Cleanup of handoff files.
8. Commit and push to the same publication branch.
9. Creation of a supervised draft PR if one does not already exist.

## Handoff Contract

Each issue uses a temporary handoff directory inside the normal publication write boundary:

`issues/<ISSUE-DIRECTORY>/.handoff/`

This keeps scheduled publisher writes within `issues/` and avoids granting it new infrastructure write authority.

### Chunk files

Each binary artifact is encoded using standard RFC 4648 base64 with no compression and split into text files containing at most 16,000 ASCII characters each.

Example:

```text
issues/ISSUE-005-nothing-is-secondary/.handoff/pdf.part001.b64
issues/ISSUE-005-nothing-is-secondary/.handoff/pdf.part002.b64
issues/ISSUE-005-nothing-is-secondary/.handoff/preview.part001.b64
```

Chunk filenames are ordered explicitly in the manifest. The finalizer never discovers or sorts arbitrary files and never concatenates files not named by the manifest.

### Manifest-last rule

The scheduled publisher MUST commit all chunk files before writing:

`issues/<ISSUE-DIRECTORY>/.handoff/manifest.json`

`manifest.json` is the readiness signal. Automatic finalization is triggered only by a push that includes this manifest path. A partial chunk upload without a manifest is inert.

### Handoff manifest schema

The JSON manifest has this shape:

```json
{
  "schema_version": 1,
  "issue_id": "ISSUE-005",
  "issue_dir": "issues/ISSUE-005-nothing-is-secondary",
  "visual_inspection": {
    "passed": true,
    "page_count": 3
  },
  "artifacts": [
    {
      "role": "pdf",
      "output": "ISSUE-005-nothing-is-secondary.pdf",
      "media_type": "application/pdf",
      "byte_size": 81092,
      "sha256": "<64 lowercase hex characters>",
      "chunks": [
        "pdf.part001.b64",
        "pdf.part002.b64"
      ]
    },
    {
      "role": "preview",
      "output": "preview.jpg",
      "media_type": "image/jpeg",
      "byte_size": 29286,
      "sha256": "<64 lowercase hex characters>",
      "chunks": [
        "preview.part001.b64"
      ]
    }
  ],
  "issue_manifest_updates": {
    "status": "published",
    "original_format": "magazine_v3",
    "diagnostic": false
  }
}
```

The actual byte sizes and hashes come from the scheduled publisher's locally generated files.

## Handoff Security and Validation Rules

The finalizer rejects the handoff before decoding if any of the following is true:

- `schema_version` is not exactly `1`.
- `issue_id` is not `ISSUE-` followed by exactly three digits.
- `issue_dir` is absolute, contains `..`, or does not match `issues/ISSUE-*`.
- The target branch does not match `publish/issue-###-YYYY-MM-DD`.
- A chunk path is absolute, contains `..`, contains a slash, or does not end in `.b64`.
- An artifact output contains `/`, `\\`, `..`, or an unexpected extension.
- The PDF role does not use `.pdf` and `application/pdf`.
- The preview role does not use `.jpg`/`.jpeg` and `image/jpeg`.
- Any declared byte size is non-positive or exceeds a conservative per-artifact ceiling of 20 MiB.
- A SHA-256 value is not exactly 64 lowercase hexadecimal characters.
- Visual inspection is not explicitly recorded as passed.
- The handoff names duplicate chunks or duplicate output paths.

Only files inside the manifest's `.handoff` directory may be read as chunk inputs. Only the declared PDF and preview paths inside the same issue directory may be written as reconstructed binaries.

## Binary Reconstruction

For each artifact, the finalizer:

1. Reads chunk files in manifest order as ASCII text.
2. Rejects characters outside the base64 alphabet plus permitted whitespace.
3. Concatenates the chunk text.
4. Decodes using strict base64 validation.
5. Verifies exact decoded byte count.
6. Verifies SHA-256.
7. Verifies file magic:
   - PDF begins with `%PDF-`.
   - JPEG begins with JPEG SOI bytes and ends with JPEG EOI bytes.
8. Writes to a temporary file in the issue directory.
9. Runs validation against the temporary artifact.
10. Atomically replaces the target output only after validation succeeds.

This permits ISSUE-005 to replace the known truncated diagnostic PDF/JPEG blobs safely. Existing valid binaries with the expected SHA-256 are treated as idempotently complete rather than rewritten.

## PDF Mechanical Validation

The GitHub runner complements, but does not replace, the scheduled publisher's visual inspection.

The workflow installs `poppler-utils` and uses `pdfinfo`, `pdftotext`, and `pdffonts`.

Blocking mechanical checks are:

- The PDF passes the handoff size and SHA-256 checks.
- PDF parser tools can open it successfully.
- Page count is exactly 3 unless the issue manifest explicitly records a permitted four-page override.
- Every page reports A4 dimensions within a small point tolerance.
- `pdftotext` produces substantial non-empty text.
- At least one live URI is present for every required case slot; normal ISSUE-005+ issues therefore require at least five URI annotations.
- `pdffonts` reports every listed font as embedded.
- Every SVG path listed by `issue.yml` exists.
- Required source snapshots and Markdown paths listed by `issue.yml` exist.
- The handoff manifest records successful local visual inspection.

Visual criteria such as clipping, overlap, label legibility, hierarchy, and dead-space usage remain the scheduled publisher's responsibility because they require page-image inspection. The finalizer does not pretend shell utilities can judge typography like a human or vision model.

## `issue.yml` Finalization

`issue.yml` must not point to binary output files until those files have been reconstructed and validated.

After successful reconstruction, the finalizer updates only controlled top-level publication metadata and generated-artifact blocks. It preserves all unrelated issue metadata and slots.

For ISSUE-005 the finalizer will:

- set `status: published`;
- set `original_format: magazine_v3`;
- set `diagnostic: false`;
- replace the diagnostic failure note with a short finalization note;
- add a `pdf` block containing relative path, SHA-256, and byte size;
- add a `preview` block containing relative path, SHA-256, and byte size.

The implementation will use a small dependency-free top-level YAML block editor rather than importing a general YAML package solely for this controlled mutation. Tests must prove it preserves unrelated content and correctly replaces existing blocks.

## Workflow Triggers

The workflow is stored at:

`.github/workflows/casebook-finalizer.yml`

It supports two entry paths.

### Automatic future path

`push` to branches matching:

`publish/issue-*`

with a changed path matching:

`issues/**/.handoff/manifest.json`

Future publication branches created from `main` after this subsystem is merged inherit the workflow and finalize automatically when the manifest arrives.

### ISSUE-005 rescue path

`workflow_dispatch` accepts one required `target_branch` input.

The workflow file runs from `main`, validates that `target_branch` matches the publication-branch pattern, checks out that branch, locates exactly one ready handoff manifest, and finalizes it.

This avoids rebasing ISSUE-005 merely to make the workflow file exist on that older branch.

## Commit and Pull Request Behavior

After all checks pass, the workflow:

1. Deletes the issue's `.handoff/` directory.
2. Stages only the finalized issue directory.
3. Verifies no other repository paths changed.
4. Commits with message `build: finalize ISSUE-###`.
5. Pushes to the same publication branch.
6. Checks for an existing open PR from that branch to `main`.
7. If none exists, opens a draft PR titled `Publish Engineering Casebook ISSUE-###`.
8. Never merges the PR.

For Issues 005–007, the existing supervised-publication rule remains unchanged. Later automation may alter merge policy only through a separate explicit repository change.

## GitHub Actions Security Model

The repository is public, but the finalizer is intentionally designed without secrets.

### Required workflow permissions

```yaml
permissions:
  contents: write
  pull-requests: write
```

No additional permissions are granted.

### Explicit security constraints

- No repository or environment secrets.
- No personal access token.
- No `pull_request_target` trigger.
- No execution of code from fork pull requests with a write-capable token.
- No dynamic downloading or execution of scripts specified by issue content.
- No shell evaluation of manifest values.
- Manifest paths are validated before filesystem use.
- Publication branches must match the strict branch pattern.
- `workflow_dispatch` is available only to users with repository workflow permissions.
- Automatic `push` runs occur only for branches in the upstream repository; pushes inside a fork do not grant access to the upstream repository token.
- The workflow uses the built-in `GITHUB_TOKEN`, whose repository scope expires with the job.
- Third-party Actions are avoided. GitHub-owned checkout tooling may be used and should be pinned to a reviewed immutable commit SHA during implementation.

## Repository Files

The subsystem adds focused files with separate responsibilities:

- `.github/workflows/casebook-finalizer.yml` — event handling, permissions, runner setup, finalizer invocation, commit/push, and PR creation.
- `scripts/casebook_finalizer.py` — handoff validation, reconstruction, integrity checks, PDF mechanical validation, controlled `issue.yml` update, and cleanup.
- `tests/test_casebook_finalizer.py` — dependency-free unit tests for path validation, base64 reconstruction, hash/size checks, YAML-block mutation, and failure behavior.
- `docs/casebook-finalizer.md` — concise operator documentation for the scheduled publisher handoff contract and manual ISSUE-005 rescue.
- `skills/casebook-publisher/SKILL.md` — publisher contract updated so binary artifacts use the handoff rather than direct GitHub binary writes.
- `docs/validation-standard.md` — publication validation wording updated to recognize the finalizer boundary while preserving all existing blocking quality requirements.

## Failure Behavior

The finalizer is fail-closed.

If any validation step fails:

- no PR is created by that run;
- no invalid decoded artifact replaces an existing path;
- `.handoff/` remains intact for diagnosis;
- the workflow exits non-zero with a stage-specific message;
- the publication branch remains available for repair;
- `main` is never modified directly.

If binary reconstruction succeeds but a later mechanical PDF check fails, temporary decoded files are removed and the handoff remains.

If the commit/push step fails after local finalization, the runner exits non-zero and GitHub retains the logs; the next manual dispatch is safe because the finalizer is idempotent.

## Idempotency

Repeated runs are safe.

- If an output already exists with the exact expected hash, it is accepted rather than regenerated.
- If an output exists with a different hash, it is replaced only after the handoff artifact validates completely.
- If no `.handoff/manifest.json` exists, the finalizer exits without changing publication data.
- If the PR already exists, the workflow does not create a duplicate.

## ISSUE-005 Rollout

The existing `publish/issue-005-2026-08-18` branch is preserved. No research or editorial stages are repeated merely to test transport.

Rollout sequence:

1. Merge the finalizer infrastructure change to `main` after review.
2. Run a focused scheduled task on the existing ISSUE-005 branch that recreates the already-generated local PDF/preview, performs the same local visual inspection, and writes only the base64 chunk handoff plus `manifest.json`.
3. Manually dispatch `Casebook Finalizer` from `main` with `target_branch=publish/issue-005-2026-08-18`.
4. Verify reconstructed PDF and preview hashes, workflow logs, final `issue.yml`, and the draft PR.
5. Review ISSUE-005 manually before merging, as already required.
6. Remove diagnostic-only files from the publication branch before merge, including `.publisher-diagnostic.md`, `.scheduled-github-smoke-test.txt`, and the known truncated diagnostic binary blobs if they are not replaced by the valid finalizer outputs.
7. After ISSUE-005 proves the pipeline, simplify the recurring scheduled publisher prompt so repository rules and `skills/casebook-publisher/SKILL.md` remain the canonical workflow definition.

## Acceptance Criteria

The subsystem is accepted when all of the following are true:

1. The repository contains no new secrets or long-lived credentials.
2. A synthetic unit test reconstructs known bytes from multiple base64 chunks and rejects one-byte corruption.
3. Traversal attempts and invalid branch/issue paths are rejected.
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
