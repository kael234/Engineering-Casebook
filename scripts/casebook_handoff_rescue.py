from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile

MAX_CHUNK_CHARS = 16000
CHUNK_RE = re.compile(r"^(pdf|preview)\.part([0-9]{3})\.b64$")
ISSUE_DIR_RE = re.compile(r"^issues/ISSUE-([0-9]{3})-[a-z0-9-]+$")
BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\r\n\t ]*$")


class RescueError(RuntimeError):
    pass


def ordered_chunks(handoff_dir: pathlib.Path, role: str) -> list[pathlib.Path]:
    if role not in {"pdf", "preview"}:
        raise RescueError("unsupported artifact role")
    found: list[tuple[int, pathlib.Path]] = []
    for path in handoff_dir.glob(f"{role}.part*.b64"):
        match = CHUNK_RE.fullmatch(path.name)
        if not match or match.group(1) != role:
            continue
        found.append((int(match.group(2)), path))
    if not found:
        raise RescueError(f"no {role} chunks found")
    found.sort()
    expected = list(range(1, len(found) + 1))
    actual = [number for number, _ in found]
    if actual != expected:
        raise RescueError(f"{role} chunk sequence is incomplete: {actual}")
    return [path for _, path in found]


def _read_chunk(path: pathlib.Path) -> str:
    if path.is_symlink():
        raise RescueError(f"chunk may not be a symlink: {path.name}")
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RescueError(f"cannot read chunk {path.name}: {exc}") from exc
    if len(text) > MAX_CHUNK_CHARS:
        raise RescueError(f"chunk exceeds {MAX_CHUNK_CHARS} characters: {path.name}")
    if not BASE64_RE.fullmatch(text):
        raise RescueError(f"chunk contains non-base64 characters: {path.name}")
    return text


def decode_pdf_chunks(paths: list[pathlib.Path]) -> bytes:
    chunks = [_read_chunk(path) for path in paths]
    compacts = [re.sub(r"[\r\n\t ]", "", text) for text in chunks]
    compact = "".join(compacts)
    # Base64 must be a whole number of 4-character quanta. Verifying that up
    # front turns a corrupt transport into an instant, diagnosable failure
    # instead of an opaque "Incorrect padding" once the runner is already warm.
    if len(compact) % 4:
        sizes = ", ".join(
            f"{path.name}={len(text)}" for path, text in zip(paths, compacts)
        )
        raise RescueError(
            f"PDF base64 length {len(compact)} is not a multiple of 4 "
            f"(remainder {len(compact) % 4}); chunk lengths: {sizes}"
        )
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RescueError(f"PDF base64 decode failed: {exc}") from exc
    if not raw.startswith(b"%PDF-") or b"%%EOF" not in raw[-1024:]:
        raise RescueError("reconstructed PDF magic/trailer is invalid")
    return raw


def write_preview_chunks(
    handoff_dir: pathlib.Path, preview_bytes: bytes, max_chars: int = MAX_CHUNK_CHARS
) -> list[str]:
    if not preview_bytes.startswith(b"\xff\xd8\xff") or not preview_bytes.endswith(b"\xff\xd9"):
        raise RescueError("preview JPEG magic/trailer is invalid")
    for old in handoff_dir.glob("preview.part*.b64"):
        old.unlink()
    encoded = base64.b64encode(preview_bytes).decode("ascii")
    names: list[str] = []
    for index, start in enumerate(range(0, len(encoded), max_chars), 1):
        name = f"preview.part{index:03d}.b64"
        (handoff_dir / name).write_text(encoded[start : start + max_chars], encoding="ascii")
        names.append(name)
    return names


