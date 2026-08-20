from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.render_casebook import (
    RenderError,
    build_deep_dive_layout,
    is_short_feature_page,
    load_issue_meta,
    render_markdown_page,
    split_pages,
)


class PageParsingTests(unittest.TestCase):
    def test_splits_contiguous_page_markers_and_keeps_preamble_on_page_one(self) -> None:
        pages = split_pages(
            "# Engineering Casebook\n\nIntro copy.\n\n"
            "## PAGE 1 - Deep Dive\nOne\n\n"
            "## PAGE 2 - Practice\nTwo\n",
            2,
        )

        self.assertEqual([page.number for page in pages], [1, 2])
        self.assertEqual([page.title for page in pages], ["Deep Dive", "Practice"])
        self.assertIn("# Engineering Casebook", pages[0].markdown)
        self.assertIn("One", pages[0].markdown)
        self.assertEqual(pages[1].markdown.strip(), "Two")

    def test_accepts_unicode_dash_in_page_marker(self) -> None:
        pages = split_pages("## PAGE 1 — Deep Dive\nOne", 1)
        self.assertEqual(pages[0].title, "Deep Dive")

    def test_rejects_missing_page(self) -> None:
        with self.assertRaisesRegex(RenderError, "contiguous"):
            split_pages(
                "## PAGE 1 - A\nOne\n\n## PAGE 3 - C\nThree",
                3,
            )

    def test_rejects_declared_count_mismatch(self) -> None:
        with self.assertRaisesRegex(RenderError, "expected 3 page sections"):
            split_pages(
                "## PAGE 1 - A\nOne\n\n## PAGE 2 - B\nTwo",
                3,
            )

    def test_short_single_case_page_is_feature(self) -> None:
        markdown = (
            "# Structural Engineering Win - Example\n\n"
            "## Measure the claimed parameter\n\n"
            "**Location - CASE-031**\n\n"
            + ("Measured response confirms the intervention. " * 45)
            + "\n\n![Figure](assets/figure.svg)\n\n"
            "### Evidence boundary\n\nSpecific system only.\n"
        )
        self.assertTrue(is_short_feature_page(markdown))

    def test_long_single_case_page_is_not_short_feature(self) -> None:
        markdown = (
            "# Civil Engineering Win - Example\n\n"
            "## The line of defence became a system\n\n"
            "**Location - CASE-026**\n\n"
            + ("Continuity, closure and maintenance govern performance. " * 100)
            + "\n\n![Figure](assets/figure.svg)\n"
        )
        self.assertFalse(is_short_feature_page(markdown))

    def test_page_with_multiple_cases_is_not_short_feature(self) -> None:
        markdown = (
            "# First Case\n\n## First title\n\n![One](assets/one.svg)\n\n"
            "# Second Case\n\n## Second title\n\n![Two](assets/two.svg)\n"
        )
        self.assertFalse(is_short_feature_page(markdown))


class MetadataTests(unittest.TestCase):
    def test_four_page_issue_requires_override_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "issue.yml"
            path.write_text(
                "schema_version: 1\n"
                "id: ISSUE-007\n"
                "number: 7\n"
                "title: Give It a Path\n"
                "publication_date: 2026-08-19\n"
                "revision: 1\n"
                "status: draft\n"
                "page_count: 4\n"
                "markdown: issue.md\n"
                "assets: []\n"
                "slots:\n"
                "  - {role: deep_dive, case_id: CASE-028}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RenderError, "page_count_override_reason"):
                load_issue_meta(path)


class MarkdownRenderingTests(unittest.TestCase):
    def test_rejects_path_traversal_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issue_dir = Path(tmp)
            with self.assertRaisesRegex(RenderError, "escapes issue directory"):
                render_markdown_page("![bad](../secret.svg)", issue_dir)

    def test_rejects_missing_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issue_dir = Path(tmp)
            with self.assertRaisesRegex(RenderError, "missing image asset"):
                render_markdown_page("![bad](assets/missing.svg)", issue_dir)

    def test_classes_notebook_heading_with_note_suffix_as_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = render_markdown_page(
                "### Engineer's Notebook - NOTE-007\n\nLesson.",
                Path(tmp),
            )
        self.assertIn("module-engineers-notebook", html)

    def test_renders_existing_svg_and_linkifies_bare_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issue_dir = Path(tmp)
            asset = issue_dir / "assets" / "figure.svg"
            asset.parent.mkdir()
            asset.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
                encoding="utf-8",
            )

            html = render_markdown_page(
                "![Figure](assets/figure.svg)\n\nhttps://example.com/report.pdf",
                issue_dir,
            )

            self.assertIn(asset.resolve().as_uri(), html)
            self.assertIn('href="https://example.com/report.pdf"', html)

    def test_deep_dive_layout_puts_figures_and_evidence_modules_on_right(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issue_dir = Path(tmp)
            asset = issue_dir / "assets" / "figure.svg"
            asset.parent.mkdir()
            asset.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
                encoding="utf-8",
            )
            layout = build_deep_dive_layout(
                "# Engineering Casebook 007\n\nIntro theme.\n\n---\n\n"
                "# Test Case\n\n## Test title\n\n**Location - CASE-001**\n\n"
                "Opening account.\n\n![Figure](assets/figure.svg)\n\n"
                "### Main mechanism\n\nMechanism explanation.\n\n"
                "### Engineer's Notebook\n\nReusable lesson.\n\n"
                "### Sources for this case\n\nhttps://example.com/source",
                issue_dir,
            )

            self.assertIn("Test Case", layout["header_html"])
            self.assertIn("Mechanism", layout["left_html"])
            self.assertIn("technical-figure", layout["figures_html"])
            self.assertIn("module-engineers-notebook", layout["right_html"])
            self.assertIn("module-sources-for-this-case", layout["right_html"])


