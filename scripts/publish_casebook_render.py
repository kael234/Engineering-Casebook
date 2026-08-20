from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import pathlib
import re
import subprocess
import tempfile

import yaml
from PIL import Image

try:
    from scripts.render_casebook import RenderError, load_issue_meta, render_issue
except ImportError:  # pragma: no cover - direct script execution
    from render_casebook import RenderError, load_issue_meta, render_issue


BRANCH_RE = re.compile(r"^publish/issue-([0-9]{3})-[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ISSUE_DIR_RE = re.compile(r"^issues/ISSUE-([0-9]{3})-[a-z0-9-]+$")
RENDERER_VERSION = "casebook-renderer/1"


class PublicationError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class ArtifactMeta:
    path: str
    byte_size: int
    sha256: str


@dataclasses.dataclass(frozen=True)
class PublicationResult:
    issue_id: str
    pdf: ArtifactMeta
    preview: ArtifactMeta
    changed: bool


def validate_publication_branch(branch: str, issue_id: str) -> None:
    match = BRANCH_RE.fullmatch(branch)
    if not match:
        raise PublicationError(f"invalid publication branch: {branch}")
    expected = f"ISSUE-{match.group(1)}"
    if expected != issue_id:
        raise PublicationError(f"publication branch {branch} does not match {issue_id}")


def _artifact_meta(path: pathlib.Path, output_name: str) -> ArtifactMeta:
    raw = path.read_bytes()
    return ArtifactMeta(
        path=output_name,
        byte_size=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _artifact_from_mapping(issue_path: pathlib.Path, value: object) -> ArtifactMeta | None:
    if not isinstance(value, dict):
        return None
    rel = value.get("path")
    size = value.get("byte_size")
    digest = value.get("sha256")
    if (
        not isinstance(rel, str)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        return None
    candidate = (issue_path / rel).resolve()
    root = issue_path.resolve()
    if root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
        return None
    raw = candidate.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        return None
    return ArtifactMeta(rel, size, digest)


def _existing_render(issue_path: pathlib.Path, yml_text: str) -> PublicationResult | None:
    try:
        data = yaml.safe_load(yml_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or data.get("status") not in {"rendered", "published"}:
        return None
    if (issue_path / ".handoff").exists():
        return None
    pdf = _artifact_from_mapping(issue_path, data.get("pdf"))
    preview = _artifact_from_mapping(issue_path, data.get("preview"))
    issue_id = data.get("id")
    if pdf is None or preview is None or not isinstance(issue_id, str):
        return None
    return PublicationResult(issue_id, pdf, preview, False)


def render_rendered_issue_yml(
    existing: str,
    pdf: ArtifactMeta,
    preview: ArtifactMeta,
    renderer_version: str,
) -> str:
    try:
        data = yaml.safe_load(existing)
    except yaml.YAMLError as exc:
        raise PublicationError(f"cannot parse issue.yml: {exc}") from exc
    if not isinstance(data, dict):
        raise PublicationError("issue.yml must contain an object")
    if data.get("status") not in {"draft", "rendered"}:
        raise PublicationError(f"cannot render issue in status {data.get('status')!r}")

    data["status"] = "rendered"
    data["note"] = (
        "PDF and preview generated deterministically and mechanically validated by "
        "GitHub Actions; awaiting visual publication review."
    )
    data["pdf"] = dataclasses.asdict(pdf)
    data["preview"] = dataclasses.asdict(preview)
    data["render"] = {
        "renderer": renderer_version,
        "mechanical_validation": "passed",
        "visual_review": "pending",
    }
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _mechanical_validate_pdf(
    pdf_path: pathlib.Path,
    issue_path: pathlib.Path,
    issue_yml_text: str,
    page_count: int,
) -> None:
    try:
        from scripts import casebook_finalizer
    except ImportError as exc:  # pragma: no cover - environment contract
        raise PublicationError("trusted casebook_finalizer.py is unavailable") from exc
    try:
        casebook_finalizer.validate_pdf(
            pdf_path,
            issue_path,
            issue_yml_text,
            page_count,
        )
    except Exception as exc:
        raise PublicationError(f"mechanical PDF validation failed: {exc}") from exc


def _generate_preview(pdf_path: pathlib.Path, preview_path: pathlib.Path) -> None:
    prefix = preview_path.with_suffix("")
    completed = subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-singlefile",
            "-jpeg",
            "-scale-to",
            "1200",
            str(pdf_path),
            str(prefix),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    generated = prefix.with_suffix(".jpg")
    if completed.returncode != 0 or not generated.is_file():
        raise PublicationError(f"preview generation failed: {completed.stderr.strip()}")
    if generated != preview_path:
        os.replace(generated, preview_path)
    raw = preview_path.read_bytes()
    if not raw.startswith(b"\xff\xd8\xff") or not raw.endswith(b"\xff\xd9"):
        raise PublicationError("preview is not a valid JPEG")
    try:
        with Image.open(preview_path) as image:
            image.verify()
        with Image.open(preview_path) as image:
            width, height = image.size
    except Exception as exc:
        raise PublicationError(f"preview verification failed: {exc}") from exc
    if width < 600 or height < 600:
        raise PublicationError(f"preview dimensions are too small: {width}x{height}")


def _safe_issue_path(repo_root: pathlib.Path, issue_dir: str) -> pathlib.Path:
    match = ISSUE_DIR_RE.fullmatch(issue_dir)
    if not match:
        raise PublicationError(f"invalid issue directory: {issue_dir}")
    root = repo_root.resolve()
    issue_path = (root / issue_dir).resolve()
    issues_root = (root / "issues").resolve()
    if issues_root not in issue_path.parents or not issue_path.is_dir():
        raise PublicationError(f"issue directory is missing or escapes issues root: {issue_dir}")
    return issue_path


def publish_render(
    repo_root: pathlib.Path,
    issue_dir: str,
    branch: str,
    tooling_root: pathlib.Path,
) -> PublicationResult:
    issue_path = _safe_issue_path(repo_root, issue_dir)
    issue_yml_path = issue_path / "issue.yml"
    if issue_yml_path.is_symlink():
        raise PublicationError("issue.yml may not be a symlink")
    try:
        issue_yml_text = issue_yml_path.read_text(encoding="utf-8")
        meta = load_issue_meta(issue_yml_path)
    except (OSError, UnicodeError, RenderError) as exc:
        raise PublicationError(f"invalid issue package: {exc}") from exc
    validate_publication_branch(branch, meta.issue_id)

    handoff = issue_path / ".handoff"
    if handoff.is_symlink():
        raise PublicationError("refusing to process symlinked .handoff")

    existing = _existing_render(issue_path, issue_yml_text)
    if existing is not None:
        return existing

    if meta.status != "draft":
        raise PublicationError(f"issue must be draft before rendering, found {meta.status}")

    template_root = tooling_root.resolve() / "templates"
    output_name = f"{issue_path.name}.pdf"
    final_pdf = issue_path / output_name
    final_preview = issue_path / "preview.jpg"
    for target in (final_pdf, final_preview):
        if target.is_symlink():
            raise PublicationError(f"render target may not be a symlink: {target.name}")

    with tempfile.TemporaryDirectory(
        prefix=".casebook-publish-", dir=issue_path
    ) as temp_dir_name:
        temp_dir = pathlib.Path(temp_dir_name)
        pdf_temp = temp_dir / output_name
        preview_temp = temp_dir / "preview.jpg"
        try:
            render_issue(issue_path, pdf_temp, template_root)
        except RenderError as exc:
            raise PublicationError(str(exc)) from exc
        _mechanical_validate_pdf(
            pdf_temp,
            issue_path,
            issue_yml_text,
            meta.page_count,
        )
        _generate_preview(pdf_temp, preview_temp)
        pdf_meta = _artifact_meta(pdf_temp, output_name)
        preview_meta = _artifact_meta(preview_temp, "preview.jpg")
        updated_yml = render_rendered_issue_yml(
            issue_yml_text,
            pdf_meta,
            preview_meta,
            RENDERER_VERSION,
        )
        staged_yml = temp_dir / "issue.yml"
        staged_yml.write_text(updated_yml, encoding="utf-8")

        backups: dict[pathlib.Path, pathlib.Path] = {}
        handoff_backup: pathlib.Path | None = None
        try:
            for target in (final_pdf, final_preview):
                if target.exists():
                    backup = temp_dir / f"backup-{target.name}"
                    target.rename(backup)
                    backups[target] = backup
            if handoff.exists():
                handoff_backup = temp_dir / "backup-handoff"
                handoff.rename(handoff_backup)

            os.replace(pdf_temp, final_pdf)
            os.replace(preview_temp, final_preview)
            os.replace(staged_yml, issue_yml_path)
        except OSError as exc:
            for target in (final_pdf, final_preview):
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
            for target, backup in backups.items():
                if backup.exists():
                    backup.rename(target)
            if handoff_backup is not None and handoff_backup.exists():
                handoff_backup.rename(handoff)
            raise PublicationError(f"render persistence failed: {exc}") from exc

    return PublicationResult(meta.issue_id, pdf_meta, preview_meta, True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render and mechanically validate an Engineering Casebook issue"
    )
    parser.add_argument("--repo-root", required=True, type=pathlib.Path)
    parser.add_argument("--issue-dir", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument(
        "--tooling-root",
        default=pathlib.Path(__file__).parents[1],
        type=pathlib.Path,
    )
    args = parser.parse_args(argv)
    try:
        result = publish_render(
            args.repo_root,
            args.issue_dir,
            args.branch,
            args.tooling_root,
        )
    except PublicationError as exc:
        parser.exit(1, f"Casebook publication render failed: {exc}\n")
    print(
        f"{result.issue_id} changed={str(result.changed).lower()} "
        f"pdf={result.pdf.path}:{result.pdf.byte_size}:{result.pdf.sha256} "
        f"preview={result.preview.path}:{result.preview.byte_size}:{result.preview.sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
