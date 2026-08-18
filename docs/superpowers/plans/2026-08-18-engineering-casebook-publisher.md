# Engineering Casebook Publisher Implementation Plan

> **For agentic workers:** Execute this plan task-by-task and verify each independently.

**Goal:** Bootstrap the durable Casebook schema, backfill Issues 001–004, prove one repository-aware publication run, then update the weekly ChatGPT task.

**Architecture:** Repository contracts live in `docs/`, `schemas/`, `templates/` and `skills/`. Knowledge lives in `cases/` and `library/`; frozen publications live in `issues/`; compact indexes live in `catalog/`.

**Spec:** `docs/superpowers/specs/2026-08-18-engineering-casebook-publisher-design.md`

## Tasks
- [x] 1. Create repository constitution, editorial/source/diagram/validation standards and stable identifier rules.
- [ ] 2. Add machine-readable schemas and publication templates.
- [ ] 3. Add publisher skill containing the complete scheduled-run state machine and failure rules.
- [ ] 4. Backfill Issues 001–004, CASE-001 through CASE-017, verified sources and core toolbox relations.
- [ ] 5. Generate compact catalogs and cross-case relations; verify sequential IDs and referential integrity.
- [ ] 6. Perform a manual Issue 005 repository-aware publication dry run on a `publish/issue-005-*` branch and open a PR without merging.
- [ ] 7. Update the existing Saturday 08:00 ChatGPT task to run the repository publisher contract.

## Verification gate
Before Tasks 6–7, fetch representative case, issue, source and catalog files from the branch and verify they conform to the repository standards. Issue 005 must not publish if the PDF or evidence checks fail.
