# Casebook Finalizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure GitHub Actions finalizer that reconstructs the scheduled publisher's PDF and JPEG from text-safe base64 chunks, verifies them exactly, runs mechanical publication checks, commits the valid binaries to the publication branch, and leaves Issues 005–007 supervised.

**Architecture:** The scheduled ChatGPT publisher remains responsible for research, writing, figures, local PDF generation, and visual inspection. It commits only text/SVG publication material plus a manifest-last `.handoff/` directory. GitHub Actions executes trusted finalizer code from `main`, treats the publication branch as data, reconstructs the binaries, validates them, finalizes `issue.yml`, removes the handoff, and pushes only the finalized issue directory.

**Tech Stack:** Python 3 standard library, `unittest`, GitHub Actions on Ubuntu, `poppler-utils` (`pdfinfo`, `pdftotext`, `pdffonts`), Git CLI, GitHub-owned `actions/checkout` pinned to an immutable SHA.

**Spec:** `docs/superpowers/specs/2026-08-18-casebook-finalizer-design.md`

## Global Constraints

- No repository or environment secrets.
- No personal access token.
- Workflow permissions are exactly `contents: write` unless GitHub itself requires a narrower read permission implicitly.
- No `pull_request` or `pull_request_target` execution path for the write-capable finalizer.
- Executable finalizer code always comes from canonical `main`; publication-branch content is data only.
- Publication branches must match `^publish/issue-[0-9]{3}-[0-9]{4}-[0-9]{2}-[0-9]{2}$`.
- Handoff `schema_version` is exactly `1`.
- Artifact size ceiling is 20 MiB per artifact.
- Chunk size contract is at most 16,000 ASCII base64 characters per chunk.
- Normal issues have exactly 3 A4 pages; 4 pages require both `page_count: 4` and non-empty `page_count_override_reason` in `issue.yml`.
- A4 tolerance is ±2.0 points around 595.28 × 841.89 points.
- Extracted text must contain at least 1,800 whitespace-delimited words and at least 10,000 non-whitespace characters.
- URI annotations must be at least the number of issue slots; ISSUE-005+ normal issues therefore require at least five.
- Every font listed by `pdffonts` must report `emb` as `yes`.
- Issues 005–007 are never auto-merged.
- The Action never opens, approves, or merges a pull request.
- TDD applies to Python behavior: write a failing test, run it and observe the expected failure, then add the minimum implementation.

## File Map

- Create `.github/workflows/casebook-finalizer.yml`: trigger/permission boundary, trusted tooling checkout, publication-data checkout, package install, finalizer invocation, path-scope guard, commit and push.
- Create `scripts/casebook_finalizer.py`: manifest validation, safe path resolution, binary reconstruction, integrity checks, controlled `issue.yml` update, mechanical PDF validation, cleanup, CLI.
- Create `tests/test_casebook_finalizer.py`: dependency-free `unittest` coverage for schema/path validation, corruption rejection, magic checks, YAML mutation, idempotency, and CLI-safe behavior.
- Create `docs/casebook-finalizer.md`: operator contract for scheduled publisher handoff and ISSUE-005 rescue.
- Modify `skills/casebook-publisher/SKILL.md`: replace direct binary GitHub persistence with manifest-last text handoff and draft-PR timing.
- Modify `docs/validation-standard.md`: preserve quality gates while defining the scheduled-publisher/Action split for binary persistence.

---

### Task 1: Manifest and Path Validation Core

**Files:**
- Create: `tests/test_casebook_finalizer.py`
- Create: `scripts/casebook_finalizer.py`

**Interfaces:**
- Produces: `FinalizerError(Exception)`, `validate_branch(branch: str, issue_id: str) -> None`, `load_and_validate_manifest(repo_root: pathlib.Path, manifest_path: pathlib.Path, branch: str) -> dict`, `safe_issue_dir(repo_root: pathlib.Path, issue_dir: str) -> pathlib.Path`.
- Later tasks consume the validated manifest dictionary and safe issue directory returned here.

- [ ] **Step 1: Write failing manifest-validation tests**

Create `tests/test_casebook_finalizer.py` with standard-library imports, a helper that creates a temporary repository tree, and these initial behaviors:

