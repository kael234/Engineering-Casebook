# Casebook Finalizer

The Casebook Finalizer bridges one deliberately narrow gap in the publication workflow: the scheduled ChatGPT publisher can generate and inspect PDF/JPEG binaries, but its connected GitHub text write path does not reliably preserve arbitrary binary bytes.

The publisher therefore hands binaries over without relying on a text write path. The preferred transport is raw Git blobs (`manifest.json` with `schema_version: 2`); base64 chunking is the legacy path, kept for existing handoffs and recovery. GitHub Actions reconstructs the exact bytes, verifies them, performs mechanical PDF checks, and commits only validated binary artifacts to the publication branch.

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

The manifest is the readiness signal. A partial chunk upload without `manifest.json` is inert and must not be finalized.

### Preferred transport: raw Git blobs (schema 2)

Base64 chunking is legacy. It is retained only to read handoffs that already exist, and for recovery. New issues use raw binary blobs:

```text
.handoff/
  pdf.bin
  preview.bin
  manifest.json      # schema_version: 2
```

The publisher writes the PDF and JPEG as Git blobs through the Git Data API — no text encoding at any point — and names them from the manifest as `input: pdf.bin` / `input: preview.bin`. `scripts/casebook_blob_handoff_adapter.py` runs first inside the Finalizer workflow, verifies exact byte size, SHA-256, PDF magic/trailer, JPEG magic/trailer, expected filenames, issue identity, declared page count and the visual-inspection declaration, then rewrites the manifest into the strict v1 contract the finalizer already enforces. A `schema_version: 1` manifest passes through untouched.

Prefer this path. A base64 stream is a single long string in which one dropped character destroys everything after it, and the loss is invisible until decode time. Raw blobs are byte-exact by construction and their hash is checked before anything else runs.

### Preferred atomic Git write

The connected publisher should prefer Git Data operations over one Contents-API commit per chunk. It creates all chunk blobs and the completed manifest blob without moving the branch, then creates one tree and one commit containing the entire `.handoff/` package and fast-forwards the publication branch once. The manifest and all of the bytes it names therefore become visible together.

This atomic tree commit is equivalent to "manifest last" for safety purposes and is preferred because a scheduled publisher cannot die halfway through a long sequence of tiny commits while leaving a misleading almost-ready handoff.

## Manifest contract

`manifest.json` records:

- `schema_version: 1` (base64 chunks) or `schema_version: 2` (raw `pdf.bin`/`preview.bin` blobs, converted to v1 by the adapter before finalization);
- the issue ID and repository-relative issue directory;
- `visual_inspection.passed: true` and the visually inspected page count;
- exactly one PDF artifact and one JPEG preview artifact;
- for each artifact: output filename, media type, exact decoded byte size, SHA-256, and either ordered chunk filenames (v1) or the raw `input` filename (v2).

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

## Abandoned-handoff rescue

A publisher can occasionally finish and visually validate a PDF, write a complete PDF chunk sequence, and then expire before the preview or readiness manifest is committed. Those chunks remain deliberately inert.

A focused recovery is available only when the issue metadata and the recovery request explicitly confirm that the layout was visually validated. Add:

```json
{"visual_inspection_passed": true}
```

as `.handoff/rescue-request.json`. The trusted **Casebook Handoff Rescue** Action then:

1. checks out rescue/finalizer tooling from `main` and the publication branch separately;
2. requires a complete sequential PDF chunk set and reconstructs it;
3. runs the existing mechanical PDF validation against `issue.yml`;
4. generates a page-1 JPEG preview from the reconstructed PDF;
5. computes exact PDF/preview byte sizes and SHA-256 hashes;
6. writes the preview chunks and strict `manifest.json`;
7. removes `rescue-request.json`; and
8. commits only the rescued issue directory.

The resulting manifest commit wakes the normal Casebook Finalizer. If reconstruction or validation fails, no readiness manifest is produced and the partial handoff remains available for diagnosis. The rescue path is not a substitute for visual inspection and may not be used to bless an uninspected PDF.

## Automatic publication flow

After the infrastructure is on `main`, a normal publication run is:

1. The scheduled publisher creates or resumes `publish/issue-###-YYYY-MM-DD`.
2. It writes the issue source package and prepares the base64 handoff locally.
3. It commits the complete handoff atomically through the Git Data API when available; the fallback is chunks first and `manifest.json` last.
4. The manifest-bearing publication-branch push can wake the Casebook Finalizer immediately.
5. For a normal unstacked branch, the publisher also opens or updates a **draft same-repository PR** from the publication branch to `main`; PR events remain an additional wake-up path.
6. The workflow checks out trusted executable tooling from `main` separately from the publication branch, which is treated as data.
7. After successful validation it commits the finalized PDF/preview back to the publication branch and removes `.handoff/`.
8. The scheduled publisher reports the direct PDF link and PR status to the task conversation only after Finalizer success.

`workflow_dispatch` remains a manual fallback. A stacked supervised publication branch may be finalized before a PR to `main` is appropriate; it must not open a misleading PR merely to wake the Finalizer.

The Action does not approve or merge pull requests. The scheduled publisher handles PR state according to `publication.supervised_through_issue` and the repository publisher rules.

## Security boundary for PR events

The write-capable workflow uses `pull_request`, never `pull_request_target`. The finalizer job runs for PR events only when:

- the PR head repository is this same repository; and
- the head branch starts with `publish/issue-`.

Fork PRs therefore do not execute the write-capable finalizer job. Finalizer code itself always comes from trusted `main`, not from the publication branch.

## Manual fallback

Committing a handoff is not the same as starting a workflow. Connected-GitHub writes have not always triggered Actions reliably, so the publisher must **verify that the expected run actually exists and succeeded** rather than assuming GitHub noticed.

If no run appears, use an explicitly supported trigger:

- **Casebook Finalizer** — `workflow_dispatch` from `main` with `target_branch` set to the publication branch.
- **Casebook Handoff Rescue** — `workflow_dispatch` from `main` with `target_branch` set to the publication branch. Its push trigger only fires on changes to `.handoff/rescue-request.json`, so commits that repair chunks or binaries do not re-arm it.
- Reopening or synchronizing the publication PR, which both workflows accept as a wake-up.

The manual path performs the same reconstruction, integrity verification, PDF checks, `issue.yml` finalization, handoff removal, and binary commit. It does not change the editorial content or bypass any quality gate.

### Publication success requires Finalizer success

An issue is not delivered because a branch exists, a PR exists, or handoff files exist. Success requires all of: a complete handoff, a Finalizer run that passed, the final binary artifacts present in the issue directory, and finalized metadata. Anything short of that is an unfinished publication and must be reported as one.

## Delivery back to ChatGPT

The repository is the durable archive, but the user-facing delivery point is the scheduled task conversation. After successful finalization, the publisher should return a prominent clickable PDF link, the five-case summary, important toolbox additions, evidence gaps, Finalizer status, and the supervised PR link/status.

For an unmerged supervised issue, use the publication-branch GitHub PDF link. After merge, prefer the corresponding `main` link.

## Failure behavior

The finalizer and rescue workflow are fail-closed. If reconstruction or validation fails, invalid decoded bytes do not replace the issue outputs, `issue.yml` is not finalized, and the incomplete handoff remains for diagnosis. GitHub Actions logs identify the failing gate.

No repository secrets, environment secrets, personal access tokens, or third-party write-capable Actions are required.
