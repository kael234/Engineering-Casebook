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

The manifest is written **last**. Its presence is the readiness signal. A partial chunk upload without `manifest.json` is inert and must not be finalized.

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

## Automatic publication flow

After the infrastructure is on `main`, a normal publication run is:

1. The scheduled publisher creates or resumes `publish/issue-###-YYYY-MM-DD`.
2. It writes the issue source package and all base64 chunks.
3. It commits `.handoff/manifest.json` last.
4. It opens or updates a **draft same-repository PR** from the publication branch to `main`.
5. The PR `opened`, `synchronize`, or `reopened` event is the authoritative automatic wake-up path for the Casebook Finalizer when the PR diff contains `issues/**/.handoff/manifest.json`.
6. The workflow checks out trusted executable tooling from `main` separately from the publication branch, which is treated as data.
7. After successful validation it commits the finalized PDF/preview back to the publication branch and removes `.handoff/`.
8. The scheduled publisher reports the direct PDF link and PR status to the task conversation only after Finalizer success.

The workflow also keeps the original `push` trigger as a backup for ordinary Git pushes and `workflow_dispatch` as a manual fallback. Connected GitHub-app writes have been observed not to wake the push trigger reliably, which is why the same-repository PR event is the primary path.

The Action does not open, approve, or merge pull requests. The scheduled publisher opens the draft PR through the connected GitHub app. Issues 005–007 remain human-reviewed.

## Security boundary for PR events

The write-capable workflow uses `pull_request`, never `pull_request_target`. The finalizer job runs for PR events only when:

- the PR head repository is this same repository; and
- the head branch starts with `publish/issue-`.

Fork PRs therefore do not execute the write-capable finalizer job. Finalizer code itself always comes from trusted `main`, not from the publication branch.

## Manual fallback

If automatic PR-triggered finalization does not start, run **Casebook Finalizer** manually from `main` using `workflow_dispatch` with `target_branch` set to the publication branch.

The manual path performs the same reconstruction, integrity verification, PDF checks, `issue.yml` finalization, handoff removal, and binary commit. It does not change the editorial content or bypass any quality gate.

## Delivery back to ChatGPT

The repository is the durable archive, but the user-facing delivery point is the scheduled task conversation. After successful finalization, the publisher should return a prominent clickable PDF link, the five-case summary, important toolbox additions, evidence gaps, Finalizer status, and the supervised PR link/status.

For an unmerged supervised issue, use the publication-branch GitHub PDF link. After merge, prefer the corresponding `main` link.

## Failure behavior

The finalizer is fail-closed. If reconstruction or validation fails, invalid decoded bytes do not replace the issue outputs, `issue.yml` is not finalized, and `.handoff/` remains for diagnosis. GitHub Actions logs identify the failing gate.

No repository secrets, environment secrets, personal access tokens, or third-party write-capable Actions are required.