```python
import json
import pathlib
import tempfile
import unittest

from scripts.casebook_finalizer import (
    FinalizerError,
    load_and_validate_manifest,
    validate_branch,
)


class FinalizerTests(unittest.TestCase):
    def write_manifest(self, root: pathlib.Path, manifest: dict) -> pathlib.Path:
        handoff = root / manifest["issue_dir"] / ".handoff"
        handoff.mkdir(parents=True)
        path = handoff / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def valid_manifest(self) -> dict:
        return {
            "schema_version": 1,
            "issue_id": "ISSUE-005",
            "issue_dir": "issues/ISSUE-005-nothing-is-secondary",
            "visual_inspection": {"passed": True, "page_count": 3},
            "artifacts": [
                {
                    "role": "pdf",
                    "output": "ISSUE-005-nothing-is-secondary.pdf",
                    "media_type": "application/pdf",
                    "byte_size": 10,
                    "sha256": "0" * 64,
                    "chunks": ["pdf.part001.b64"],
                },
                {
                    "role": "preview",
                    "output": "preview.jpg",
                    "media_type": "image/jpeg",
                    "byte_size": 10,
                    "sha256": "1" * 64,
                    "chunks": ["preview.part001.b64"],
                },
            ],
        }

    def test_valid_branch_matches_issue(self):
        validate_branch("publish/issue-005-2026-08-18", "ISSUE-005")

    def test_branch_issue_mismatch_is_rejected(self):
        with self.assertRaises(FinalizerError):
            validate_branch("publish/issue-006-2026-08-18", "ISSUE-005")

    def test_manifest_rejects_unknown_top_level_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["command"] = "rm -rf /"
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_manifest_rejects_traversal_in_issue_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["issue_dir"] = "issues/ISSUE-005-../../escape"
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_manifest_rejects_chunk_path_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["artifacts"][0]["chunks"] = ["../pdf.part001.b64"]
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
python -m unittest tests.test_casebook_finalizer -v
```

Expected: import failure because `scripts.casebook_finalizer` does not yet exist.

- [ ] **Step 3: Implement the minimum validation core**

Create `scripts/casebook_finalizer.py` with:

```python
class FinalizerError(RuntimeError):
    pass
```

Then implement strict regular expressions and exact-key validation for the manifest contract from the design. Reject booleans masquerading as integers (`bool` is a subclass of `int` in Python), require exactly two artifacts with roles `{pdf, preview}`, enforce output/media-type pairs, size/hash formats, unique outputs/chunks, exact visual-inspection keys, and the issue/branch numeric match. Resolve issue paths and confirm they remain beneath `repo_root / "issues"`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python -m unittest tests.test_casebook_finalizer -v
```

Expected: all Task 1 tests PASS.

- [ ] **Step 5: Add boundary tests before refactoring**

Add tests that reject: wrong schema version; uppercase SHA-256; byte size 0; byte size above `20 * 1024 * 1024`; false visual inspection; page count 2; duplicate chunk names; output containing `/`; artifact extra keys; invalid issue directory characters; invalid branch date shape.

Run the suite first and confirm the new tests fail for the missing edge behavior, then extend validation minimally until they pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add scripts/casebook_finalizer.py tests/test_casebook_finalizer.py
git commit -m "feat: validate Casebook handoff manifests"
```

---

### Task 2: Binary Reconstruction and Controlled Manifest Mutation

**Files:**
- Modify: `tests/test_casebook_finalizer.py`
- Modify: `scripts/casebook_finalizer.py`

**Interfaces:**
- Produces: `reconstruct_artifact(issue_dir: pathlib.Path, artifact: dict) -> bytes`, `render_issue_yml(existing: str, artifacts: dict[str, dict]) -> str`.
- `reconstruct_artifact` returns verified bytes without touching the target output path.
- `render_issue_yml` returns replacement text; callers decide when to persist it.

- [ ] **Step 1: Write failing reconstruction tests**

Add tests using known bytes:

```python
import base64
import hashlib


def artifact_for(role: str, output: str, media_type: str, raw: bytes, chunks: list[str]) -> dict:
    return {
        "role": role,
        "output": output,
        "media_type": media_type,
        "byte_size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "chunks": chunks,
    }
```

