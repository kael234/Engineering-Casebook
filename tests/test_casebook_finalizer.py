import json
import pathlib
import tempfile
import unittest

from scripts.casebook_finalizer import (
    FinalizerError,
    load_and_validate_manifest,
    validate_branch,
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
