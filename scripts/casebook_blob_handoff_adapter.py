from __future__ import annotations

import base64
import hashlib
import json
import pathlib
import re

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_CHUNK_CHARS = 16000
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
ISSUE_DIR_RE = re.compile(r'^issues/ISSUE-([0-9]{3})-[a-z0-9-]+$')
TOP_KEYS = {'schema_version', 'issue_id', 'issue_dir', 'visual_inspection', 'artifacts'}
VISUAL_KEYS = {'passed', 'page_count'}
ARTIFACT_V2_KEYS = {'role', 'output', 'media_type', 'byte_size', 'sha256', 'input'}


class AdapterError(RuntimeError):
    pass


def _require_exact_keys(obj: dict, expected: set[str], label: str) -> None:
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise AdapterError(f'{label} keys invalid; missing={missing} extra={extra}')


def _safe_input_name(role: str, name: object) -> str:
    expected = f'{role}.bin'
    if not isinstance(name, str) or name != expected:
        raise AdapterError(f'invalid input filename for {role}; expected {expected}')
    return name


def _verify_raw(role: str, path: pathlib.Path, artifact: dict) -> bytes:
    if path.is_symlink():
        raise AdapterError(f'{role} input may not be a symlink')
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AdapterError(f'cannot read {role} input: {exc}') from exc
    expected_size = artifact['byte_size']
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        raise AdapterError('byte_size must be an integer')
    if expected_size <= 0 or expected_size > MAX_ARTIFACT_BYTES:
        raise AdapterError('byte_size outside allowed range')
    if len(raw) != expected_size:
        raise AdapterError(f'byte size mismatch for {role}: expected {expected_size}, got {len(raw)}')
    expected_hash = artifact['sha256']
    if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
        raise AdapterError('invalid sha256')
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_hash:
        raise AdapterError(f'sha256 mismatch for {role}')
    if role == 'pdf':
        if artifact['media_type'] != 'application/pdf' or not artifact['output'].endswith('.pdf'):
            raise AdapterError('invalid PDF output/media type')
        if not raw.startswith(b'%PDF-') or b'%%EOF' not in raw[-1024:]:
            raise AdapterError('PDF magic/trailer is invalid')
    elif role == 'preview':
        if artifact['media_type'] != 'image/jpeg' or not artifact['output'].lower().endswith(('.jpg', '.jpeg')):
            raise AdapterError('invalid preview output/media type')
        if not raw.startswith(b'\xff\xd8\xff') or not raw.endswith(b'\xff\xd9'):
            raise AdapterError('JPEG magic/trailer is invalid')
    else:
        raise AdapterError('invalid artifact role')
    return raw


def _write_chunks(handoff: pathlib.Path, role: str, raw: bytes) -> list[str]:
    for old in handoff.glob(f'{role}.part*.b64'):
        old.unlink()
    encoded = base64.b64encode(raw).decode('ascii')
    names: list[str] = []
    for index, start in enumerate(range(0, len(encoded), MAX_CHUNK_CHARS), 1):
        name = f'{role}.part{index:03d}.b64'
        (handoff / name).write_text(encoded[start:start + MAX_CHUNK_CHARS], encoding='ascii')
        names.append(name)
    return names


def adapt(repo_root: pathlib.Path, manifest_path: pathlib.Path) -> bool:
    root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f'cannot read manifest: {exc}') from exc
    if not isinstance(manifest, dict):
        raise AdapterError('manifest must be an object')
    schema = manifest.get('schema_version')
    if schema == 1:
        return False
    if type(schema) is not int or schema != 2:
        raise AdapterError('unsupported schema_version')
    _require_exact_keys(manifest, TOP_KEYS, 'manifest')

    issue_id = manifest['issue_id']
    issue_dir = manifest['issue_dir']
    if not isinstance(issue_id, str) or not re.fullmatch(r'ISSUE-[0-9]{3}', issue_id):
        raise AdapterError('invalid issue_id')
    if not isinstance(issue_dir, str):
        raise AdapterError('issue_dir must be a string')
    match = ISSUE_DIR_RE.fullmatch(issue_dir)
    if not match or issue_id != f'ISSUE-{match.group(1)}':
        raise AdapterError('issue_dir does not match issue_id')
    issue_path = (root / issue_dir).resolve()
    issues_root = (root / 'issues').resolve()
    if issues_root not in issue_path.parents:
        raise AdapterError('issue_dir escapes issues root')
    expected_manifest = issue_path / '.handoff' / 'manifest.json'
    if manifest_path != expected_manifest.resolve():
        raise AdapterError('manifest path does not match issue_dir')

    visual = manifest['visual_inspection']
    if not isinstance(visual, dict):
        raise AdapterError('visual_inspection must be an object')
    _require_exact_keys(visual, VISUAL_KEYS, 'visual_inspection')
    if visual['passed'] is not True:
        raise AdapterError('visual inspection must explicitly pass')
    if type(visual['page_count']) is not int or visual['page_count'] not in {3, 4}:
        raise AdapterError('visual page_count must be integer 3 or 4')

    artifacts = manifest['artifacts']
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise AdapterError('artifacts must contain exactly PDF and preview')
    by_role: dict[str, tuple[dict, bytes]] = {}
    handoff = manifest_path.parent
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise AdapterError('artifact must be an object')
        _require_exact_keys(artifact, ARTIFACT_V2_KEYS, 'artifact')
        role = artifact['role']
        if role not in {'pdf', 'preview'} or role in by_role:
            raise AdapterError('artifacts must contain exactly one PDF and one preview')
        input_name = _safe_input_name(role, artifact['input'])
        raw = _verify_raw(role, handoff / input_name, artifact)
        by_role[role] = (artifact, raw)
    if set(by_role) != {'pdf', 'preview'}:
        raise AdapterError('artifacts must contain exactly one PDF and one preview')

    v1_artifacts = []
    for role in ('pdf', 'preview'):
        artifact, raw = by_role[role]
        chunk_names = _write_chunks(handoff, role, raw)
        v1_artifacts.append({
            'role': role,
            'output': artifact['output'],
            'media_type': artifact['media_type'],
            'byte_size': artifact['byte_size'],
            'sha256': artifact['sha256'],
            'chunks': chunk_names,
        })
    v1 = {
        'schema_version': 1,
        'issue_id': issue_id,
        'issue_dir': issue_dir,
        'visual_inspection': visual,
        'artifacts': v1_artifacts,
    }
    manifest_path.write_text(json.dumps(v1, indent=2) + '\n', encoding='utf-8')
    return True