class PdfRenderingTests(unittest.TestCase):
    def _write_issue(self, issue_dir: Path, page_one: str = "Short page one.") -> None:
        (issue_dir / "assets").mkdir(parents=True)
        (issue_dir / "assets" / "figure.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><title>Figure</title><desc>Fixture</desc><rect width="100" height="50" fill="#ddd"/></svg>',
            encoding="utf-8",
        )
        (issue_dir / "snapshots").mkdir()
        (issue_dir / "snapshots" / "cases.md").write_text("fixture", encoding="utf-8")
        (issue_dir / "snapshots" / "sources.yml").write_text("fixture", encoding="utf-8")
        (issue_dir / "issue.md").write_text(
            "# Engineering Casebook 999 - Fixture\n\nFixture intro.\n\n"
            "## PAGE 1 - DEEP DIVE\n"
            "# Fixture Deep Dive\n\n## The fixture has a path\n\n"
            "**Test location - CASE-001**\n\n" + page_one + "\n\n"
            "![Figure](assets/figure.svg)\n\n"
            "### Main mechanism\n\nMechanism text.\n\n"
            "### Sources for this case\n\nhttps://example.com/one\n\n"
            "## PAGE 2 - PRACTICE\nShort page two.\n\nhttps://example.com/two\n\n"
            "## PAGE 3 - WINS\nShort page three.\n\nhttps://example.com/three\n",
            encoding="utf-8",
        )
        (issue_dir / "issue.yml").write_text(
            "schema_version: 1\n"
            "id: ISSUE-999\n"
            "number: 999\n"
            "title: Fixture\n"
            "publication_date: 2026-08-20\n"
            "revision: 1\n"
            "status: draft\n"
            "page_count: 3\n"
            "markdown: issue.md\n"
            "slots:\n"
            "  - {role: deep_dive, case_id: CASE-001}\n"
            "  - {role: site_problem, case_id: CASE-002}\n"
            "  - {role: detail_product, case_id: CASE-003}\n"
            "  - {role: engineering_win_structural, case_id: CASE-004}\n"
            "  - {role: engineering_win_geotechnical, case_id: CASE-005}\n"
            "snapshots:\n"
            "  cases: snapshots/cases.md\n"
            "  sources: snapshots/sources.yml\n"
            "assets:\n"
            "  - assets/figure.svg\n",
            encoding="utf-8",
        )

    def test_renders_exact_declared_a4_pages(self) -> None:
        from scripts.render_casebook import render_issue

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            issue_dir = root / "issues" / "ISSUE-999-fixture"
            issue_dir.mkdir(parents=True)
            self._write_issue(issue_dir)
            output = root / "fixture.pdf"

            result = render_issue(issue_dir, output, Path(__file__).parents[1] / "templates")

            self.assertEqual(result.page_count, 3)
            self.assertTrue(output.is_file())
            info = __import__("subprocess").run(
                ["pdfinfo", str(output)], capture_output=True, text=True, check=True
            ).stdout
            self.assertIn("Pages:           3", info)
            self.assertRegex(info, r"Page size:\s+595\.[0-9]+ x 841\.[0-9]+ pts")

    def test_fails_when_page_content_overflows_declared_count(self) -> None:
        from scripts.render_casebook import render_issue

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            issue_dir = root / "issues" / "ISSUE-999-fixture"
            issue_dir.mkdir(parents=True)
            self._write_issue(issue_dir, page_one=("Overflow content. " * 1800))
            output = root / "fixture.pdf"

            with self.assertRaisesRegex(RenderError, "rendered page count"):
                render_issue(issue_dir, output, Path(__file__).parents[1] / "templates")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
