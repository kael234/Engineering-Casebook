# Casebook Finalizer

The Casebook Finalizer bridges one deliberately narrow gap in the publication workflow: the scheduled ChatGPT publisher can generate and inspect PDF/JPEG binaries, but its connected GitHub text write path does not reliably preserve arbitrary binary bytes.

The publisher therefore transports generated binaries as base64 text. GitHub Actions reconstructs the exact bytes, verifies them, performs mechanical PDF checks, and commits only validated binary artifacts to the publication branch.

## Responsibility split

The scheduled publisher still owns research, source verification, canonical records, SVG figures, magazine composition, local PDF generation, page rendering, and visual inspection. GitHub Actions does not call an LLM or redo editorial work.

The finalizer owns binary reconstruction, exact byte-size and SHA-256 verification, PDF mechanical validation, controlled `issue.yml` finalization, handoff cleanup, and the final binary commit.

## Handoff layout

For an issue directory such as `issues/ISSUE-005-nothing-is-secondary/`, the publisher creates:

```text
.handoff/
  pdf.part001.b64
  pdf.part002.b64
  ...
  preview.part001.b64
  manifest.json
```

Each chunk contains standard RFC 4648 base64 ASCII and is at most 16,000 characters. Chunk order is recorded explicitly in `manifest.json`.

The manifest is written **last**. Its presence is the readiness signal. A partial chunk upload without `manifest.json` is inert and does not trigger automatic finalization.

## Manifest contract

`manifest.json` records:

- `schema_version: 1`;
- the issue ID and repository-relative issue directory;
- `visual_inspection.passed: true` and the visually inspected page count;
- exactly one PDF artifact and one JPEG preview artifact;
- for each artifact: output filename, media type, exact decoded byte size, SHA-256, and ordered chunk filenames.

The finalizer rejects unknown fields, path traversal, symlinked handoff/manifest/chunk/`issue.yml` inputs, mismatched issue/branch IDs, invalid chunk names, chunks larger than 16,000 characters, duplicate outputs/chunks, invalid hashes, artifacts larger than 20 MiB, or a handoff that does not explicitly record successful visual inspection.

## Mechanical PDF checks

On Ubuntu the Action installs `poppler-utils` and requires:

- exact reconstructed byte size and SHA-256;
- valid PDF/JPEG magic;
- 3 pages normally, or an explicitly justified 4-page issue;
- A4 dimensions within ±2 points on every page;
- at least 1,800 extracted words and 10,000 non-whitespace characters;
- at least one live URI annotation per issue slot;
- every reported PDF font embedded;
- every Markdown, snapshot, and SVG path listed by `issue.yml` present.

Visual checks such as clipping, overlap, diagram legibility, hierarchy, and dead-space use remain the scheduled publisher's responsibility before the handoff is created.

## Automatic future runs

After this infrastructure is on `main`, new `publish/issue-*` branches inherit `.github/workflows/casebook-finalizer.yml`.

A push that adds `issues/**/.handoff/manifest.json` starts the finalizer. The workflow checks out trusted executable tooling from `main` separately from the publication branch, which is treated as data. After validation it commits the finalized issue back to the same publication branch.

The Action does not open or merge pull requests. The scheduled publisher opens the supervised draft PR through the connected GitHub app after committing the handoff manifest. Issues 005-007 remain human-reviewed.

## ISSUE-005 rescue

ISSUE-005 predates the workflow, so it uses the manual `workflow_dispatch` path after the infrastructure is merged to `main`.

1. Run a focused scheduled task that recreates the already-composed ISSUE-005 PDF and preview locally, visually inspects them, writes the base64 chunk files, and commits `manifest.json` last to `publish/issue-005-2026-08-18`.
2. In GitHub Actions, run **Casebook Finalizer** manually from `main` with `target_branch` set to `publish/issue-005-2026-08-18`.
3. Inspect the Action result. On success, the valid PDF/preview replace the known truncated diagnostic blobs, `issue.yml` is finalized, and `.handoff/` is removed.
4. Open or update the supervised ISSUE-005 draft PR and review it before merge.

No Issue-005 research or editorial work needs to be repeated merely to test transport.

## Failure behavior

The finalizer is fail-closed. If reconstruction or validation fails, invalid decoded bytes do not replace the issue outputs, `issue.yml` is not finalized, and `.handoff/` remains for diagnosis. GitHub Actions logs identify the failing gate.

No repository secrets, environment secrets, personal access tokens, or third-party write-capable Actions are required.
