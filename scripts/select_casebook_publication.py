from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import subprocess

import yaml


BRANCH_RE = re.compile(r"^publish/issue-([0-9]{3})-[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ISSUE_ID_RE = re.compile(r"^ISSUE-([0-9]{3})$")
ISSUE_YML_RE = re.compile(r"^issues/(ISSUE-([0-9]{3})-[a-z0-9-]+)/issue\.yml$")
FINISHED_STATUSES = {"published", "corrected"}
VALID_STATUSES = {"draft", "rendered", "published", "corrected"}


class SelectionError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class BranchRecord:
    branch: str
    issue_id: str
    status: str
    issue_dir: str

    def __post_init__(self) -> None:
        branch_match = BRANCH_RE.fullmatch(self.branch)
        issue_match = ISSUE_ID_RE.fullmatch(self.issue_id)
        directory_match = re.fullmatch(
            r"issues/ISSUE-([0-9]{3})-[a-z0-9-]+", self.issue_dir
        )
        if not branch_match:
            raise SelectionError(f"invalid publication branch: {self.branch}")
        if not issue_match:
            raise SelectionError(f"invalid issue id: {self.issue_id}")
        if not directory_match:
            raise SelectionError(f"invalid issue directory: {self.issue_dir}")
        number = branch_match.group(1)
        if issue_match.group(1) != number or directory_match.group(1) != number:
            raise SelectionError(
                f"branch {self.branch} does not match {self.issue_id}/{self.issue_dir}"
            )
        if self.status not in VALID_STATUSES:
            raise SelectionError(f"unsupported issue status: {self.status}")

    @property
    def number(self) -> int:
        return int(self.issue_id.split("-")[1])


def validate_target_branch(branch: str, issue_id: str) -> None:
    match = BRANCH_RE.fullmatch(branch)
    if not match:
        raise SelectionError(f"invalid publication branch: {branch}")
    expected = f"ISSUE-{match.group(1)}"
    if expected != issue_id:
        raise SelectionError(f"publication branch {branch} does not match {issue_id}")


def select_named_target(
    records: list[BranchRecord], target_branch: str
) -> BranchRecord:
    if not BRANCH_RE.fullmatch(target_branch):
        raise SelectionError(f"invalid publication branch: {target_branch}")
    matches = [record for record in records if record.branch == target_branch]
    if len(matches) != 1:
        raise SelectionError(
            f"publication branch {target_branch} was not found exactly once"
        )
    return matches[0]


def select_target(records: list[BranchRecord]) -> BranchRecord | None:
    by_number: dict[int, BranchRecord] = {}
    for record in records:
        if record.number in by_number:
            other = by_number[record.number]
            raise SelectionError(
                f"duplicate publication branches reserve {record.issue_id}: "
                f"{other.branch}, {record.branch}"
            )
        by_number[record.number] = record
    unfinished = [record for record in records if record.status not in FINISHED_STATUSES]
    return max(unfinished, key=lambda record: record.number, default=None)


def _git(repo_root: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        raise SelectionError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


def discover_records(repo_root: pathlib.Path) -> list[BranchRecord]:
    repo_root = repo_root.resolve()
    refs = _git(
        repo_root,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/remotes/origin/publish/issue-*",
    )
    records: list[BranchRecord] = []
    for remote_ref in sorted(line.strip() for line in refs.splitlines() if line.strip()):
        if not remote_ref.startswith("origin/"):
            continue
        branch = remote_ref.removeprefix("origin/")
        if not BRANCH_RE.fullmatch(branch):
            continue
        paths = _git(repo_root, "ls-tree", "-r", "--name-only", remote_ref, "issues/")
        candidates = [
            line.strip()
            for line in paths.splitlines()
            if ISSUE_YML_RE.fullmatch(line.strip())
            and ISSUE_YML_RE.fullmatch(line.strip()).group(2)
            == BRANCH_RE.fullmatch(branch).group(1)
        ]
        if len(candidates) != 1:
            raise SelectionError(
                f"expected one issue.yml for {branch}, found {len(candidates)}"
            )
        issue_yml = candidates[0]
        text = _git(repo_root, "show", f"{remote_ref}:{issue_yml}")
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SelectionError(f"cannot parse {issue_yml} on {branch}: {exc}") from exc
        if not isinstance(data, dict):
            raise SelectionError(f"{issue_yml} on {branch} is not an object")
        issue_id = data.get("id")
        status = data.get("status")
        if not isinstance(issue_id, str) or not isinstance(status, str):
            raise SelectionError(f"{issue_yml} on {branch} lacks id/status")
        records.append(
            BranchRecord(
                branch=branch,
                issue_id=issue_id,
                status=status,
                issue_dir=issue_yml.rsplit("/", 1)[0],
            )
        )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the highest unfinished Engineering Casebook branch"
    )
    parser.add_argument("--repo-root", required=True, type=pathlib.Path)
    parser.add_argument("--target-branch")
    args = parser.parse_args(argv)
    try:
        records = discover_records(args.repo_root)
        if args.target_branch:
            selected = select_named_target(records, args.target_branch)
        else:
            selected = select_target(records)
    except SelectionError as exc:
        parser.exit(1, f"Casebook branch selection failed: {exc}\n")
    if selected is None:
        print("NOOP")
    else:
        print(f"{selected.branch}\t{selected.issue_dir}\t{selected.issue_id}\t{selected.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
