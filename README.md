# Engineering Casebook

Canonical source of truth for a continuously growing civil/structural engineering case-study library and its weekly magazine publication.

The repository stores structured cases, verified sources, reusable toolbox knowledge, technical figures and frozen issue packages. The PDF is a generated user-facing output; the repository is the durable knowledge layer.

## Publication model

Each normal issue contains five cases:
1. Deep Dive
2. Site Problem
3. Detail / Product / Material
4. Engineering Win — structural/civil
5. Engineering Win — geotechnical/site

Issues are three or four A4 pages. Cases are canonical knowledge records and may later appear in synthesis issues or the future app.

The normal weekly flow is deliberately split:

1. **Thursday 00:15 (Seychelles):** ChatGPT prepares the verified editorial package on a `publish/issue-*` branch.
2. **Thursday 04:00:** GitHub Actions renders the committed Markdown/SVG package, mechanically validates the PDF, commits the PDF/preview, and records `status: rendered`.
3. **Thursday 05:00:** ChatGPT inspects the exact rendered pages, promotes a passing issue to `published`, applies supervision/merge policy, and delivers the PDF.

PDF/JPEG handoff chunks are legacy recovery infrastructure, not the normal publication path.

See `AGENTS.md`, `skills/casebook-publisher/SKILL.md`, and `docs/validation-standard.md` before publishing or modifying Casebook data.
