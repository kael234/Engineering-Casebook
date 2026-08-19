import base64
import json
import pathlib
import tempfile
import unittest

from scripts.casebook_handoff_rescue import (
    RescueError,
    build_manifest,
    decode_pdf_chunks,
    ordered_chunks,
    write_preview_chunks,
)


class RescueTests(unittest.TestCase):
    def test_orders_complete_pdf_chunk_sequence(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            for n in (2, 1, 3):
                (root / f"pdf.part{n:03d}.b64").write_text("QQ==", encoding="ascii")
            self.assertEqual(
                [p.name for p in ordered_chunks(root, "pdf")],
                ["pdf.part001.b64", "pdf.part002.b64", "pdf.part003.b64"],
            )

    def test_rejects_gap_in_pdf_chunk_sequence(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "pdf.part001.b64").write_text("QQ==", encoding="ascii")
            (root / "pdf.part003.b64").write_text("QQ==", encoding="ascii")
            with self.assertRaises(RescueError):
                ordered_chunks(root, "pdf")

    def test_decodes_complete_pdf(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            raw = b"%PDF-1.7\nhello\n%%EOF\n"
            encoded = base64.b64encode(raw).decode("ascii")
            (root / "pdf.part001.b64").write_text(encoded[:12], encoding="ascii")
            (root / "pdf.part002.b64").write_text(encoded[12:], encoding="ascii")
            self.assertEqual(decode_pdf_chunks(ordered_chunks(root, "pdf")), raw)

    def test_preview_chunks_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            raw = b"\xff\xd8\xff" + b"x" * 25000 + b"\xff\xd9"
            names = write_preview_chunks(root, raw, max_chars=16000)
            encoded = "".join((root / n).read_text(encoding="ascii") for n in names)
            self.assertEqual(base64.b64decode(encoded), raw)
            self.assertTrue(all((root / n).stat().st_size <= 16000 for n in names))

    def test_manifest_records_exact_hashes_and_chunk_names(self):
        pdf = b"%PDF-1.7\nhello\n%%EOF\n"
        preview = b"\xff\xd8\xffx\xff\xd9"
        manifest = build_manifest(
            issue_id="ISSUE-007",
            issue_dir="issues/ISSUE-007-give-it-a-path",
            page_count=4,
            pdf_output="ISSUE-007-give-it-a-path.pdf",
            pdf_bytes=pdf,
            preview_bytes=preview,
            pdf_chunks=["pdf.part001.b64"],
            preview_chunks=["preview.part001.b64"],
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["visual_inspection"], {"passed": True, "page_count": 4})
        self.assertEqual(manifest["artifacts"][0]["byte_size"], len(pdf))
        self.assertEqual(manifest["artifacts"][0]["chunks"], ["pdf.part001.b64"])
        self.assertEqual(manifest["artifacts"][1]["byte_size"], len(preview))


class RescueIntegrationTests(unittest.TestCase):
    def test_rescue_builds_preview_and_manifest_from_existing_pdf_chunks(self):
        from scripts.casebook_handoff_rescue import rescue

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            issue_dir = "issues/ISSUE-007-give-it-a-path"
            issue = root / issue_dir
            handoff = issue / ".handoff"
            handoff.mkdir(parents=True)
            (issue / "assets").mkdir()
            (issue / "snapshots").mkdir()
            (issue / "issue.md").write_text("issue", encoding="utf-8")
            (issue / "snapshots/cases.md").write_text("cases", encoding="utf-8")
            (issue / "snapshots/sources.yml").write_text("sources", encoding="utf-8")
            (issue / "assets/a.svg").write_text("<svg/>", encoding="utf-8")
            (issue / "issue.yml").write_text(
                "schema_version: 1\nid: ISSUE-007\npage_count: 3\n"
                "slots:\n  - {role: deep_dive, case_id: CASE-028}\n"
                "markdown: issue.md\nsnapshots:\n  cases: snapshots/cases.md\n"
                "  sources: snapshots/sources.yml\nassets:\n  - assets/a.svg\n",
                encoding="utf-8",
            )
            raw = base64.b64decode(
                "JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA1OTUuMjggODQxLjg5IF0gL1BhcmVudCA2IDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BERiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJhbnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9QYWdlTW9kZSAvVXNlTm9uZSAvUGFnZXMgNiAwIFIgL1R5cGUgL0NhdGFsb2cKPj4KZW5kb2JqCjUgMCBvYmoKPDwKL0F1dGhvciAoYW5vbnltb3VzKSAvQ3JlYXRpb25EYXRlIChEOjIwMjYwODE5MTE1ODQ2KzAwJzAwJykgL0NyZWF0b3IgKGFub255bW91cykgL0tleXdvcmRzICgpIC9Nb2REYXRlIChEOjIwMjYwODE5MTE1ODQ2KzAwJzAwJykgL1Byb2R1Y2VyIChSZXBvcnRMYWIgUERGIExpYnJhcnkgLSBcKG9wZW5zb3VyY2VcKSkgCiAgL1N1YmplY3QgKHVuc3BlY2lmaWVkKSAvVGl0bGUgKHVudGl0bGVkKSAvVHJhcHBlZCAvRmFsc2UKPj4KZW5kb2JqCjYgMCBvYmoKPDwKL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9QYWdlcwo+PgplbmRvYmoKNyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUgL0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCAxMTIKPj4Kc3RyZWFtCkdhcFFoMEU9RiwwVVxIM1RccE5ZVF5RS2s/dGM+SVAsO1cjVTFeMjNpaFBFTV8/Q1c0S0lTaTwhWzdgI09CX3F1a0paQjBWIzouLEtxZClWak8uIl1QMThKKDluZVpbS2IsaHQtM1oiJWhtWEFofj5lbmRzdHJlYW0KZW5kb2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA2MSAwMDAwMCBuIAowMDAwMDAwMDkyIDAwMDAwIG4gCjAwMDAwMDAxOTkgMDAwMDAgbiAKMDAwMDAwMDM5OCAwMDAwMCBuIAowMDAwMDAwNDY2IDAwMDAwIG4gCjAwMDAwMDA3MjcgMDAwMDAgbiAKMDAwMDAwMDc4NiAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9JRCAKWzxjNDY2ZjE0ZDU1MmRlYmYyYWU5NDk4ODI2OTMxOWM1Mz48YzQ2NmYxNGQ1NTJkZWJmMmFlOTQ5ODgyNjkzMTljNTM+XQolIFJlcG9ydExhYiBnZW5lcmF0ZWQgUERGIGRvY3VtZW50IC0tIGRpZ2VzdCAob3BlbnNvdXJjZSkKCi9JbmZvIDUgMCBSCi9Sb290IDQgMCBSCi9TaXplIDgKPj4Kc3RhcnR4cmVmCjk4OAolJUVPRgo="
            )
            encoded = base64.b64encode(raw).decode("ascii")
            for index, start in enumerate(range(0, len(encoded), 16000), 1):
                (handoff / f"pdf.part{index:03d}.b64").write_text(
                    encoded[start:start + 16000], encoding="ascii"
                )
            (handoff / "rescue-request.json").write_text(
                json.dumps({"visual_inspection_passed": True}), encoding="utf-8"
            )

            self.assertEqual(
                rescue(root, issue_dir, "publish/issue-007-2026-08-19"),
                "ISSUE-007",
            )
            self.assertFalse((handoff / "rescue-request.json").exists())
            self.assertTrue((handoff / "manifest.json").is_file())
            manifest = json.loads((handoff / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["issue_id"], "ISSUE-007")
            self.assertTrue(manifest["artifacts"][1]["chunks"])


if __name__ == "__main__":
    unittest.main()
