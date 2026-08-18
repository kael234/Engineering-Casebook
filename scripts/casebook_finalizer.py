from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

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


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n\t ]*$")


def reconstruct_artifact(issue_dir: pathlib.Path, artifact: dict) -> bytes:
    handoff_dir = issue_dir / ".handoff"
    pieces: list[str] = []
    for chunk_name in artifact["chunks"]:
        chunk_path = handoff_dir / chunk_name
        try:
            text = chunk_path.read_text(encoding="ascii")
        except (OSError, UnicodeError) as exc:
            raise FinalizerError(f"cannot read chunk {chunk_name}: {exc}") from exc
        if not _BASE64_RE.fullmatch(text):
            raise FinalizerError(f"chunk {chunk_name} contains non-base64 characters")
        pieces.append(text)

    encoded = "".join(pieces)
    compact = re.sub(r"[\r\n\t ]", "", encoded)
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FinalizerError(f"base64 decode failed for {artifact['role']}: {exc}") from exc

    if len(raw) != artifact["byte_size"]:
        raise FinalizerError(
            f"decoded byte size mismatch for {artifact['role']}: "
            f"expected {artifact['byte_size']}, got {len(raw)}"
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != artifact["sha256"]:
        raise FinalizerError(f"sha256 mismatch for {artifact['role']}")

    if artifact["role"] == "pdf":
        if not raw.startswith(b"%PDF-"):
            raise FinalizerError("PDF magic is invalid")
    elif artifact["role"] == "preview":
        if not raw.startswith(b"\xff\xd8\xff") or not raw.endswith(b"\xff\xd9"):
            raise FinalizerError("JPEG magic/trailer is invalid")
    else:
        raise FinalizerError("unsupported artifact role")
    return raw


def _top_level_spans(lines: list[str]) -> list[tuple[str, int, int]]:
    starts: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        if not line.strip() or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_]+):(?:\s|$)", line)
        if match:
            starts.append((match.group(1), index))
    spans: list[tuple[str, int, int]] = []
    for pos, (key, start) in enumerate(starts):
        end = starts[pos + 1][1] if pos + 1 < len(starts) else len(lines)
        spans.append((key, start, end))
    return spans


def render_issue_yml(existing: str, artifacts: dict[str, dict]) -> str:
    if set(artifacts) != {"pdf", "preview"}:
        raise FinalizerError("artifact map must contain pdf and preview")
    lines = existing.splitlines(keepends=True)
    spans = _top_level_spans(lines)
    span_by_key = {key: (start, end) for key, start, end in spans}

    replacements: dict[str, list[str] | None] = {
        "status": ["status: published\n"],
        "original_format": ["original_format: magazine_v3\n"],
        "pdf": [
            "pdf:\n",
            f"  path: {artifacts['pdf']['output']}\n",
            f"  sha256: {artifacts['pdf']['sha256']}\n",
            f"  byte_size: {artifacts['pdf']['byte_size']}\n",
        ],
        "preview": [
            "preview:\n",
            f"  path: {artifacts['preview']['output']}\n",
            f"  sha256: {artifacts['preview']['sha256']}\n",
            f"  byte_size: {artifacts['preview']['byte_size']}\n",
        ],
    }
    if "diagnostic" in span_by_key:
        replacements["diagnostic"] = ["diagnostic: false\n"]
    if "note" in span_by_key:
        start, end = span_by_key["note"]
        note_text = "".join(lines[start:end])
        if "Checkpoint F" in note_text or "binary upload" in note_text.lower():
            replacements["note"] = [
                "note: Binary artifacts finalized and mechanically validated by GitHub Actions.\n"
            ]

    output: list[str] = []
    index = 0
    for key, start, end in spans:
        if start < index:
            continue
        output.extend(lines[index:start])
        if key in replacements:
            replacement = replacements.pop(key)
            if replacement:
                output.extend(replacement)
        else:
            output.extend(lines[start:end])
        index = end
    output.extend(lines[index:])

    for key in ("pdf", "preview"):
        if key in replacements:
            if output and output[-1] and not output[-1].endswith("\n"):
                output[-1] += "\n"
            output.extend(replacements[key] or [])
            replacements.pop(key, None)

    return "".join(output)


A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89
A4_TOLERANCE_PT = 2.0
MIN_TEXT_WORDS = 1800
MIN_TEXT_NONSPACE = 10000


