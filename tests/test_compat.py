import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from queryminder import compat, settings


class WheelTests(unittest.TestCase):
    def test_multiples_of_120_scroll_three_units_per_notch(self):
        self.assertEqual(compat.wheel_units(-120), 3)
        self.assertEqual(compat.wheel_units(240), -6)

    def test_small_aqua_deltas_are_lines(self):
        self.assertEqual(compat.wheel_units(-2), 2)
        self.assertEqual(compat.wheel_units(1), -1)
        self.assertEqual(compat.wheel_units(0), 0)


@unittest.skipIf(sys.platform == "win32", "flock is the non-Windows path")
class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"APPDATA": tempfile.mkdtemp()})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._release)

    def _release(self):
        if compat._instance_lock is not None:
            compat._instance_lock.close()
            compat._instance_lock = None

    def test_second_instance_refused_until_first_releases(self):
        self.assertTrue(compat.single_instance())
        self.assertFalse(compat.single_instance())
        self._release()
        self.assertTrue(compat.single_instance())


class SettingsPathTests(unittest.TestCase):
    def test_appdata_wins_everywhere(self):
        with mock.patch.dict(os.environ, {"APPDATA": "/x"}):
            self.assertEqual(settings.settings_path(), Path("/x/queryminder/settings.json"))

    def test_macos_default(self):
        env = {k: v for k, v in os.environ.items() if k != "APPDATA"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(
                settings.settings_path(),
                Path.home() / "Library" / "Application Support" / "queryminder" / "settings.json",
            )


class DialogOwnerTests(unittest.TestCase):
    def test_no_parent_on_macos_so_dialogs_are_not_sheets(self):
        from queryminder import picker

        with mock.patch.object(compat, "IS_MAC", True):
            self.assertEqual(picker._owner("root"), {})
        with mock.patch.object(compat, "IS_MAC", False):
            self.assertEqual(picker._owner("root"), {"parent": "root"})


class MacChooseFileTests(unittest.TestCase):
    """Existing files load without a save panel; a new file is only offered on Cancel."""

    def _choose(self, opened="", create=False, saved=""):
        from queryminder import picker

        with mock.patch.object(compat, "IS_MAC", True), \
                mock.patch.object(picker.filedialog, "askopenfilename", return_value=opened), \
                mock.patch.object(picker.filedialog, "asksaveasfilename", return_value=saved) as save, \
                mock.patch.object(picker.messagebox, "askyesno", return_value=create):
            return picker.choose_file(None), save

    def test_existing_file_is_loaded_unchanged_without_save_panel(self):
        path = Path(tempfile.mkdtemp()) / "todos.md"
        body = b"## Today\n\n- [ ] keep me\n\n## Done\n\n"
        path.write_bytes(body)
        chosen, save = self._choose(opened=str(path))
        self.assertEqual(chosen, path)
        save.assert_not_called()
        self.assertEqual(path.read_bytes(), body)

    def test_cancel_and_decline_returns_none(self):
        chosen, save = self._choose()
        self.assertIsNone(chosen)
        save.assert_not_called()

    def test_cancel_then_create_makes_the_file(self):
        path = Path(tempfile.mkdtemp()) / "new.md"
        chosen, _ = self._choose(create=True, saved=str(path))
        self.assertEqual(chosen, path)
        self.assertIn("## Today", path.read_text(encoding="utf-8"))


class OpenPathTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "macOS path")
    def test_uses_open_on_macos(self):
        with mock.patch.object(compat.subprocess, "run") as run:
            compat.open_path("/tmp/a b.md")
        self.assertEqual(run.call_args.args[0], ["open", "/tmp/a b.md"])
