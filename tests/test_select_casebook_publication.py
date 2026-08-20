from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.select_casebook_publication import (
    BranchRecord,
    SelectionError,
    discover_records,
    select_named_target,
    select_target,
    validate_target_branch,
)


class SelectionLogicTests(unittest.TestCase):
    def test_selects_highest_unfinished_issue(self) -> None:
        records = [
            BranchRecord("publish/issue-006-2026-08-19", "ISSUE-006", "published", "issues/ISSUE-006-six"),
            BranchRecord("publish/issue-007-2026-08-19", "ISSUE-007", "rendered", "issues/ISSUE-007-seven"),
            BranchRecord("publish/issue-008-2026-08-20", "ISSUE-008", "draft", "issues/ISSUE-008-eight"),
        ]
        self.assertEqual(select_target(records).branch, "publish/issue-008-2026-08-20")

    def test_rendered_highest_issue_blocks_lower_draft(self) -> None:
        records = [
            BranchRecord("publish/issue-007-2026-08-19", "ISSUE-007", "draft", "issues/ISSUE-007-seven"),
            BranchRecord("publish/issue-008-2026-08-20", "ISSUE-008", "rendered", "issues/ISSUE-008-eight"),
        ]
        self.assertEqual(select_target(records).issue_id, "ISSUE-008")

    def test_returns_none_when_all_publication_branches_are_published(self) -> None:
        records = [
            BranchRecord("publish/issue-006-2026-08-19", "ISSUE-006", "published", "issues/ISSUE-006-six"),
            BranchRecord("publish/issue-007-2026-08-19", "ISSUE-007", "published", "issues/ISSUE-007-seven"),
        ]
        self.assertIsNone(select_target(records))

    def test_selects_named_target_without_allocating_past_it(self) -> None:
        records = [
            BranchRecord("publish/issue-007-2026-08-19", "ISSUE-007", "rendered", "issues/ISSUE-007-seven"),
            BranchRecord("publish/issue-008-2026-08-20", "ISSUE-008", "draft", "issues/ISSUE-008-eight"),
        ]
        self.assertEqual(
            select_named_target(records, "publish/issue-007-2026-08-19").issue_id,
            "ISSUE-007",
        )

    def test_rejects_unknown_named_target(self) -> None:
        with self.assertRaisesRegex(SelectionError, "was not found"):
            select_named_target([], "publish/issue-007-2026-08-19")

    def test_rejects_duplicate_branch_issue_numbers(self) -> None:
        records = [
            BranchRecord("publish/issue-007-2026-08-19", "ISSUE-007", "draft", "issues/ISSUE-007-seven"),
            BranchRecord("publish/issue-007-2026-08-20", "ISSUE-007", "draft", "issues/ISSUE-007-seven-b"),
        ]
        with self.assertRaisesRegex(SelectionError, "duplicate publication branches"):
            select_target(records)


class ValidationTests(unittest.TestCase):
    def test_accepts_matching_target_branch(self) -> None:
        validate_target_branch("publish/issue-007-2026-08-19", "ISSUE-007")

    def test_rejects_mismatch(self) -> None:
        with self.assertRaisesRegex(SelectionError, "does not match"):
            validate_target_branch("publish/issue-008-2026-08-20", "ISSUE-007")


class DiscoveryTests(unittest.TestCase):
    def test_discovers_issue_metadata_from_remote_refs(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            issue = repo / "issues" / "ISSUE-007-seven"
            issue.mkdir(parents=True)
            (issue / "issue.yml").write_text(
                "id: ISSUE-007\nstatus: draft\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
            sha = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "-C", str(repo), "update-ref", "refs/remotes/origin/publish/issue-007-2026-08-19", sha],
                check=True,
            )

            records = discover_records(repo)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].issue_dir, "issues/ISSUE-007-seven")
            self.assertEqual(records[0].status, "draft")


if __name__ == "__main__":
    unittest.main()
