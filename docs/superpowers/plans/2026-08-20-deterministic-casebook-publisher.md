# Deterministic Engineering Casebook Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repository-owned renderer and GitHub Actions publication stage that deterministically generates and mechanically validates Casebook PDFs/previews, leaving ChatGPT responsible only for visual approval, merge policy, and delivery.

**Architecture:** Trusted Python and HTML/CSS live on `main`; publication branches are checked out separately as data. GitHub Actions renders a declared three- or four-page issue, validates it with the existing Finalizer checks, commits the PDF/preview and `status: rendered` metadata directly to the publication branch, and uploads page renders for diagnosis. The 05:00 publisher reviews the exact rendered binary and promotes it to `published` only after visual approval.

**Tech Stack:** Python 3.12, standard-library `unittest`, PyYAML, Mistune, Jinja2, WeasyPrint, Pillow, Poppler (`pdfinfo`, `pdftotext`, `pdffonts`, `pdftoppm`), Git CLI, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-20-deterministic-casebook-publisher-design.md`

## Global Constraints

- Trusted renderer/workflow code comes from `main`; publication-branch content is data only.
- Publication branches must match `^publish/issue-[0-9]{3}-[0-9]{4}-[0-9]{2}-[0-9]{2}$`.
- The normal path does not create `.handoff/` data.
- Existing Finalizer/rescue code remains available for legacy recovery only.
- A successful render records `status: rendered`, not `published`.
- Visual inspection is still required before `published` status.
- Exactly 3 or 4 A4 pages; 4 pages require a non-empty `page_count_override_reason`.
- Existing Finalizer mechanical thresholds remain blocking: at least 1,800 words, 10,000 non-whitespace characters, one URI annotation per slot, A4 ±2 pt, and embedded fonts.
- Render output is staged in a temporary directory and moved into the issue directory only after all validation passes.
- The renderer does not rewrite editorial content or rebalance content between committed `PAGE N` sections.
- TDD applies to all Python behavior.

## File Map

- Create `scripts/render_casebook.py`: issue metadata/page parsing, controlled Markdown rendering, safe asset resolution, HTML composition, PDF generation, page-count verification.
- Create `scripts/publish_casebook_render.py`: publication-branch validation, source-package validation, preview generation, mechanical validation, hashes, atomic artifact placement, `status: rendered` metadata.
- Create `scripts/select_casebook_publication.py`: deterministic highest-unfinished publication-branch selection for scheduled workflow use.
- Create `templates/magazine.html`: trusted page shell.
- Create `templates/magazine.css`: deterministic A4 magazine layout.
- Create `requirements-publisher.txt`: pinned rendering dependencies.
- Create `tests/test_render_casebook.py`: parser, asset, URL, and HTML behavior.
- Create `tests/test_publish_casebook_render.py`: metadata transition, idempotency, path scope, and artifact hashing.
- Create `tests/test_select_casebook_publication.py`: branch selection behavior.
- Create `.github/workflows/casebook-publisher.yml`: scheduled/manual/PR renderer and controlled commit.
- Create `.github/workflows/casebook-publisher-ci.yml`: unit and ISSUE-006 integration tests for infrastructure PRs.
- Modify `schemas/issue.schema.json`: allow `rendered` status.
- Modify `AGENTS.md`, `casebook.yml`, `README.md`, `docs/validation-standard.md`, `docs/casebook-finalizer.md`, `templates/magazine-style.md`, and `skills/casebook-publisher/SKILL.md`: document one normal path.

---

### Task 1: Page Parsing and Safe Markdown Rendering

**Files:**
- Create: `tests/test_render_casebook.py`
- Create: `scripts/render_casebook.py`

**Interfaces:**
- Produces `IssueMeta`, `PageSection`, `load_issue_meta(path)`, `split_pages(markdown, expected_count)`, `render_markdown_page(markdown, issue_dir)`, and `build_html(issue_dir, meta, pages, template_path, css_path)`.

- [ ] **Step 1: Write failing tests for three/four-page parsing and malformed page markers.**

```python
class PageParsingTests(unittest.TestCase):
    def test_splits_contiguous_page_markers(self):
        pages = split_pages("# Intro\n\n## PAGE 1 - A\nOne\n\n## PAGE 2 - B\nTwo", 2)
        self.assertEqual([page.number for page in pages], [1, 2])

    def test_rejects_missing_page(self):
        with self.assertRaises(RenderError):
            split_pages("## PAGE 1 - A\nOne\n\n## PAGE 3 - C\nThree", 3)
