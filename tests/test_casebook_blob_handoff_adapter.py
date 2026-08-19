import base64
import hashlib
import json
import pathlib
import tempfile
import unittest

from scripts.casebook_blob_handoff_adapter import AdapterError, adapt


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BlobAdapterTests(unittest.TestCase):
    def make_issue(self, root: pathlib.Path, *, schema=2):
        issue_rel = 'issues/ISSUE-006-capacity-is-conditional'
        handoff = root / issue_rel / '.handoff'
        handoff.mkdir(parents=True)
        pdf = b'%PDF-1.7\n' + b'p' * 20000 + b'\n%%EOF\n'
        preview = b'\xff\xd8\xff' + b'j' * 5000 + b'\xff\xd9'
        (handoff / 'pdf.bin').write_bytes(pdf)
        (handoff / 'preview.bin').write_bytes(preview)
        if schema == 1:
            manifest = {
                'schema_version': 1,
                'issue_id': 'ISSUE-006',
                'issue_dir': issue_rel,
                'visual_inspection': {'passed': True, 'page_count': 4},
                'artifacts': [],
            }
        else:
            manifest = {
                'schema_version': 2,
                'issue_id': 'ISSUE-006',
                'issue_dir': issue_rel,
                'visual_inspection': {'passed': True, 'page_count': 4},
                'artifacts': [
                    {
                        'role': 'pdf',
                        'output': 'ISSUE-006-capacity-is-conditional.pdf',
                        'media_type': 'application/pdf',
                        'byte_size': len(pdf),
                        'sha256': sha(pdf),
                        'input': 'pdf.bin',
                    },
                    {
                        'role': 'preview',
                        'output': 'preview.jpg',
                        'media_type': 'image/jpeg',
                        'byte_size': len(preview),
                        'sha256': sha(preview),
                        'input': 'preview.bin',
                    },
                ],
            }
        path = handoff / 'manifest.json'
        path.write_text(json.dumps(manifest), encoding='utf-8')
        return path, pdf, preview

    def test_schema1_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, _, _ = self.make_issue(root, schema=1)
            before = path.read_text(encoding='utf-8')
            self.assertFalse(adapt(root, path))
            self.assertEqual(path.read_text(encoding='utf-8'), before)

    def test_schema2_adapts_raw_blobs_to_strict_v1_chunks(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, pdf, preview = self.make_issue(root)
            self.assertTrue(adapt(root, path))
            manifest = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['schema_version'], 1)
            self.assertEqual(set(manifest), {'schema_version','issue_id','issue_dir','visual_inspection','artifacts'})
            by_role = {a['role']: a for a in manifest['artifacts']}
            self.assertEqual(set(by_role['pdf']), {'role','output','media_type','byte_size','sha256','chunks'})
            self.assertEqual(set(by_role['preview']), {'role','output','media_type','byte_size','sha256','chunks'})
            handoff = path.parent
            for role, expected in [('pdf', pdf), ('preview', preview)]:
                names = by_role[role]['chunks']
                self.assertTrue(names)
                self.assertTrue(all((handoff / n).stat().st_size <= 16000 for n in names))
                encoded = ''.join((handoff / n).read_text(encoding='ascii') for n in names)
                self.assertEqual(base64.b64decode(encoded, validate=True), expected)
            self.assertTrue((handoff / 'pdf.bin').is_file())
            self.assertTrue((handoff / 'preview.bin').is_file())

    def test_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, _, _ = self.make_issue(root)
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['artifacts'][0]['sha256'] = '0' * 64
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(AdapterError, 'sha256 mismatch'):
                adapt(root, path)

    def test_rejects_symlink_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, _, _ = self.make_issue(root)
            target = path.parent / 'real.bin'
            target.write_bytes((path.parent / 'pdf.bin').read_bytes())
            (path.parent / 'pdf.bin').unlink()
            (path.parent / 'pdf.bin').symlink_to(target)
            with self.assertRaisesRegex(AdapterError, 'symlink'):
                adapt(root, path)

    def test_rejects_extra_artifact_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, _, _ = self.make_issue(root)
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['artifacts'][0]['surprise'] = True
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(AdapterError, 'keys invalid'):
                adapt(root, path)

    def test_rejects_role_input_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            path, _, _ = self.make_issue(root)
            manifest = json.loads(path.read_text(encoding='utf-8'))
            manifest['artifacts'][0]['input'] = 'preview.bin'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(AdapterError, 'input filename'):
                adapt(root, path)


if __name__ == '__main__':
    unittest.main()
