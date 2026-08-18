import base64
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import scripts.casebook_finalizer as finalizer

from scripts.casebook_finalizer import (
    FinalizerError,
    finalize,
    load_and_validate_manifest,
    parse_issue_yml,
    reconstruct_artifact,
    render_issue_yml,
    validate_branch,
    validate_issue_references,
)


class FinalizerTests(unittest.TestCase):
    def write_manifest(self, root: pathlib.Path, manifest: dict) -> pathlib.Path:
        handoff = root / manifest["issue_dir"] / ".handoff"
        handoff.mkdir(parents=True)
        path = handoff / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def valid_manifest(self) -> dict:
        return {
            "schema_version": 1,
            "issue_id": "ISSUE-005",
            "issue_dir": "issues/ISSUE-005-nothing-is-secondary",
            "visual_inspection": {"passed": True, "page_count": 3},
            "artifacts": [
                {
                    "role": "pdf",
                    "output": "ISSUE-005-nothing-is-secondary.pdf",
                    "media_type": "application/pdf",
                    "byte_size": 10,
                    "sha256": "0" * 64,
                    "chunks": ["pdf.part001.b64"],
                },
                {
                    "role": "preview",
                    "output": "preview.jpg",
                    "media_type": "image/jpeg",
                    "byte_size": 10,
                    "sha256": "1" * 64,
                    "chunks": ["preview.part001.b64"],
                },
            ],
        }

    def test_valid_branch_matches_issue(self):
        validate_branch("publish/issue-005-2026-08-18", "ISSUE-005")

    def test_branch_issue_mismatch_is_rejected(self):
        with self.assertRaises(FinalizerError):
            validate_branch("publish/issue-006-2026-08-18", "ISSUE-005")

    def test_manifest_rejects_unknown_top_level_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["command"] = "rm -rf /"
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_manifest_rejects_traversal_in_issue_dir(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["issue_dir"] = "issues/ISSUE-005-../../escape"
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_manifest_rejects_chunk_path_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["artifacts"][0]["chunks"] = ["../pdf.part001.b64"]
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

class ManifestBoundaryTests(FinalizerTests):
    def test_schema_version_float_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["schema_version"] = 1.0
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_visual_page_count_float_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["visual_inspection"]["page_count"] = 3.0
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_uppercase_sha256_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["artifacts"][0]["sha256"] = "A" * 64
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")

    def test_oversize_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            manifest = self.valid_manifest()
            manifest["artifacts"][0]["byte_size"] = 20 * 1024 * 1024 + 1
            path = self.write_manifest(root, manifest)
            with self.assertRaises(FinalizerError):
                load_and_validate_manifest(root, path, "publish/issue-005-2026-08-18")


class ReconstructionTests(unittest.TestCase):
    def artifact_for(self, role, output, media_type, raw, chunks):
        return {
            "role": role,
            "output": output,
            "media_type": media_type,
            "byte_size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "chunks": chunks,
        }

    def write_chunks(self, issue_dir, names, encoded):
        handoff = issue_dir / ".handoff"
        handoff.mkdir(parents=True, exist_ok=True)
        cut = len(encoded) // len(names)
        start = 0
        for index, name in enumerate(names):
            end = len(encoded) if index == len(names) - 1 else start + cut
            (handoff / name).write_text(encoded[start:end], encoding="ascii")
            start = end

    def test_reconstructs_pdf_from_multiple_chunks(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"%PDF-1.7\nsynthetic-payload\n%%EOF"
            encoded = base64.b64encode(raw).decode("ascii")
            names = ["pdf.part001.b64", "pdf.part002.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("pdf", "issue.pdf", "application/pdf", raw, names)
            self.assertEqual(reconstruct_artifact(issue_dir, artifact), raw)

    def test_reconstructs_jpeg_with_magic_and_trailer(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"\xff\xd8\xffpayload\xff\xd9"
            encoded = base64.b64encode(raw).decode("ascii")
            names = ["preview.part001.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("preview", "preview.jpg", "image/jpeg", raw, names)
            self.assertEqual(reconstruct_artifact(issue_dir, artifact), raw)

    def test_reconstruction_rejects_base64_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"%PDF-1.7\nabc\n%%EOF"
            encoded = base64.b64encode(raw).decode("ascii")[:-1] + "!"
            names = ["pdf.part001.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("pdf", "issue.pdf", "application/pdf", raw, names)
            with self.assertRaises(FinalizerError):
                reconstruct_artifact(issue_dir, artifact)

    def test_reconstruction_rejects_sha_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"%PDF-1.7\nabc\n%%EOF"
            encoded = base64.b64encode(raw).decode("ascii")
            names = ["pdf.part001.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("pdf", "issue.pdf", "application/pdf", raw, names)
            artifact["sha256"] = "0" * 64
            with self.assertRaises(FinalizerError):
                reconstruct_artifact(issue_dir, artifact)

    def test_reconstruction_rejects_wrong_pdf_magic(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"NOTPDF-data"
            encoded = base64.b64encode(raw).decode("ascii")
            names = ["pdf.part001.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("pdf", "issue.pdf", "application/pdf", raw, names)
            with self.assertRaises(FinalizerError):
                reconstruct_artifact(issue_dir, artifact)

    def test_reconstruction_rejects_wrong_jpeg_trailer(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            raw = b"\xff\xd8\xffpayload-no-eoi"
            encoded = base64.b64encode(raw).decode("ascii")
            names = ["preview.part001.b64"]
            self.write_chunks(issue_dir, names, encoded)
            artifact = self.artifact_for("preview", "preview.jpg", "image/jpeg", raw, names)
            with self.assertRaises(FinalizerError):
                reconstruct_artifact(issue_dir, artifact)


class IssueYmlMutationTests(unittest.TestCase):
    def fixture(self):
        return """schema_version: 1\nid: ISSUE-005\nnumber: 5\ntitle: Nothing Is Secondary\npublication_date: 2026-08-18\nrevision: 1\nstatus: draft\npage_count: 3\noriginal_format: magazine_v3_diagnostic\ndiagnostic: true\nslots:\n  - {role: deep_dive, case_id: CASE-018}\n  - {role: site_problem, case_id: CASE-019}\nmarkdown: issue.md\nsnapshots:\n  cases: snapshots/cases.md\n  sources: snapshots/sources.yml\nassets:\n  - assets/a.svg\nnote: Checkpoint F generated a valid local PDF and preview, but binary upload failed.\n"""

    def artifacts(self):
        return {
            "pdf": {"output": "ISSUE-005-nothing-is-secondary.pdf", "sha256": "a" * 64, "byte_size": 81092},
            "preview": {"output": "preview.jpg", "sha256": "b" * 64, "byte_size": 29286},
        }

    def test_issue_yml_finalization_changes_only_controlled_metadata(self):
        original = self.fixture()
        updated = render_issue_yml(original, self.artifacts())
        self.assertIn("status: published\n", updated)
        self.assertIn("original_format: magazine_v3\n", updated)
        self.assertIn("diagnostic: false\n", updated)
        self.assertIn("note: Binary artifacts finalized and mechanically validated by GitHub Actions.\n", updated)
        self.assertIn("pdf:\n  path: ISSUE-005-nothing-is-secondary.pdf\n  sha256: " + "a" * 64 + "\n  byte_size: 81092\n", updated)
        self.assertIn("preview:\n  path: preview.jpg\n  sha256: " + "b" * 64 + "\n  byte_size: 29286\n", updated)
        preserved = "slots:\n  - {role: deep_dive, case_id: CASE-018}\n  - {role: site_problem, case_id: CASE-019}\nmarkdown: issue.md\nsnapshots:\n  cases: snapshots/cases.md\n  sources: snapshots/sources.yml\nassets:\n  - assets/a.svg\n"
        self.assertIn(preserved, updated)

    def test_issue_yml_finalization_is_idempotent(self):
        once = render_issue_yml(self.fixture(), self.artifacts())
        twice = render_issue_yml(once, self.artifacts())
        self.assertEqual(once, twice)


class IssueReferenceTests(unittest.TestCase):
    def issue_text(self):
        return """schema_version: 1\nid: ISSUE-005\npage_count: 3\nslots:\n  - {role: deep_dive, case_id: CASE-018}\n  - {role: site_problem, case_id: CASE-019}\n  - {role: detail_product, case_id: CASE-020}\n  - {role: engineering_win_structural, case_id: CASE-021}\n  - {role: engineering_win_geotechnical, case_id: CASE-022}\nmarkdown: issue.md\nsnapshots:\n  cases: snapshots/cases.md\n  sources: snapshots/sources.yml\nassets:\n  - assets/a.svg\n  - assets/b.svg\n"""

    def test_parse_issue_yml_extracts_publication_references(self):
        meta = parse_issue_yml(self.issue_text())
        self.assertEqual(meta["page_count"], 3)
        self.assertEqual(meta["slot_count"], 5)
        self.assertEqual(meta["markdown"], "issue.md")
        self.assertEqual(meta["snapshots"], ["snapshots/cases.md", "snapshots/sources.yml"])
        self.assertEqual(meta["assets"], ["assets/a.svg", "assets/b.svg"])
        self.assertIsNone(meta["page_count_override_reason"])

    def test_missing_referenced_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            issue_dir = pathlib.Path(td)
            (issue_dir / "snapshots").mkdir()
            (issue_dir / "assets").mkdir()
            (issue_dir / "issue.md").write_text("x", encoding="utf-8")
            (issue_dir / "snapshots/cases.md").write_text("x", encoding="utf-8")
            (issue_dir / "snapshots/sources.yml").write_text("x", encoding="utf-8")
            (issue_dir / "assets/a.svg").write_text("<svg/>", encoding="utf-8")
            meta = parse_issue_yml(self.issue_text())
            with self.assertRaises(FinalizerError):
                validate_issue_references(issue_dir, meta)

    def test_traversal_in_referenced_path_is_rejected(self):
        text = self.issue_text().replace("markdown: issue.md", "markdown: ../escape.md")
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FinalizerError):
                validate_issue_references(pathlib.Path(td), parse_issue_yml(text))


class FinalizeFilesystemTests(FinalizerTests):
    ISSUE_YML = """schema_version: 1\nid: ISSUE-005\nnumber: 5\ntitle: Nothing Is Secondary\nstatus: draft\npage_count: 3\noriginal_format: magazine_v3_diagnostic\ndiagnostic: true\nslots:\n  - {role: deep_dive, case_id: CASE-018}\n  - {role: site_problem, case_id: CASE-019}\n  - {role: detail_product, case_id: CASE-020}\n  - {role: engineering_win_structural, case_id: CASE-021}\n  - {role: engineering_win_geotechnical, case_id: CASE-022}\nmarkdown: issue.md\nsnapshots:\n  cases: snapshots/cases.md\n  sources: snapshots/sources.yml\nassets:\n  - assets/a.svg\nnote: Checkpoint F binary upload failed.\n"""

    def setup_repo(self, root: pathlib.Path):
        issue_dir = root / "issues/ISSUE-005-nothing-is-secondary"
        handoff = issue_dir / ".handoff"
        (issue_dir / "snapshots").mkdir(parents=True)
        (issue_dir / "assets").mkdir()
        handoff.mkdir()
        (issue_dir / "issue.md").write_text("draft", encoding="utf-8")
        (issue_dir / "snapshots/cases.md").write_text("cases", encoding="utf-8")
        (issue_dir / "snapshots/sources.yml").write_text("sources", encoding="utf-8")
        (issue_dir / "assets/a.svg").write_text("<svg/>", encoding="utf-8")
        (issue_dir / "issue.yml").write_text(self.ISSUE_YML, encoding="utf-8")
        pdf_raw = b"%PDF-1.7\nsynthetic\n%%EOF"
        jpg_raw = b"\xff\xd8\xffsynthetic\xff\xd9"
        pdf_b64 = base64.b64encode(pdf_raw).decode("ascii")
        jpg_b64 = base64.b64encode(jpg_raw).decode("ascii")
        (handoff / "pdf.part001.b64").write_text(pdf_b64, encoding="ascii")
        (handoff / "preview.part001.b64").write_text(jpg_b64, encoding="ascii")
        manifest = self.valid_manifest()
        manifest["artifacts"][0].update({
            "byte_size": len(pdf_raw),
            "sha256": hashlib.sha256(pdf_raw).hexdigest(),
        })
        manifest["artifacts"][1].update({
            "byte_size": len(jpg_raw),
            "sha256": hashlib.sha256(jpg_raw).hexdigest(),
        })
        manifest_path = handoff / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return issue_dir, manifest_path, pdf_raw, jpg_raw

    def test_validation_failure_leaves_existing_outputs_and_handoff_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            issue_dir, manifest_path, _, _ = self.setup_repo(root)
            old_pdf = b"old-pdf"
            old_jpg = b"old-jpg"
            (issue_dir / "ISSUE-005-nothing-is-secondary.pdf").write_bytes(old_pdf)
            (issue_dir / "preview.jpg").write_bytes(old_jpg)
            original_yml = (issue_dir / "issue.yml").read_text(encoding="utf-8")
            with mock.patch("scripts.casebook_finalizer.validate_pdf", side_effect=FinalizerError("synthetic validation failure")):
                with self.assertRaises(FinalizerError):
                    finalize(root, manifest_path, "publish/issue-005-2026-08-18")
            self.assertEqual((issue_dir / "ISSUE-005-nothing-is-secondary.pdf").read_bytes(), old_pdf)
            self.assertEqual((issue_dir / "preview.jpg").read_bytes(), old_jpg)
            self.assertEqual((issue_dir / "issue.yml").read_text(encoding="utf-8"), original_yml)
            self.assertTrue(manifest_path.exists())
            self.assertEqual(list(issue_dir.glob(".finalizer-*")), [])

    def test_successful_finalize_replaces_outputs_updates_yml_and_removes_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            issue_dir, manifest_path, pdf_raw, jpg_raw = self.setup_repo(root)
            with mock.patch("scripts.casebook_finalizer.validate_pdf", return_value=None):
                issue_id = finalize(root, manifest_path, "publish/issue-005-2026-08-18")
            self.assertEqual(issue_id, "ISSUE-005")
            self.assertEqual((issue_dir / "ISSUE-005-nothing-is-secondary.pdf").read_bytes(), pdf_raw)
            self.assertEqual((issue_dir / "preview.jpg").read_bytes(), jpg_raw)
            updated = (issue_dir / "issue.yml").read_text(encoding="utf-8")
            self.assertIn("status: published", updated)
            self.assertIn("pdf:", updated)
            self.assertIn("preview:", updated)
            self.assertFalse((issue_dir / ".handoff").exists())


class PopplerParsingTests(unittest.TestCase):
    def test_parse_page_size_accepts_numbered_pdfinfo_label(self):
        output = "Pages:           3\nPage    1 size:  595.276 x 841.89 pts (A4)\n"
        self.assertEqual(finalizer._parse_page_size(output), (595.276, 841.89))