Test a PDF-like payload beginning `%PDF-` split across two base64 chunks, and a JPEG-like payload beginning `b"\xff\xd8\xff"` and ending `b"\xff\xd9"`. Add separate tests for one-character base64 corruption, byte-size mismatch, SHA mismatch, wrong PDF magic, and wrong JPEG trailer.

- [ ] **Step 2: Verify RED**

Run the reconstruction tests and confirm failure because `reconstruct_artifact` is absent.

- [ ] **Step 3: Implement strict reconstruction**

Read only manifest-declared filenames from `issue_dir / ".handoff"`; decode ASCII; accept only base64 alphabet plus ASCII whitespace; remove whitespace; use `base64.b64decode(..., validate=True)`; verify size, hash and magic; return bytes. Do not write the final output here.

- [ ] **Step 4: Verify GREEN**

Run all unit tests and confirm PASS.

- [ ] **Step 5: Write failing `issue.yml` mutation tests**

Use a realistic ISSUE-005 fixture containing slots, snapshots, assets, `status: draft`, `original_format: magazine_v3_diagnostic`, `diagnostic: true`, and the diagnostic failure note. Assert that mutation:

```text
status: published
original_format: magazine_v3
diagnostic: false
note: Binary artifacts finalized and mechanically validated by GitHub Actions.
```

and adds exactly:

```yaml
pdf:
  path: ISSUE-005-nothing-is-secondary.pdf
  sha256: <hash>
  byte_size: <size>
preview:
  path: preview.jpg
  sha256: <hash>
  byte_size: <size>
```

Assert the slots/snapshots/assets section remains byte-for-byte unchanged. Add idempotency test: running the mutation twice returns identical text.

- [ ] **Step 6: Verify RED, implement the controlled editor, then GREEN**

Implement only a top-level scalar/block editor. Do not parse arbitrary YAML. Recognize unindented top-level keys, preserve unrelated slices exactly, replace/remove only controlled keys `status`, `original_format`, optional `diagnostic`, the known diagnostic `note`, `pdf`, and `preview`.

Run:

```bash
python -m unittest tests.test_casebook_finalizer -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add scripts/casebook_finalizer.py tests/test_casebook_finalizer.py
git commit -m "feat: reconstruct Casebook binary handoffs"
```

---

### Task 3: Mechanical PDF Validation and Fail-Closed Finalization

**Files:**
- Modify: `tests/test_casebook_finalizer.py`
- Modify: `scripts/casebook_finalizer.py`

**Interfaces:**
- Produces: `validate_pdf(pdf_path: pathlib.Path, issue_dir: pathlib.Path, issue_yml_text: str, expected_pages: int) -> None`, `finalize(repo_root: pathlib.Path, manifest_path: pathlib.Path, branch: str) -> str`, and CLI `python scripts/casebook_finalizer.py --repo-root PATH --manifest PATH --branch NAME`.
- `finalize` returns the issue ID on success and raises `FinalizerError` on any failed gate.

- [ ] **Step 1: Add unit tests for issue-manifest reference checks**

Without requiring Poppler in unit tests, isolate and test helpers that extract `page_count`, optional `page_count_override_reason`, slot count, Markdown path, snapshot paths, and asset paths from the controlled `issue.yml` structure. Assert missing referenced files fail before finalization.

- [ ] **Step 2: Verify RED and implement reference-check helpers**

Run the new tests, confirm expected failure, implement minimal parsing for the repository's known `issue.yml` shape, and rerun to GREEN.

- [ ] **Step 3: Implement Poppler command wrappers**

Use `subprocess.run` with argument lists only, `check=True`, captured UTF-8 output, and no shell. `validate_pdf` must:

1. call `pdfinfo` and verify page count;
2. call `pdfinfo -f N -l N` for each page and parse `Page size:` points to verify A4 ±2.0 pt;
3. call `pdftotext <pdf> -` and verify ≥1,800 words and ≥10,000 non-whitespace characters;
4. extract URI annotations with `pdfinfo -url` when available; if the runner's Poppler lacks that option, fail with an explicit unsupported-tool message rather than silently skipping the gate;
5. call `pdffonts` and verify every data row reports embedded `yes`;
6. verify issue slot count and required Markdown/snapshot/SVG paths exist;
7. enforce the 3-page normal rule or explicit 4-page override.

