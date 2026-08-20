from __future__ import annotations

import argparse
import dataclasses
import html
import os
import pathlib
import re
import subprocess
import tempfile

import mistune
import yaml
from jinja2 import Environment, StrictUndefined
from weasyprint import HTML

ISSUE_ID_RE = re.compile(r"^ISSUE-([0-9]{3})$")
PAGE_MARKER_RE = re.compile(r"^## PAGE ([0-9]+)\s*[-–—]\s*(.+?)\s*$", re.MULTILINE)
CASE_HEADING_RE = re.compile(
    r"^# (?!Engineering Casebook\b).+$", re.MULTILINE | re.IGNORECASE
)
IMAGE_BLOCK_RE = re.compile(r"^!\[[^\]]*\]\([^)]+\)\s*$", re.MULTILINE)
SHORT_FEATURE_MAX_WORDS = 525


class RenderError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class IssueMeta:
    issue_id: str
    number: int
    title: str
    status: str
    page_count: int
    page_count_override_reason: str | None
    markdown: str
    snapshots: tuple[str, ...]
    assets: tuple[str, ...]
    slot_count: int


@dataclasses.dataclass(frozen=True)
class PageSection:
    number: int
    title: str
    markdown: str


@dataclasses.dataclass(frozen=True)
class RenderResult:
    issue_id: str
    output_pdf: pathlib.Path
    page_count: int
    page_sizes: tuple[tuple[float, float], ...]
    source_word_count: int

    @property
    def source_words(self) -> int:
        return self.source_word_count