```

- [ ] **Step 2: Run the focused test and observe import/function failure.**

Run: `.venv/bin/python -m unittest tests.test_render_casebook.PageParsingTests -v`

- [ ] **Step 3: Implement strict metadata and page parsing.**
- [ ] **Step 4: Add failing tests for path traversal, missing SVG, and bare URL linkification.**
- [ ] **Step 5: Implement safe asset resolution and Mistune plugins for images/URLs.**
- [ ] **Step 6: Run `tests.test_render_casebook` and keep all tests green.**
- [ ] **Step 7: Commit `test: define deterministic Casebook render contract`.**

### Task 2: HTML/CSS PDF Renderer

**Files:**
- Modify: `tests/test_render_casebook.py`
- Modify: `scripts/render_casebook.py`
- Create: `templates/magazine.html`
- Create: `templates/magazine.css`
- Create: `requirements-publisher.txt`

**Interfaces:**
- Produces `render_issue(issue_dir, output_pdf, template_root) -> RenderResult` and CLI flags `--issue-dir`, `--output`, `--template-root`.

- [ ] **Step 1: Write a failing integration test that renders a synthetic four-page issue and asserts four A4 pages.**
- [ ] **Step 2: Run it and observe the missing renderer failure.**
- [ ] **Step 3: Add the trusted HTML shell and initial A4 stylesheet.**
- [ ] **Step 4: Implement WeasyPrint rendering and `pdfinfo` page-count verification.**
- [ ] **Step 5: Add a failing overflow test where one declared page produces two PDF pages.**
- [ ] **Step 6: Fail closed when rendered page count differs from declared page count.**
- [ ] **Step 7: Run the renderer test module and inspect rendered PNGs from the synthetic fixture.**
- [ ] **Step 8: Commit `feat: add deterministic Casebook renderer`.**

### Task 3: Render Publication State Machine

**Files:**
- Create: `tests/test_publish_casebook_render.py`
- Create: `scripts/publish_casebook_render.py`

**Interfaces:**
- Produces `validate_publication_branch(branch, issue_id)`, `render_rendered_issue_yml(existing, pdf_meta, preview_meta, renderer_version)`, `publish_render(repo_root, issue_dir, branch, tooling_root) -> PublicationResult`.
- Consumes `render_issue` and `casebook_finalizer.validate_pdf`.

- [ ] **Step 1: Write failing tests for branch/issue mismatch and `draft -> rendered` metadata.**
- [ ] **Step 2: Run the focused tests and observe failures.**
- [ ] **Step 3: Implement branch validation and controlled YAML mutation.**
- [ ] **Step 4: Write failing tests proving catalog status remains draft and `.handoff/` is removed only after success.**
- [ ] **Step 5: Implement temporary render, preview generation, validation, atomic replacement, hashes, and idempotency.**
- [ ] **Step 6: Run all publisher-render tests.**
- [ ] **Step 7: Commit `feat: persist mechanically validated rendered issues`.**

### Task 4: Scheduled Branch Selection and Workflow

**Files:**
- Create: `tests/test_select_casebook_publication.py`
- Create: `scripts/select_casebook_publication.py`
- Create: `.github/workflows/casebook-publisher.yml`
- Create: `.github/workflows/casebook-publisher-ci.yml`

**Interfaces:**
- Produces CLI output of one target branch or `NOOP`.
- Workflow accepts optional `target_branch` and schedules Thursday 00:00 UTC.

- [ ] **Step 1: Write failing tests for selecting the highest unfinished issue and skipping published branches.**
- [ ] **Step 2: Implement pure selection logic over branch/status records.**
- [ ] **Step 3: Add CLI support for GitHub API branch enumeration with strict branch-name validation.**
- [ ] **Step 4: Add renderer workflow using separate trusted tooling/publication checkouts and a path-scope commit guard.**
- [ ] **Step 5: Add CI workflow running all unit tests and rendering ISSUE-006 as the full integration fixture.**
- [ ] **Step 6: Commit `ci: render Casebook issues deterministically`.**

### Task 5: Normalize Contracts and Scheduled Task Responsibilities

**Files:**
- Modify: `schemas/issue.schema.json`
- Modify: `AGENTS.md`
- Modify: `casebook.yml`
- Modify: `README.md`
- Modify: `docs/validation-standard.md`
- Modify: `docs/casebook-finalizer.md`
- Modify: `templates/magazine-style.md`
- Modify: `skills/casebook-publisher/SKILL.md`

- [ ] **Step 1: Extend schema status enum to include `rendered`.**
- [ ] **Step 2: Document deterministic rendering as the only normal publication path.**
- [ ] **Step 3: Move Finalizer/blob/rescue instructions under an explicit legacy-recovery section.**
- [ ] **Step 4: Record Thursday 00:15 research, 04:00 render, and 05:00 review schedule.**
- [ ] **Step 5: Rewrite publisher skill to inspect `draft`/`rendered`/`published` states and never generate or transport binaries.**
- [ ] **Step 6: Commit `docs: simplify Casebook publication contract`.**

### Task 6: CI, Review, and Infrastructure Merge

**Files:**
- All files from Tasks 1-5.

- [ ] **Step 1: Open a draft infrastructure PR from `fix/deterministic-casebook-publisher` to `main`.**
- [ ] **Step 2: Inspect CI jobs and logs; fix every failing test or integration gate.**
- [ ] **Step 3: Render and inspect the ISSUE-006 integration artifact.**
- [ ] **Step 4: Mark the infrastructure PR ready and merge it to `main` after all checks pass.**
- [ ] **Step 5: Verify `main` contains renderer/workflow/docs and no publication data changed.**

### Task 7: Recover ISSUE-007 and Reconfigure ChatGPT Tasks

**Files:**
- Publication branch: `publish/issue-007-2026-08-19`
- ChatGPT automations: `Casebook Research`, `Casebook Publisher`

- [ ] **Step 1: Trigger the new renderer for ISSUE-007.**
- [ ] **Step 2: Verify four A4 pages, searchable text, live links, embedded fonts, SVG references, exact hashes/sizes, `status: rendered`, and no `.handoff/`.**
- [ ] **Step 3: Render every page to images and visually inspect the exact branch PDF.**
- [ ] **Step 4: If visual review passes, update ISSUE-007 and catalog state to `published` while leaving PR #16 open and draft/supervised.**
- [ ] **Step 5: Update PR #16 description with the final artifact metadata and validation state.**
- [ ] **Step 6: Rewrite the 05:00 publisher task as review/delivery only and enable Casebook task notifications.**
- [ ] **Step 7: Verify the next research run cannot allocate ISSUE-008 until ISSUE-007 is merged, then deliver ISSUE-007 to the user for approval.**

## Verification Gate

Completion requires all unit tests green, ISSUE-006 integration rendering green, infrastructure merged to `main`, ISSUE-007 rendered and visually approved, PR #16 still supervised/unmerged, both scheduled-task prompts aligned with the new state machine, and no normal-path documentation instructing ChatGPT to transport PDF/JPEG bytes.