- [ ] **Step 4: Implement fail-closed `finalize` ordering**

Required order:

```text
validate manifest
→ reconstruct PDF/JPEG to memory
→ write temporary files beside targets
→ run all mechanical checks against temporary PDF
→ render replacement issue.yml in memory
→ atomically replace PDF/JPEG outputs
→ atomically replace issue.yml
→ remove .handoff/
```

On any exception before the atomic replacement stage, remove temporary files and leave existing outputs, `issue.yml`, and `.handoff/` untouched. If target outputs already match expected hashes, reuse them idempotently but still run validation before finalizing metadata/cleanup.

- [ ] **Step 5: Add fail-closed filesystem tests**

Patch the Poppler wrapper at the narrow subprocess boundary so a deterministic `FinalizerError` occurs after temporary reconstruction. Assert:

- pre-existing target bytes are unchanged;
- `issue.yml` is unchanged;
- `.handoff/manifest.json` remains;
- no temporary files remain.

Then test successful finalization with validation helper patched to succeed: outputs replaced, `issue.yml` finalized, `.handoff/` removed.

- [ ] **Step 6: Verify complete unit suite**

```bash
python -m unittest tests.test_casebook_finalizer -v
```

Expected: all tests PASS with no warnings/errors.

- [ ] **Step 7: Commit Task 3**

```bash
git add scripts/casebook_finalizer.py tests/test_casebook_finalizer.py
git commit -m "feat: validate and finalize Casebook publications"
```

---

### Task 4: GitHub Actions Trust Boundary and Publication Contracts

**Files:**
- Create: `.github/workflows/casebook-finalizer.yml`
- Create: `docs/casebook-finalizer.md`
- Modify: `skills/casebook-publisher/SKILL.md`
- Modify: `docs/validation-standard.md`

**Interfaces:**
- Workflow consumes `target_branch` for `workflow_dispatch`, or `github.ref_name` for automatic push runs.
- Workflow invokes trusted `main` tooling as:

```bash
python "$GITHUB_WORKSPACE/tooling/scripts/casebook_finalizer.py" \
  --repo-root "$GITHUB_WORKSPACE/publication" \
  --manifest "$MANIFEST" \
  --branch "$TARGET_BRANCH"
```

- [ ] **Step 1: Create the workflow with minimum permissions**

Use:

```yaml
name: Casebook Finalizer

on:
  push:
    branches:
      - 'publish/issue-*'
    paths:
      - 'issues/**/.handoff/manifest.json'
  workflow_dispatch:
    inputs:
      target_branch:
        description: Publication branch to finalize
        required: true
        type: string

permissions:
  contents: write
```

The job runs on `ubuntu-latest`, validates `TARGET_BRANCH` with a fixed Bash regex before checkout, installs `poppler-utils`, checks out `main` into `tooling/`, checks out the exact publication branch into `publication/`, locates exactly one `issues/**/.handoff/manifest.json`, invokes the trusted main-branch script, stages only the finalized issue directory, rejects any staged path outside it, commits `build: finalize ISSUE-###`, and pushes `HEAD:$TARGET_BRANCH`.

Do not use `pull_request`, `pull_request_target`, secrets, PATs, dynamic `curl | sh`, or publication-branch scripts.

Pin `actions/checkout` to the current reviewed immutable commit SHA, not a floating major tag.

- [ ] **Step 2: Add operator documentation**

`docs/casebook-finalizer.md` must document:

- why binary handoff exists;
- exact `.handoff/` structure;
- manifest-last readiness rule;
- 16,000-character chunk ceiling;
- SHA/size fields;
- the fact that the scheduled publisher visually inspects before handoff;
- automatic future behavior;
- manual ISSUE-005 rescue using `workflow_dispatch`;
- failure behavior and where to inspect Actions logs;
- no secrets/PAT requirement.

