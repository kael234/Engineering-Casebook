# Engineering Casebook Publisher Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and verify each independently.

**Goal:** Bootstrap the durable Casebook schema, backfill Issues 001–004, prove the GitHub publication write path, then update the weekly ChatGPT task.

**Architecture:** Repository contracts live in `docs/`, `schemas/`, `templates/` and `skills/`. Knowledge lives in `cases/` and `library/`; frozen publications live in `issues/`; compact indexes live in `catalog/`.

**Spec:** `docs/superpowers/specs/2026-08-18-engineering-casebook-publisher-design.md`

## Tasks
- [x] 1. Create repository constitution, editorial/source/diagram/validation standards and stable identifier rules.
- [x] 2. Add machine-readable schemas and durable publication/presentation templates.
- [x] 3. Add publisher skill containing the complete scheduled-run state machine and failure rules.
- [x] 4. Backfill Issues 001–004, CASE-001 through CASE-017, verified sources and core toolbox relations.
- [x] 5. Generate compact catalogs and cross-case relations; verify sequential IDs and representative referential integrity by repository read-back.
- [x] 6. Prove the connected GitHub write path using the bootstrap branch: create branch, multi-file/tree commits, updates, read-back and pull request. The first real repository-aware publication will be supervised ISSUE-005 rather than a disposable fake issue.
- [ ] 7. Merge the validated bootstrap PR and update the existing Saturday 08:00 ChatGPT task to run the repository publisher contract.

## Verification gate
Before Task 7, fetch representative publisher, case, issue, source/catalog and validation records from the branch and verify that PR #1 is mergeable. ISSUE-005 must not publish if the PDF or evidence checks fail.