def _safe_rel_path(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RenderError(f"invalid {label} path: {value!r}")
    pure = pathlib.PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise RenderError(f"{label} path escapes issue directory: {value}")
    return value


def load_issue_meta(path: pathlib.Path) -> IssueMeta:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RenderError(f"cannot read issue.yml: {exc}") from exc
    if not isinstance(data, dict):
        raise RenderError("issue.yml must contain an object")

    issue_id = data.get("id")
    match = ISSUE_ID_RE.fullmatch(issue_id) if isinstance(issue_id, str) else None
    if not match:
        raise RenderError("issue.yml has invalid id")
    number = data.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
        raise RenderError("issue.yml number must be an integer")
    if number != int(match.group(1)):
        raise RenderError("issue.yml number does not match id")

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RenderError("issue.yml requires a title")
    status = data.get("status")
    if status not in {"draft", "rendered", "published", "corrected"}:
        raise RenderError("issue.yml has unsupported status")

    page_count = data.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int):
        raise RenderError("issue.yml page_count must be an integer")
    if page_count not in {3, 4}:
        raise RenderError("issue.yml page_count must be 3 or 4")
    reason = data.get("page_count_override_reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        reason = None
    if page_count == 4 and not reason:
        raise RenderError("four-page issue requires non-empty page_count_override_reason")

    markdown = _safe_rel_path(data.get("markdown"), label="markdown")
    snapshots_obj = data.get("snapshots", {}) or {}
    if not isinstance(snapshots_obj, dict):
        raise RenderError("issue.yml snapshots must be an object")
    snapshots = tuple(
        _safe_rel_path(value, label="snapshot") for value in snapshots_obj.values()
    )
    assets_obj = data.get("assets", [])
    if not isinstance(assets_obj, list):
        raise RenderError("issue.yml assets must be a list")
    assets = tuple(_safe_rel_path(value, label="asset") for value in assets_obj)
    slots = data.get("slots")
    if not isinstance(slots, list) or not slots:
        raise RenderError("issue.yml requires slots")

    return IssueMeta(
        issue_id=issue_id,
        number=number,
        title=title.strip(),
        status=status,
        page_count=page_count,
        page_count_override_reason=reason.strip() if isinstance(reason, str) else None,
        markdown=markdown,
        snapshots=snapshots,
        assets=assets,
        slot_count=len(slots),
    )


def split_pages(markdown: str, expected_count: int) -> list[PageSection]:
    markers = list(PAGE_MARKER_RE.finditer(markdown))
    if not markers:
        raise RenderError("issue Markdown contains no PAGE markers")
    numbers = [int(marker.group(1)) for marker in markers]
    if numbers != list(range(1, len(numbers) + 1)):
        raise RenderError(f"PAGE markers must be contiguous from 1; found {numbers}")
    if len(markers) != expected_count:
        raise RenderError(
            f"expected {expected_count} page sections but found {len(markers)} PAGE markers"
        )

    preamble = markdown[: markers[0].start()].strip()
    pages: list[PageSection] = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(markdown)
        body = markdown[start:end].strip()
        if index == 0 and preamble:
            body = f"{preamble}\n\n{body}" if body else preamble
        pages.append(
            PageSection(
                number=numbers[index],
                title=marker.group(2).strip(),
                markdown=body,
            )
        )
    return pages


def is_short_feature_page(markdown: str) -> bool:
    """Return true for a compact, single-case page suited to a feature layout."""
    case_count = len(CASE_HEADING_RE.findall(markdown))
    figure_count = len(IMAGE_BLOCK_RE.findall(markdown))
    word_count = len(re.findall(r"\b\w+\b", markdown))
    return (
        case_count == 1
        and figure_count == 1
        and word_count <= SHORT_FEATURE_MAX_WORDS
    )


def resolve_asset(issue_dir: pathlib.Path, relative: str) -> pathlib.Path:
    relative = _safe_rel_path(relative, label="image asset")
    if pathlib.PurePosixPath(relative).suffix.lower() != ".svg":
        raise RenderError(f"publication image must be SVG: {relative}")
    root = issue_dir.resolve()
    candidate = (root / relative).resolve()
    if root not in candidate.parents:
        raise RenderError(f"image asset escapes issue directory: {relative}")
    if not candidate.is_file():
        raise RenderError(f"missing image asset: {relative}")
    if candidate.is_symlink():
        raise RenderError(f"image asset may not be a symlink: {relative}")
    return candidate


class _CasebookHTMLRenderer(mistune.HTMLRenderer):
    def __init__(self, issue_dir: pathlib.Path):
        super().__init__(escape=True)
        self.issue_dir = issue_dir

    def image(self, text: str, url: str, title: str | None = None) -> str:
        asset = resolve_asset(self.issue_dir, url)
        alt = re.sub(r"<[^>]+>", "", text or "").strip()
        title_attr = f' title="{html.escape(title, quote=True)}"' if title else ""
        return (
            '<figure class="technical-figure">'
            f'<img src="{html.escape(asset.as_uri(), quote=True)}" '
            f'alt="{html.escape(alt, quote=True)}"{title_attr}>'
            f'<figcaption>{html.escape(alt)}</figcaption>'
            "</figure>"
        )

    def heading(self, text: str, level: int, **attrs: object) -> str:
        plain = re.sub(r"<[^>]+>", "", text).strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
        classes = [f"heading-{level}"]
        module_slug = None
        if plain.startswith(("engineer's notebook", "engineers notebook")):
            module_slug = "engineers-notebook"
        else:
            exact_modules = {
                "you-are-the-engineer",
                "evidence-boundary",
                "sources-for-this-case",
                "the-thread",
                "60-second-takeaway",
                "from-the-archive",
            }
            if slug in exact_modules:
                module_slug = slug
        if module_slug:
            classes.extend(("module-heading", f"module-{module_slug}"))
        return f'<h{level} class="{" ".join(classes)}">{text}</h{level}>\n'


def render_markdown_page(markdown: str, issue_dir: pathlib.Path) -> str:
    converter = mistune.create_markdown(
        escape=True,
        renderer=_CasebookHTMLRenderer(issue_dir),
        plugins=["url", "table", "strikethrough"],
    )
    return converter(markdown)


def _safe_issue_file(issue_dir: pathlib.Path, relative: str, label: str) -> pathlib.Path:
    relative = _safe_rel_path(relative, label=label)
    root = issue_dir.resolve()
    candidate = (root / relative).resolve()
    if root not in candidate.parents:
        raise RenderError(f"{label} path escapes issue directory: {relative}")
    if not candidate.is_file():
        raise RenderError(f"missing {label}: {relative}")
    if candidate.is_symlink():
        raise RenderError(f"{label} may not be a symlink: {relative}")
    return candidate


def _markdown_blocks(markdown: str) -> list[str]:
    return [
        block.strip()
        for block in re.split(r"\n\s*\n", markdown.strip())
        if block.strip()
    ]


def _block_word_count(blocks: list[str]) -> int:
    return sum(len(re.findall(r"\b\w+\b", block)) for block in blocks)


def _group_markdown_blocks(blocks: list[str]) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    for block in blocks:
        if block.startswith("### "):
            if current:
                groups.append(current)
            current = [block]
        else:
            current.append(block)
    if current:
        groups.append(current)
    return groups


def build_deep_dive_layout(markdown: str, issue_dir: pathlib.Path) -> dict[str, str]:
    case_match = CASE_HEADING_RE.search(markdown)
    if case_match is None:
        raise RenderError("deep-dive page requires a case heading")

    lines = markdown[case_match.start() :].splitlines()
    if not lines or not lines[0].strip().startswith("# "):
        raise RenderError("deep-dive page requires a case heading")

    title_index = next(
        (
            index
            for index, line in enumerate(lines[1:], 1)
            if line.strip().startswith("## ")
        ),
        -1,
    )
    if title_index < 0:
        raise RenderError("deep-dive page requires a case title")

    metadata_index = next(
        (
            index
            for index, line in enumerate(lines[title_index + 1 :], title_index + 1)
            if line.strip()
        ),
        -1,
    )
    if metadata_index < 0:
        raise RenderError("deep-dive page requires case metadata")

    case_heading = lines[0].strip()
    case_title = lines[title_index].strip()
    case_metadata = lines[metadata_index].strip()
    header_blocks = [case_heading, case_title, case_metadata]
    body_markdown = "\n".join(lines[metadata_index + 1 :]).strip()
    body_blocks = _markdown_blocks(body_markdown)

    figure_blocks = [block for block in body_blocks if block.startswith("![")]
    text_blocks = [
        block
        for block in body_blocks
        if not block.startswith("![") and block != "---"
    ]
    groups = _group_markdown_blocks(text_blocks)

    protected_index = len(groups)
    for index, group in enumerate(groups):
        heading = group[0].lower() if group and group[0].startswith("### ") else ""
        if heading.startswith(
            (
                "### engineer's notebook",
                "### engineers notebook",
                "### evidence boundary",
                "### sources for this case",
            )
        ):
            protected_index = index
            break

    core_groups = groups[:protected_index]
    protected_groups = groups[protected_index:]
    total_words = _block_word_count([block for group in groups for block in group])
    left_target = max(1, round(total_words * 0.66))
    left_groups: list[list[str]] = []
    right_groups: list[list[str]] = []
    left_words = 0
    for group in core_groups:
        group_words = _block_word_count(group)
        if left_groups and left_words + group_words > left_target:
            right_groups.append(group)
        else:
            left_groups.append(group)
            left_words += group_words
    right_groups.extend(protected_groups)

    def render_groups(items: list[list[str]]) -> str:
        if not items:
            return ""
        markdown_text = "\n\n".join(
            block for group in items for block in group
        )
        return render_markdown_page(markdown_text, issue_dir)

    return {
        "header_html": render_markdown_page("\n\n".join(header_blocks), issue_dir),
        "left_html": render_groups(left_groups),
        "figures_html": (
            render_markdown_page("\n\n".join(figure_blocks), issue_dir)
            if figure_blocks
            else ""
        ),
        "right_html": render_groups(right_groups),
    }


def build_html(
    issue_dir: pathlib.Path,
    meta: IssueMeta,
    pages: list[PageSection],
    template_path: pathlib.Path,
    css_path: pathlib.Path,
) -> str:
    if not template_path.is_file() or not css_path.is_file():
        raise RenderError("magazine template or stylesheet is missing")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    template = environment.from_string(template_path.read_text(encoding="utf-8"))
    rendered_pages: list[dict[str, object]] = []
    for page in pages:
        if page.number == 1:
            rendered_pages.append(
                {
                    "number": page.number,
                    "title": page.title,
                    "mode": "deep-dive",
                    **build_deep_dive_layout(page.markdown, issue_dir),
                }
            )
        else:
            rendered_pages.append(
                {
                    "number": page.number,
                    "title": page.title,
                    "mode": (
                        "short-feature"
                        if is_short_feature_page(page.markdown)
                        else "columns"
                    ),
                    "html": render_markdown_page(page.markdown, issue_dir),
                }
            )
    return template.render(
        issue_id=meta.issue_id,
        issue_number=f"{meta.number:03d}",
        title=meta.title,
        pages=rendered_pages,
        css=css_path.read_text(encoding="utf-8"),
    )


def inspect_pdf_pages(pdf_path: pathlib.Path) -> tuple[tuple[float, float], ...]:
    summary = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if summary.returncode != 0:
        raise RenderError(f"pdfinfo failed: {summary.stderr.strip()}")
    match = re.search(r"^Pages:\s+([0-9]+)\s*$", summary.stdout, re.MULTILINE)
    if not match:
        raise RenderError("pdfinfo did not report page count")
    page_count = int(match.group(1))
    sizes: list[tuple[float, float]] = []
    for page in range(1, page_count + 1):
        detail = subprocess.run(
            ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if detail.returncode != 0:
            raise RenderError(f"pdfinfo failed for page {page}: {detail.stderr.strip()}")
        size = re.search(
            rf"^Page(?:\s+{page})?\s+size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
            detail.stdout,
            re.MULTILINE,
        )
        if not size:
            size = re.search(
                r"^Page size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts",
                detail.stdout,
                re.MULTILINE,
            )
        if not size:
            raise RenderError(f"pdfinfo did not report size for page {page}")
        sizes.append((round(float(size.group(1))), round(float(size.group(2)))))
    return tuple(sizes)


def _diagnose_declared_page_counts(
    issue_dir: pathlib.Path,
    meta: IssueMeta,
    pages: list[PageSection],
    template_root: pathlib.Path,
    output_dir: pathlib.Path,
) -> dict[int, int]:
    counts: dict[int, int] = {}
    for page in pages:
        document = build_html(
            issue_dir,
            meta,
            [page],
            template_root / "magazine.html",
            template_root / "magazine.css",
        )
        diagnostic = output_dir / f".casebook-page-{page.number}.pdf"
        HTML(string=document, base_url=str(issue_dir)).write_pdf(str(diagnostic))
        try:
            counts[page.number] = len(inspect_pdf_pages(diagnostic))
        finally:
            diagnostic.unlink(missing_ok=True)
    return counts


def render_issue(
    issue_dir: pathlib.Path,
    output_pdf: pathlib.Path,
    template_root: pathlib.Path,
) -> RenderResult:
    issue_dir = issue_dir.resolve()
    meta = load_issue_meta(issue_dir / "issue.yml")
    markdown_path = _safe_issue_file(issue_dir, meta.markdown, "issue markdown")
    for snapshot in meta.snapshots:
        _safe_issue_file(issue_dir, snapshot, "snapshot")
    for asset in meta.assets:
        resolve_asset(issue_dir, asset)

    markdown = markdown_path.read_text(encoding="utf-8")
    pages = split_pages(markdown, meta.page_count)
    document = build_html(
        issue_dir,
        meta,
        pages,
        template_root / "magazine.html",
        template_root / "magazine.css",
    )

    output_pdf = output_pdf.resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=".casebook-render-", suffix=".pdf", dir=output_pdf.parent
    )
    os.close(fd)
    temporary = pathlib.Path(name)
    try:
        HTML(string=document, base_url=str(issue_dir)).write_pdf(str(temporary))
        sizes = inspect_pdf_pages(temporary)
        if len(sizes) != meta.page_count:
            section_counts = _diagnose_declared_page_counts(
                issue_dir, meta, pages, template_root, output_pdf.parent
            )
            detail = ", ".join(
                f"PAGE {number}={count}"
                for number, count in sorted(section_counts.items())
            )
            raise RenderError(
                f"rendered page count {len(sizes)} does not match declared "
                f"{meta.page_count}; section page counts: {detail}"
            )
        for index, (width, height) in enumerate(sizes, 1):
            if abs(width - 595.0) > 2 or abs(height - 842.0) > 2:
                raise RenderError(f"page {index} is not A4: {(width, height)}")
        os.replace(temporary, output_pdf)
    finally:
        temporary.unlink(missing_ok=True)

    return RenderResult(
        issue_id=meta.issue_id,
        output_pdf=output_pdf,
        page_count=meta.page_count,
        page_sizes=sizes,
        source_word_count=len(re.findall(r"\b\w+\b", markdown)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render an Engineering Casebook issue")
    parser.add_argument("--issue-dir", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument(
        "--template-root",
        default=pathlib.Path(__file__).parents[1] / "templates",
        type=pathlib.Path,
    )
    args = parser.parse_args(argv)
    try:
        result = render_issue(args.issue_dir, args.output, args.template_root)
    except RenderError as exc:
        parser.exit(1, f"Casebook render failed: {exc}\n")
    print(
        f"{result.issue_id} pages={result.page_count} "
        f"words={result.source_word_count} output={result.output_pdf}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
