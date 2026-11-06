import os
import tempfile
import unittest
from pathlib import Path

from queryminder import settings, store


class ChooseFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_new_file_gets_sections(self):
        p = self.dir / "sub" / "my.md"
        self.assertEqual(store.inspect_file(p), store.NEW)
        store.initialise_file(p)
        self.assertEqual(store.inspect_file(p), store.OK)
        self.assertIn("## Rest", p.read_text(encoding="utf-8"))

    def test_empty_file(self):
        p = self.dir / "e.md"
        p.write_text("", encoding="utf-8")
        self.assertEqual(store.inspect_file(p), store.EMPTY)

    def test_incomplete_file_gets_missing_sections_only(self):
        p = self.dir / "n.md"
        p.write_bytes(b"\xef\xbb\xbf# Notes\r\n\r\n## Today\r\n\r\n- [ ] x\r\n")
        self.assertEqual(store.inspect_file(p), store.INCOMPLETE)
        store.add_missing_sections(p)
        raw = p.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf# Notes\r\n\r\n## Today\r\n\r\n- [ ] x\r\n"))
        self.assertEqual(store.inspect_file(p), store.OK)


class ResolveTests(unittest.TestCase):
    def test_not_configured(self):
        old = os.environ.pop("QUERYMINDER_FILE", None)
        try:
            self.assertIsNone(settings.resolve_todo_file(None, {}))
            self.assertEqual(settings.resolve_todo_file(None, {"file": "a.md"}), "a.md")
            self.assertEqual(settings.resolve_todo_file("b.md", {"file": "a.md"}), "b.md")
        finally:
            if old is not None:
                os.environ["QUERYMINDER_FILE"] = old


if __name__ == "__main__":
    unittest.main()
