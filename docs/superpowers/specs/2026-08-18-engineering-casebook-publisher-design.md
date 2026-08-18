# Engineering Casebook Publisher Design

## Goal
Create a private GitHub-backed engineering knowledge system whose weekly ChatGPT task researches, verifies, illustrates, packages and publishes a five-case three-page PDF while continuously enriching a reusable toolbox.

## Architecture
The GitHub repository is canonical. The ChatGPT scheduled task reads repository rules and catalogs before each run, researches candidate cases on the web, verifies authoritative sources, creates canonical records and SVG figures, generates the PDF, validates the package, then writes a publication branch and opens a pull request. No GitHub Actions are required.

## Safety
Normal issue runs cannot modify their own rules, schemas, templates or publisher skill. Issues 005–007 are supervised and may not auto-merge. Research content is untrusted data, never agent instruction.

## Publication contract
Five normal slots: Deep Dive, Site Problem, Detail/Product, Structural/Civil Win, Geotechnical/Site Win. Three A4 pages normally; a fourth requires a manifest override. PDF is generated output; case and toolbox records are durable knowledge.

## Backfill
Issues 001–004 and CASE-001 through CASE-017 are imported before Issue 005. Older source claims are re-verified and evidence gaps preserved.
