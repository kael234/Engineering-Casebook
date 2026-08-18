from __future__ import annotations

import json
import pathlib
import re

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
BRANCH_RE = re.compile(r"^publish/issue-([0-9]{3})-[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ISSUE_ID_RE = re.compile(r"^ISSUE-([0-9]{3})$")
ISSUE_DIR_RE = re.compile(r"^issues/ISSUE-([0-9]{3})-[a-z0-9-]+$")
CHUNK_RE = re.compile(r"^(pdf|preview)\.part[0-9]{3}\.b64$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

TOP_KEYS = {"schema_version", "issue_id", "issue_dir", "visual_inspection", "artifacts"}
VISUAL_KEYS = {"passed", "page_count"}
ARTIFACT_KEYS = {"role", "output", "media_type", "byte_size", "sha256", "chunks"}


class FinalizerError(RuntimeError):
    pass


def _require_exact_keys(obj: dict, expected: set[str], label: str) -> None:
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise FinalizerError(f"{label} keys invalid; missing={missing} extra={extra}")


def validate_branch(branch: str, issue_id: str) -> None:
    issue_match = ISSUE_ID_RE.fullmatch(issue_id)
    if not issue_match:
        raise FinalizerError("invalid issue_id")
    branch_match = BRANCH_RE.fullmatch(branch)
    if not branch_match:
        raise FinalizerError("invalid publication branch")
    if branch_match.group(1) != issue_match.group(1):
        raise FinalizerError("publication branch issue number does not match issue_id")


def safe_issue_dir(repo_root: pathlib.Path, issue_dir: str) -> pathlib.Path:
    if ".." in pathlib.PurePosixPath(issue_dir).parts:
        raise FinalizerError("issue_dir traversal is not allowed")
    match = ISSUE_DIR_RE.fullmatch(issue_dir)
    if not match:
        raise FinalizerError("invalid issue_dir")
    root = repo_root.resolve()
    candidate = (root / issue_dir).resolve()
    issues_root = (root / "issues").resolve()
    if candidate == issues_root or issues_root not in candidate.parents:
        raise FinalizerError("issue_dir escapes issues root")
    return candidate


def _validate_artifact(artifact: dict) -> None:
    if not isinstance(artifact, dict):
        raise FinalizerError("artifact must be an object")
    _require_exact_keys(artifact, ARTIFACT_KEYS, "artifact")

    role = artifact["role"]
    output = artifact["output"]
    media_type = artifact["media_type"]
    byte_size = artifact["byte_size"]
    sha256 = artifact["sha256"]
    chunks = artifact["chunks"]

    if role not in {"pdf", "preview"}:
        raise FinalizerError("invalid artifact role")
    if not isinstance(output, str) or "/" in output or "\\" in output or ".." in output:
        raise FinalizerError("invalid artifact output")
    if role == "pdf":
        if not output.endswith(".pdf") or media_type != "application/pdf":
            raise FinalizerError("invalid PDF output/media type")
    else:
        if not output.lower().endswith((".jpg", ".jpeg")) or media_type != "image/jpeg":
            raise FinalizerError("invalid preview output/media type")

    if isinstance(byte_size, bool) or not isinstance(byte_size, int):
        raise FinalizerError("byte_size must be an integer")
    if byte_size <= 0 or byte_size > MAX_ARTIFACT_BYTES:
        raise FinalizerError("byte_size outside allowed range")
    if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
        raise FinalizerError("invalid sha256")
    if not isinstance(chunks, list) or not chunks:
        raise FinalizerError("chunks must be a non-empty list")
    if len(chunks) != len(set(chunks)):
        raise FinalizerError("duplicate chunk names")
    expected_prefix = f"{role}."
    for chunk in chunks:
        if not isinstance(chunk, str) or "/" in chunk or "\\" in chunk or ".." in chunk:
            raise FinalizerError("invalid chunk name")
        if not CHUNK_RE.fullmatch(chunk) or not chunk.startswith(expected_prefix):
            raise FinalizerError("invalid chunk name for artifact role")


def load_and_validate_manifest(
    repo_root: pathlib.Path, manifest_path: pathlib.Path, branch: str
) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizerError(f"cannot read handoff manifest: {exc}") from exc

    if not isinstance(manifest, dict):
        raise FinalizerError("handoff manifest must be an object")
    _require_exact_keys(manifest, TOP_KEYS, "manifest")

    schema_version = manifest["schema_version"]
    if type(schema_version) is not int or schema_version != 1:
        raise FinalizerError("unsupported schema_version")

    issue_id = manifest["issue_id"]
    issue_match = ISSUE_ID_RE.fullmatch(issue_id) if isinstance(issue_id, str) else None
    if not issue_match:
        raise FinalizerError("invalid issue_id")

    issue_dir = manifest["issue_dir"]
    if not isinstance(issue_dir, str):
        raise FinalizerError("issue_dir must be a string")
    issue_path = safe_issue_dir(repo_root, issue_dir)
    dir_match = ISSUE_DIR_RE.fullmatch(issue_dir)
    assert dir_match is not None
    if dir_match.group(1) != issue_match.group(1):
        raise FinalizerError("issue_dir issue number does not match issue_id")

    expected_manifest_path = issue_path / ".handoff" / "manifest.json"
    if manifest_path.resolve() != expected_manifest_path.resolve():
        raise FinalizerError("manifest path does not match issue_dir")

    validate_branch(branch, issue_id)

    visual = manifest["visual_inspection"]
    if not isinstance(visual, dict):
        raise FinalizerError("visual_inspection must be an object")
    _require_exact_keys(visual, VISUAL_KEYS, "visual_inspection")
    if visual["passed"] is not True:
        raise FinalizerError("visual inspection must explicitly pass")
    page_count = visual["page_count"]
    if type(page_count) is not int or page_count not in {3, 4}:
        raise FinalizerError("visual page_count must be integer 3 or 4")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise FinalizerError("artifacts must contain exactly PDF and preview")
    for artifact in artifacts:
        _validate_artifact(artifact)
    roles = [artifact["role"] for artifact in artifacts]
    if sorted(roles) != ["pdf", "preview"]:
        raise FinalizerError("artifacts must contain exactly one PDF and one preview")
    outputs = [artifact["output"] for artifact in artifacts]
    if len(outputs) != len(set(outputs)):
        raise FinalizerError("duplicate artifact outputs")
    all_chunks = [chunk for artifact in artifacts for chunk in artifact["chunks"]]
    if len(all_chunks) != len(set(all_chunks)):
        raise FinalizerError("chunk names must be unique across artifacts")

    return manifest