- [ ] **Step 3: Update publisher skill**

In `skills/casebook-publisher/SKILL.md`, change the publish stage so it:

1. generates and visually inspects PDF/preview locally;
2. does not attempt direct GitHub binary writes;
3. base64-encodes each binary, splits to ≤16,000-character UTF-8 chunks, calculates SHA-256 and byte size;
4. commits all chunks before `.handoff/manifest.json`;
5. writes the readiness manifest last;
6. creates the supervised draft PR through the GitHub connector after the readiness manifest exists;
7. never merges Issues 005–007.

- [ ] **Step 4: Update validation standard**

Preserve every existing blocking quality gate. Clarify that for ISSUE-005+, the scheduled publisher must verify the locally generated PDF before handoff and the finalizer must verify exact reconstructed bytes plus mechanical PDF checks before `issue.yml` registers the binary artifacts.

- [ ] **Step 5: Static workflow/security checks**

Run:

```bash
grep -n "pull_request_target\|pull_request:" .github/workflows/casebook-finalizer.yml && exit 1 || true
grep -n "secrets\.\|personal.*token\|PAT" .github/workflows/casebook-finalizer.yml && exit 1 || true
grep -n "permissions:" -A3 .github/workflows/casebook-finalizer.yml
```

Expected: no PR trigger, no secret references, and only `contents: write` permission.

- [ ] **Step 6: Run all Python tests again**

```bash
python -m unittest tests.test_casebook_finalizer -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add .github/workflows/casebook-finalizer.yml docs/casebook-finalizer.md skills/casebook-publisher/SKILL.md docs/validation-standard.md
git commit -m "ci: add Casebook publication finalizer"
```

---

### Task 5: Local Integration Verification and Infrastructure PR

**Files:**
- No new production files expected.
- May modify tests only if a verified integration defect is found, following TDD.

**Interfaces:**
- Produces the reviewed `infra/casebook-finalizer` branch ready for merge to `main`.

- [ ] **Step 1: Install Poppler in the isolated development environment if available**

```bash
which pdfinfo || true
which pdftotext || true
which pdffonts || true
```

If unavailable locally, unit tests remain authoritative for Python behavior and the first GitHub Actions run is the integration environment for Poppler. Do not weaken or delete the Poppler gates to accommodate the local container.

- [ ] **Step 2: Run complete test suite**

```bash
python -m unittest discover -s tests -v
```

Expected: 0 failures, 0 errors.

- [ ] **Step 3: Compile-check the finalizer**

```bash
python -m py_compile scripts/casebook_finalizer.py
```

Expected: exit 0.

- [ ] **Step 4: Verify branch diff scope**

```bash
git diff --check main...HEAD
git diff --name-only main...HEAD
```

Expected changed paths only under:

```text
.github/workflows/casebook-finalizer.yml
docs/casebook-finalizer.md
docs/superpowers/plans/2026-08-18-casebook-finalizer.md
docs/superpowers/specs/2026-08-18-casebook-finalizer-design.md
scripts/casebook_finalizer.py
skills/casebook-publisher/SKILL.md
docs/validation-standard.md
tests/test_casebook_finalizer.py
```

- [ ] **Step 5: Security grep**

```bash
grep -RniE "pull_request_target|secrets\.|ghp_|github_pat_|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY" .github scripts docs skills tests || true
```

Expected: no credential material and no `pull_request_target`. Documentation may mention forbidden terms only in explanatory prose; workflow and executable code must not use them.

- [ ] **Step 6: Push branch and open an infrastructure PR**

Push `infra/casebook-finalizer` and open a non-draft PR to `main` titled:

`Add Casebook binary finalizer`

PR body summarizes the proven failure, the text-safe handoff, trust boundary, tests, and the ISSUE-005 rollout. Do not merge automatically.

- [ ] **Step 7: After human review, merge infrastructure before ISSUE-005 rescue**

ISSUE-005 cannot use the manual finalizer dispatch until the workflow and trusted script exist on `main`. After merge, run the focused scheduled handoff task for the existing issue branch, then dispatch the finalizer, inspect the resulting Action logs and binary hashes, and keep the ISSUE-005 publication PR supervised.