def _plain_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def parse_issue_yml(issue_yml_text: str) -> dict:
    lines = issue_yml_text.splitlines(keepends=True)
    spans = _top_level_spans(lines)
    raw: dict[str, str] = {}
    blocks: dict[str, list[str]] = {}
    for key, start, end in spans:
        first = lines[start]
        value = first.split(":", 1)[1].strip()
        raw[key] = value
        blocks[key] = lines[start:end]

    try:
        page_count = int(raw["page_count"])
    except (KeyError, ValueError) as exc:
        raise FinalizerError("issue.yml requires integer page_count") from exc
    if str(page_count) != raw["page_count"]:
        raise FinalizerError("issue.yml page_count must be a plain integer")

    slot_lines = blocks.get("slots", [])
    slot_count = sum(1 for line in slot_lines[1:] if re.match(r"^\s{2}-\s+", line))
    if slot_count <= 0:
        raise FinalizerError("issue.yml has no slots")

    markdown = _plain_scalar(raw.get("markdown", ""))
    if not markdown:
        raise FinalizerError("issue.yml requires markdown path")

    snapshots: list[str] = []
    for line in blocks.get("snapshots", [])[1:]:
        match = re.match(r"^\s{2}[A-Za-z0-9_-]+:\s*(.+?)\s*$", line)
        if match:
            snapshots.append(_plain_scalar(match.group(1)))
    if not snapshots:
        raise FinalizerError("issue.yml requires snapshot paths")

    assets: list[str] = []
    for line in blocks.get("assets", [])[1:]:
        match = re.match(r"^\s{2}-\s+(.+?)\s*$", line)
        if match:
            assets.append(_plain_scalar(match.group(1)))
    if not assets:
        raise FinalizerError("issue.yml requires asset paths")

    override = _plain_scalar(raw.get("page_count_override_reason", "")) or None
    return {
        "page_count": page_count,
        "page_count_override_reason": override,
        "slot_count": slot_count,
        "markdown": markdown,
        "snapshots": snapshots,
        "assets": assets,
    }


def _safe_reference(issue_dir: pathlib.Path, rel: str) -> pathlib.Path:
    if not rel or "\\" in rel:
        raise FinalizerError(f"invalid issue reference path: {rel!r}")
    pure = pathlib.PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        raise FinalizerError(f"issue reference escapes issue directory: {rel}")
    root = issue_dir.resolve()
    candidate = (root / rel).resolve()
    if candidate == root or root not in candidate.parents:
        raise FinalizerError(f"issue reference escapes issue directory: {rel}")
    return candidate


def validate_issue_references(issue_dir: pathlib.Path, meta: dict) -> None:
    references = [meta["markdown"], *meta["snapshots"], *meta["assets"]]
    for rel in references:
        path = _safe_reference(issue_dir, rel)
        if not path.is_file():
            raise FinalizerError(f"referenced issue file is missing: {rel}")
    for rel in meta["assets"]:
        if not rel.lower().endswith(".svg"):
            raise FinalizerError(f"non-SVG issue asset listed for finalization: {rel}")


