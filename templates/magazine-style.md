# Engineering Casebook Magazine Style

`templates/magazine.html` and `templates/magazine.css` are the executable implementation of this standard. The renderer must use those trusted files from `main`; scheduled tasks do not recreate a layout engine from prose.

## Format
- A4 portrait.
- Three pages are preferred when comfortable. Four pages are normal when needed to preserve readability, figure scale and rhythm; record a non-empty `page_count_override_reason`.
- Committed `## PAGE N - ...` markers are authoritative page boundaries.
- Page 1: full-page Deep Dive.
- Page 2: Site Problem + Detail/Product case.
- Three-page issue: Page 3 contains both Engineering Wins plus Thread, 60-Second Takeaway and archive recall.
- Four-page issue: distribute wins and synthesis across Pages 3 and 4 without a thin overflow page.

## Visual character
Technical magazine, not corporate report: restrained warm-white page, dark navy/charcoal text, one warm accent, strong serif/sans hierarchy, useful diagrams and efficient breathing room.

Issue 004 remains the visual-rhythm reference. Do not use tiny archival reconstruction PDFs as the baseline when an original-quality issue is available.

## Typography
- Normal body target: 9.0-9.5 pt, roughly 1.15-1.25 line-height; never below 8.5 pt.
- Normal secondary target: 8.5-9 pt; never below 8 pt.
- Normal sources/captions target: 7.5-8 pt; never below 7 pt.
- Minimums are emergency floors, not layout targets.
- Source dossiers remain visibly legible.

## Hierarchy and modules
Preserve clear separation between case headings, body copy, figures, `YOU ARE THE ENGINEER`, Engineer's Notebook, evidence boundary and source dossiers. Thread, takeaway and archive recall form a readable closing synthesis, not microprint.

## Figures
Deep Dive has at least two meaningful figures; every other case at least one. Prefer context/elevation, load path, section, sequence, intervention, product detail, monitoring plot or option comparison. Figures teach mechanics and remain legible at normal page scale.

## Density
Target 2300-2900 useful words as guidance. Remove repetition before shrinking design. If a declared page overflows, the renderer fails rather than clipping or silently creating an extra page; editorial pagination must then be corrected on the source branch.

## Quality gate
GitHub Actions performs deterministic rendering and mechanical validation. The 05:00 publisher renders the exact PDF pages to images and performs the visual gate before publication approval.
