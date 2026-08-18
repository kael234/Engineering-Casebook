# Architecture

## Principle
Git is the durable knowledge store. Markdown/YAML/SVG records are authoritative. PDFs and thumbnails are publication outputs. A future local app may build a disposable SQLite index from this repository, but SQLite must never become the only copy of knowledge.

## Data flow
`research -> verify -> canonical case/toolbox records -> issue snapshot -> SVG figures -> PDF -> validation -> publication branch -> PR -> main`

## Boundaries
- `cases/`: canonical case records and case-owned figures.
- `issues/`: frozen publication packages.
- `library/`: reusable sources, products, systems, interventions, failure modes, and Engineer's Notebook entries.
- `catalog/`: generated compact indexes for retrieval.
- `schemas/`: structural contracts.
- `templates/`: publication and figure conventions.
- `skills/`: publisher operating instructions.

## Publication policy
Issues 005–007 require manual PR merge. Later automation may auto-merge only after explicit approval and only after all repository validation passes.