def build_manifest(
    *,
    issue_id: str,
    issue_dir: str,
    page_count: int,
    pdf_output: str,
    pdf_bytes: bytes,
    preview_bytes: bytes,
    pdf_chunks: list[str],
    preview_chunks: list[str],
) -> dict:
    return {
        "schema_version": 1,
        "issue_id": issue_id,
        "issue_dir": issue_dir,
        "visual_inspection": {"passed": True, "page_count": page_count},
        "artifacts": [
            {
                "role": "pdf",
                "output": pdf_output,
                "media_type": "application/pdf",
                "byte_size": len(pdf_bytes),
                "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "chunks": pdf_chunks,
            },
            {
                "role": "preview",
                "output": "preview.jpg",
                "media_type": "image/jpeg",
                "byte_size": len(preview_bytes),
                "sha256": hashlib.sha256(preview_bytes).hexdigest(),
                "chunks": preview_chunks,
            },
        ],
    }


def _generate_preview(pdf_path: pathlib.Path, output: pathlib.Path) -> bytes:
    prefix = output.with_suffix("")
    proc = subprocess.run(
        ["pdftoppm", "-f", "1", "-singlefile", "-jpeg", "-scale-to", "600", str(pdf_path), str(prefix)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    generated = prefix.with_suffix(".jpg")
    if proc.returncode != 0 or not generated.is_file():
        raise RescueError(f"preview generation failed: {proc.stderr.strip()}")
    data = generated.read_bytes()
    if not data.startswith(b"\xff\xd8\xff") or not data.endswith(b"\xff\xd9"):
        raise RescueError("generated preview is not a valid JPEG")
    return data


def rescue(repo_root: pathlib.Path, issue_dir: str, branch: str) -> str:
    match = ISSUE_DIR_RE.fullmatch(issue_dir)
    if not match:
        raise RescueError("invalid issue directory")
    root = repo_root.resolve()
    issue_path = (root / issue_dir).resolve()
    if (root / "issues").resolve() not in issue_path.parents:
        raise RescueError("issue directory escapes issues root")
    handoff = issue_path / ".handoff"
    request_path = handoff / "rescue-request.json"
    if not request_path.is_file():
        return "NOOP"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request != {"visual_inspection_passed": True}:
        raise RescueError("rescue request must explicitly confirm visual inspection")

    try:
        from scripts import casebook_finalizer as finalizer
    except ImportError:
        import casebook_finalizer as finalizer

    issue_id = f"ISSUE-{match.group(1)}"
    finalizer.validate_branch(branch, issue_id)
    issue_yml_path = issue_path / "issue.yml"
    issue_yml_text = issue_yml_path.read_text(encoding="utf-8")
    meta = finalizer.parse_issue_yml(issue_yml_text)

    pdf_paths = ordered_chunks(handoff, "pdf")
    pdf_bytes = decode_pdf_chunks(pdf_paths)
    with tempfile.NamedTemporaryFile(suffix=".pdf", dir=issue_path, delete=False) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = pathlib.Path(tmp.name)
    try:
        finalizer.validate_pdf(pdf_path, issue_path, issue_yml_text, meta["page_count"])
        preview_path = issue_path / ".rescue-preview.jpg"
        preview_bytes = _generate_preview(pdf_path, preview_path)
    finally:
        pdf_path.unlink(missing_ok=True)
        (issue_path / ".rescue-preview.jpg").unlink(missing_ok=True)

    preview_names = write_preview_chunks(handoff, preview_bytes)
    manifest = build_manifest(
        issue_id=issue_id,
        issue_dir=issue_dir,
        page_count=meta["page_count"],
        pdf_output=f"{issue_path.name}.pdf",
        pdf_bytes=pdf_bytes,
        preview_bytes=preview_bytes,
        pdf_chunks=[path.name for path in pdf_paths],
        preview_chunks=preview_names,
    )
    (handoff / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    request_path.unlink()
    return issue_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Complete an abandoned Casebook handoff")
    parser.add_argument("--repo-root", required=True, type=pathlib.Path)
    parser.add_argument("--issue-dir", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args(argv)
    try:
        print(rescue(args.repo_root, args.issue_dir, args.branch))
    except (RescueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Casebook handoff rescue failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
