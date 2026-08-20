from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scripts.publish_casebook_render import (
    PublicationError,
    ArtifactMeta,
    publish_render,
    render_rendered_issue_yml,
    validate_publication_branch,
)


class BranchValidationTests(unittest.TestCase):
    def test_accepts_matching_publication_branch(self) -> None:
        validate_publication_branch("publish/issue-007-2026-08-20", "ISSUE-007")

    def test_rejects_branch_issue_mismatch(self) -> None:
        with self.assertRaisesRegex(PublicationError, "does not match"):
            validate_publication_branch("publish/issue-008-2026-08-20", "ISSUE-007")

    def test_rejects_non_publication_branch(self) -> None:
        with self.assertRaisesRegex(PublicationError, "invalid publication branch"):
            validate_publication_branch("main", "ISSUE-007")


class MetadataTransitionTests(unittest.TestCase):
    def test_transitions_draft_to_rendered_with_exact_artifact_metadata(self) -> None:
        existing = (
            "schema_version: 1\n"
            "id: ISSUE-007\n"
            "number: 7\n"
            "title: Give It a Path\n"
            "status: draft\n"
            "page_count: 4\n"
            "page_count_override_reason: Readability.\n"
            "markdown: issue.md\n"
            "slots: []\n"
            "assets: []\n"
        )
        pdf = ArtifactMeta("ISSUE-007-give-it-a-path.pdf", 1234, "a" * 64)
        preview = ArtifactMeta("preview.jpg", 567, "b" * 64)

        updated = render_rendered_issue_yml(existing, pdf, preview, "casebook-renderer/1")
        data = yaml.safe_load(updated)

        self.assertEqual(data["status"], "rendered")
        self.assertEqual(data["pdf"]["path"], pdf.path)
        self.assertEqual(data["pdf"]["byte_size"], 1234)
        self.assertEqual(data["pdf"]["sha256"], "a" * 64)
        self.assertEqual(data["preview"]["path"], "preview.jpg")
        self.assertEqual(data["render"]["renderer"], "casebook-renderer/1")
        self.assertIn("mechanically validated", data["note"])


