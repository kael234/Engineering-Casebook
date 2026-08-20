# Casebook Finalizer — Legacy Recovery Infrastructure

The normal Casebook path no longer transports PDF/JPEG binaries from ChatGPT. `scripts/render_casebook.py`, `scripts/publish_casebook_render.py`, and the **Casebook Deterministic Publisher** workflow generate and mechanically validate binaries inside a trusted GitHub Actions checkout, then commit them directly to the publication branch as `status: rendered`.

The Finalizer, blob adapter and Handoff Rescue remain in the repository only to recover historical handoffs that already exist.

## When legacy recovery is appropriate

Use this machinery only when an earlier run already produced and visually inspected an exact PDF but left one of these durable states:

- a complete schema-v2 `pdf.bin` / `preview.bin` handoff;
- a complete schema-v1 base64 chunk handoff;
- a complete, validated PDF chunk set abandoned before preview/manifest creation.

Do not create a new handoff for a normal issue. Do not use rescue to bless an uninspected PDF.

## Legacy schema-v2 raw-blob handoff

```text
.handoff/
  pdf.bin
  preview.bin
  manifest.json
```

The adapter verifies exact byte size, SHA-256, PDF/JPEG signatures, filenames, issue identity, page count and visual-inspection declaration, then converts the manifest to the strict schema-v1 contract consumed by the Finalizer.

Git API requests may encode bytes as base64 because that is the API request representation; Git stores and hashes the decoded raw blob. This is not the old multi-file base64 transport.

## Legacy schema-v1 chunk handoff

```text
.handoff/
  pdf.part001.b64
  pdf.part002.b64
  preview.part001.b64
  manifest.json
```

Chunks are RFC 4648 ASCII, at most 16,000 characters, sequentially named, and listed in order. `manifest.json` is the readiness signal. A partial chunk set without it is inert.

## Legacy Handoff Rescue

A rescue request contains exactly:

```json
{"visual_inspection_passed": true}
```

The trusted workflow reconstructs the complete PDF, runs the existing mechanical checks, generates the preview, writes a strict manifest, and removes the rescue request. Because pushes made with `GITHUB_TOKEN` do not trigger a second workflow, the Finalizer may require explicit dispatch after rescue.

## Mechanical checks

Legacy finalization still requires:
- exact reconstructed byte sizes and SHA-256 hashes;
- valid PDF/JPEG signatures;
- exactly 3 pages or a justified 4 pages;
- A4 dimensions within ±2 points;
- at least 1,800 extracted words and 10,000 non-whitespace characters;
- one live URI annotation per issue slot;
- embedded fonts;
- every declared Markdown, snapshot and SVG path present.

## Security boundary

Write-capable workflows use trusted executable code from `main`, check out the publication branch separately as data, reject fork write jobs, validate publication branch/issue identity, and commit only the selected issue directory.

## Failure behaviour

Legacy tools remain fail-closed. Invalid bytes do not replace outputs, metadata is not finalized, and incomplete recovery state remains available for diagnosis.