def _run_tool(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise FinalizerError(f"required tool not installed: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise FinalizerError(f"{args[0]} failed: {detail}") from exc
    return completed.stdout


def _parse_pdfinfo_pages(output: str) -> int:
    match = re.search(r"^Pages:\s+([0-9]+)\s*$", output, re.MULTILINE)
    if not match:
        raise FinalizerError("pdfinfo did not report page count")
    return int(match.group(1))


def _parse_page_size(output: str) -> tuple[float, float]:
    match = re.search(
        r"^Page(?:\s+[0-9]+)?\s+size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
        output,
        re.MULTILINE,
    )
    if not match:
        raise FinalizerError("pdfinfo did not report page size")
    return float(match.group(1)), float(match.group(2))


def _count_uri_annotations(output: str) -> int:
    count = 0
    for line in output.splitlines():
        if "http://" in line or "https://" in line:
            count += 1
    return count


def _validate_fonts(output: str) -> None:
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) < 3:
        raise FinalizerError("pdffonts did not report any font rows")
    data_rows = lines[2:]
    if not data_rows:
        raise FinalizerError("PDF contains no reported fonts")
    for row in data_rows:
        parts = row.split()
        if len(parts) < 7:
            raise FinalizerError(f"cannot parse pdffonts row: {row}")
        bool_positions = [i for i, token in enumerate(parts) if token in {"yes", "no"}]
        if len(bool_positions) < 3:
            raise FinalizerError(f"cannot locate pdffonts embedding column: {row}")
        embedded = parts[bool_positions[0]]
        if embedded != "yes":
            raise FinalizerError(f"unembedded font detected: {parts[0]}")


def validate_pdf(
    pdf_path: pathlib.Path,
    issue_dir: pathlib.Path,
    issue_yml_text: str,
    expected_pages: int,
) -> None:
    meta = parse_issue_yml(issue_yml_text)
    validate_issue_references(issue_dir, meta)

    if meta["page_count"] != expected_pages:
        raise FinalizerError(
            f"page-count mismatch: issue.yml={meta['page_count']} handoff={expected_pages}"
        )
    if expected_pages == 3:
        pass
    elif expected_pages == 4 and meta["page_count_override_reason"]:
        pass
    else:
        raise FinalizerError("only 3 pages are normal; 4 requires page_count_override_reason")

    info = _run_tool(["pdfinfo", str(pdf_path)])
    actual_pages = _parse_pdfinfo_pages(info)
    if actual_pages != expected_pages:
        raise FinalizerError(
            f"PDF page count mismatch: expected {expected_pages}, got {actual_pages}"
        )

    for page in range(1, actual_pages + 1):
        page_info = _run_tool(["pdfinfo", "-f", str(page), "-l", str(page), str(pdf_path)])
        width, height = _parse_page_size(page_info)
        if (
            abs(width - A4_WIDTH_PT) > A4_TOLERANCE_PT
            or abs(height - A4_HEIGHT_PT) > A4_TOLERANCE_PT
        ):
            raise FinalizerError(
                f"page {page} is not A4 within tolerance: {width} x {height} pt"
            )

    text = _run_tool(["pdftotext", str(pdf_path), "-"])
    words = re.findall(r"\S+", text)
    nonspace = re.sub(r"\s", "", text)
    if len(words) < MIN_TEXT_WORDS or len(nonspace) < MIN_TEXT_NONSPACE:
        raise FinalizerError(
            f"insufficient searchable text: words={len(words)}, nonspace={len(nonspace)}"
        )

    urls = _run_tool(["pdfinfo", "-url", str(pdf_path)])
    uri_count = _count_uri_annotations(urls)
    if uri_count < meta["slot_count"]:
        raise FinalizerError(
            f"insufficient live URI annotations: found {uri_count}, need {meta['slot_count']}"
        )

    fonts = _run_tool(["pdffonts", str(pdf_path)])
    _validate_fonts(fonts)


def _artifact_map(manifest: dict) -> dict[str, dict]:
    return {artifact["role"]: artifact for artifact in manifest["artifacts"]}


def _hash_matches(path: pathlib.Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest == expected_sha256


def _write_temp(issue_dir: pathlib.Path, suffix: str, data: bytes) -> pathlib.Path:
    fd, name = tempfile.mkstemp(prefix=".finalizer-", suffix=suffix, dir=issue_dir)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise
    return pathlib.Path(name)


def _atomic_write_text(path: pathlib.Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".finalizer-", suffix=".yml", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def finalize(repo_root: pathlib.Path, manifest_path: pathlib.Path, branch: str) -> str:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    if not manifest_path.exists():
        return "NOOP"

    manifest = load_and_validate_manifest(repo_root, manifest_path, branch)
    issue_dir = safe_issue_dir(repo_root, manifest["issue_dir"])
    issue_yml_path = issue_dir / "issue.yml"
    try:
        issue_yml_text = issue_yml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FinalizerError(f"cannot read issue.yml: {exc}") from exc

    artifacts = _artifact_map(manifest)
    reconstructed = {
        role: reconstruct_artifact(issue_dir, artifact)
        for role, artifact in artifacts.items()
    }

    targets = {
        role: issue_dir / artifact["output"]
        for role, artifact in artifacts.items()
    }
    temps: dict[str, pathlib.Path] = {}
    try:
        for role, artifact in artifacts.items():
            target = targets[role]
            if _hash_matches(target, artifact["sha256"]):
                continue
            suffix = ".pdf" if role == "pdf" else ".jpg"
            temps[role] = _write_temp(issue_dir, suffix, reconstructed[role])

        pdf_for_validation = temps.get("pdf", targets["pdf"])
        validate_pdf(
            pdf_for_validation,
            issue_dir,
            issue_yml_text,
            manifest["visual_inspection"]["page_count"],
        )

        rendered_yml = render_issue_yml(issue_yml_text, artifacts)

        for role in ("pdf", "preview"):
            if role in temps:
                os.replace(temps[role], targets[role])
                temps.pop(role, None)
        _atomic_write_text(issue_yml_path, rendered_yml)
        shutil.rmtree(issue_dir / ".handoff")
        return manifest["issue_id"]
    except FinalizerError:
        raise
    except OSError as exc:
        raise FinalizerError(f"filesystem finalization failed: {exc}") from exc
    finally:
        for path in temps.values():
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize an Engineering Casebook binary handoff")
    parser.add_argument("--repo-root", required=True, type=pathlib.Path)
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    try:
        result = finalize(args.repo_root, args.manifest, args.branch)
    except FinalizerError as exc:
        parser.exit(1, f"Casebook finalizer failed: {exc}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