class PublishRenderTests(unittest.TestCase):
    def _write_issue(self, repo: Path) -> tuple[Path, str]:
        issue_rel = "issues/ISSUE-099-test-issue"
        issue = repo / issue_rel
        (issue / "assets").mkdir(parents=True)
        (issue / "snapshots").mkdir()
        (issue / "assets" / "figure.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50">'
            '<title>Fixture</title><desc>Fixture</desc><rect width="100" height="50" fill="#ddd"/></svg>',
            encoding="utf-8",
        )
        (issue / "snapshots" / "cases.md").write_text("fixture", encoding="utf-8")
        (issue / "snapshots" / "sources.yml").write_text("fixture", encoding="utf-8")
        (issue / "issue.md").write_text(
            "# Engineering Casebook 099\n\n"
            "## PAGE 1 - Deep Dive\nShort page.\n\n![Figure](assets/figure.svg)\n\nhttps://example.com/1\n\n"
            "## PAGE 2 - Practice\nShort page.\n\nhttps://example.com/2\n\n"
            "## PAGE 3 - Wins\nShort page.\n\nhttps://example.com/3\n",
            encoding="utf-8",
        )
        (issue / "issue.yml").write_text(
            "schema_version: 1\n"
            "id: ISSUE-099\n"
            "number: 99\n"
            "title: Test Issue\n"
            "publication_date: 2026-08-20\n"
            "revision: 1\n"
            "status: draft\n"
            "page_count: 3\n"
            "markdown: issue.md\n"
            "slots:\n"
            "  - {role: deep_dive, case_id: CASE-901}\n"
            "  - {role: site_problem, case_id: CASE-902}\n"
            "  - {role: detail_product, case_id: CASE-903}\n"
            "  - {role: engineering_win_structural, case_id: CASE-904}\n"
            "  - {role: engineering_win_geotechnical, case_id: CASE-905}\n"
            "snapshots:\n"
            "  cases: snapshots/cases.md\n"
            "  sources: snapshots/sources.yml\n"
            "assets:\n"
            "  - assets/figure.svg\n",
            encoding="utf-8",
        )
        (issue / ".handoff").mkdir()
        (issue / ".handoff" / "stale.txt").write_text("stale", encoding="utf-8")
        (repo / "catalog").mkdir()
        catalog = '{"schema_version":1,"issues":[{"id":"ISSUE-099","status":"draft"}]}'
        (repo / "catalog" / "issues.json").write_text(catalog, encoding="utf-8")
        return issue, catalog

    def test_success_persists_artifacts_marks_rendered_and_leaves_catalog_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            issue, original_catalog = self._write_issue(repo)
            tooling = Path(__file__).parents[1]

            with mock.patch("scripts.publish_casebook_render._mechanical_validate_pdf"):
                result = publish_render(
                    repo,
                    "issues/ISSUE-099-test-issue",
                    "publish/issue-099-2026-08-20",
                    tooling,
                )

            data = yaml.safe_load((issue / "issue.yml").read_text(encoding="utf-8"))
            self.assertTrue(result.changed)
            self.assertEqual(data["status"], "rendered")
            self.assertFalse((issue / ".handoff").exists())
            self.assertTrue((issue / data["pdf"]["path"]).is_file())
            self.assertTrue((issue / data["preview"]["path"]).is_file())
            self.assertEqual(
                (repo / "catalog" / "issues.json").read_text(encoding="utf-8"),
                original_catalog,
            )
            pdf_bytes = (issue / data["pdf"]["path"]).read_bytes()
            self.assertEqual(data["pdf"]["sha256"], hashlib.sha256(pdf_bytes).hexdigest())

    def test_validation_failure_leaves_issue_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            issue, _ = self._write_issue(repo)
            tooling = Path(__file__).parents[1]
            original_yml = (issue / "issue.yml").read_text(encoding="utf-8")

            with mock.patch(
                "scripts.publish_casebook_render._mechanical_validate_pdf",
                side_effect=PublicationError("mechanical failure"),
            ):
                with self.assertRaisesRegex(PublicationError, "mechanical failure"):
                    publish_render(
                        repo,
                        "issues/ISSUE-099-test-issue",
                        "publish/issue-099-2026-08-20",
                        tooling,
                    )

            self.assertEqual((issue / "issue.yml").read_text(encoding="utf-8"), original_yml)
            self.assertTrue((issue / ".handoff" / "stale.txt").is_file())
            self.assertFalse((issue / "ISSUE-099-test-issue.pdf").exists())
            self.assertFalse((issue / "preview.jpg").exists())

    def test_symlinked_handoff_is_rejected_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            issue, _ = self._write_issue(repo)
            tooling = Path(__file__).parents[1]
            original_yml = (issue / "issue.yml").read_text(encoding="utf-8")
            handoff = issue / ".handoff"
            for child in handoff.iterdir():
                child.unlink()
            handoff.rmdir()
            target = repo / "outside-handoff"
            target.mkdir()
            handoff.symlink_to(target, target_is_directory=True)

            with mock.patch(
                "scripts.publish_casebook_render.render_issue",
                side_effect=AssertionError("renderer should not run"),
            ):
                with self.assertRaisesRegex(PublicationError, "symlinked .handoff"):
                    publish_render(
                        repo,
                        "issues/ISSUE-099-test-issue",
                        "publish/issue-099-2026-08-20",
                        tooling,
                    )

            self.assertEqual((issue / "issue.yml").read_text(encoding="utf-8"), original_yml)
            self.assertTrue(handoff.is_symlink())

    def test_persistence_failure_rolls_back_artifacts_metadata_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            issue, _ = self._write_issue(repo)
            tooling = Path(__file__).parents[1]
            original_yml = (issue / "issue.yml").read_text(encoding="utf-8")
            real_replace = __import__("os").replace

            def fail_metadata_replace(src, dst):
                if Path(dst) == issue / "issue.yml":
                    raise OSError("simulated metadata persistence failure")
                return real_replace(src, dst)

            with mock.patch("scripts.publish_casebook_render._mechanical_validate_pdf"), mock.patch(
                "scripts.publish_casebook_render.os.replace",
                side_effect=fail_metadata_replace,
            ):
                with self.assertRaisesRegex(PublicationError, "persistence failed"):
                    publish_render(
                        repo,
                        "issues/ISSUE-099-test-issue",
                        "publish/issue-099-2026-08-20",
                        tooling,
                    )

            self.assertEqual((issue / "issue.yml").read_text(encoding="utf-8"), original_yml)
            self.assertTrue((issue / ".handoff" / "stale.txt").is_file())
            self.assertFalse((issue / "ISSUE-099-test-issue.pdf").exists())
            self.assertFalse((issue / "preview.jpg").exists())

    def test_matching_rendered_artifacts_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            issue, _ = self._write_issue(repo)
            tooling = Path(__file__).parents[1]
            with mock.patch("scripts.publish_casebook_render._mechanical_validate_pdf"):
                first = publish_render(
                    repo,
                    "issues/ISSUE-099-test-issue",
                    "publish/issue-099-2026-08-20",
                    tooling,
                )

            with mock.patch(
                "scripts.publish_casebook_render.render_issue",
                side_effect=AssertionError("renderer should not run"),
            ):
                second = publish_render(
                    repo,
                    "issues/ISSUE-099-test-issue",
                    "publish/issue-099-2026-08-20",
                    tooling,
                )

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(first.pdf.sha256, second.pdf.sha256)


if __name__ == "__main__":
    unittest.main()
