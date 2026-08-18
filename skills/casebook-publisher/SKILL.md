# Engineering Casebook Publisher

Use this skill for every scheduled or manual Casebook publication run.

## 1. Read before acting
Read `AGENTS.md`, `casebook.yml`, `docs/editorial-standard.md`, `docs/source-standard.md`, `docs/diagram-standard.md`, `docs/validation-standard.md`, catalogs, the last three issues, and relevant toolbox records.

## 2. Reserve publication identity
From merged `main`, determine next issue and case IDs. If an existing open publication branch for that issue exists, resume it; never allocate duplicate IDs.

## 3. Discover
Research roughly 10–15 real candidate cases. Reject duplicates, poorly sourced cases, speculative news-only accounts and sets with excessive disciplinary repetition.

## 4. Select five
Normal slots: Deep Dive; Site Problem; Detail/Product; Structural/Civil Engineering Win; Geotechnical/Site Engineering Win. At least one case should be readily transferable to ordinary building/site work.

## 5. Verify before writing
Open authoritative primary sources. Verify dates, geometry, numerical claims, mechanism, product identity and stated reasons for interventions. Record evidence gaps. Distinguish fact, author/investigator finding and engineering interpretation. Never infer missing technical details.

## 6. Build canonical knowledge
Create new case records and reuse existing sources/toolbox entities where appropriate. Add new products only when exact proprietary identity is documented. Add systems, interventions, failure modes and Notebook entries when they are genuinely reusable.

## 7. Build figures
Default to SVG technical illustrations. Deep Dive gets at least two meaningful figures; every other case gets at least one. Validate technical geometry against sources.

## 8. Compose issue
Generate the three-page magazine issue with visible source dossiers, Engineer's Notebook material, Thread, 60-Second Takeaway and archive recall. Aim for 2300–2900 words and the typography limits in `casebook.yml`.

## 9. Validate
Execute every blocking check in `docs/validation-standard.md`, including visual PDF inspection. If any blocking check fails, do not publish a partial package.

## 10. Publish
Create `publish/issue-###-YYYY-MM-DD`, commit the complete package atomically where possible, and open a PR to `main`. Issues 005–007 must never be auto-merged. Normal issue runs may not modify rules, schemas, templates or this skill.

## 11. Report
Return the finished PDF, five-case summary, new toolbox knowledge, evidence gaps and PR status. If publication failed, report the failed stage and leave `main` unchanged.
