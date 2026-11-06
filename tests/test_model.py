import datetime as dt
import tempfile
import unittest
from pathlib import Path

from queryminder import model
from queryminder.store import TodoFile

SAMPLE = """---
title: To-dos
updated: 2026-10-20
---

# To-dos

Intro. New items go at the top of Today or Rest.

## Today

- [ ] remote hermes / to-do things
- [ ] obsidian wiki
    - [ ] sub one
- [x] already ticked here

## Rest

- [ ] Check ignite

## Done

(In the original order, most recent at the top.)

- [x] L&L
    - [x] Add token cost
- [x] different hermes profile

## Where the items live in the wiki
stuff
"""


class ParseTests(unittest.TestCase):
    def test_pending_today_only_unchecked_top_level(self):
        items = model.pending_today(SAMPLE)
        self.assertEqual([i.text for i in items], ["remote hermes / to-do things", "obsidian wiki"])
        self.assertEqual(items[1].children, ("    - [ ] sub one",))

    def test_missing_section(self):
        with self.assertRaises(model.SectionNotFound):
            model.pending_today("# nothing\n")

    def test_heading_in_code_fence_ignored(self):
        text = "```\n## Today\n- [ ] fake\n```\n## Today\n- [ ] real\n## Done\n"
        self.assertEqual([i.text for i in model.pending_today(text)], ["real"])

    def test_today_section_stops_at_next_heading(self):
        self.assertNotIn("Check ignite", [i.text for i in model.pending_today(SAMPLE)])


class EditTests(unittest.TestCase):
    def test_complete_moves_block_to_top_of_done(self):
        new, completion = model.complete_item(SAMPLE, "obsidian wiki")
        self.assertEqual([i.text for i in model.pending_today(new)], ["remote hermes / to-do things"])
        done = new.split("## Done")[1]
        self.assertIn("top.)\n\n- [x] obsidian wiki\n    - [x] sub one\n- [x] L&L", done)
        self.assertEqual(completion.original_block, ("- [ ] obsidian wiki", "    - [ ] sub one"))
        self.assertIn("- [x] already ticked here\n\n## Rest", new)  # surroundings untouched

    def test_complete_unknown_item(self):
        with self.assertRaises(model.ItemNotFound):
            model.complete_item(SAMPLE, "nope")

    def test_undo_restores_original_block(self):
        new, completion = model.complete_item(SAMPLE, "obsidian wiki")
        restored = model.undo_completion(new, completion)
        self.assertEqual(
            [i.text for i in model.pending_today(restored)], ["obsidian wiki", "remote hermes / to-do things"]
        )
        self.assertNotIn("[x] obsidian wiki", restored)

    def test_add_goes_to_top_of_today(self):
        new = model.add_item(SAMPLE, "  new\nthing  ")
        self.assertEqual(model.pending_today(new)[0].text, "new thing")
        self.assertIn("## Today\n\n- [ ] new thing\n- [ ] remote", new)

    def test_add_to_empty_today(self):
        text = "## Today\n\n## Done\n"
        new = model.add_item(text, "first")
        self.assertEqual(new, "## Today\n\n- [ ] first\n\n## Done\n")

    def test_complete_into_empty_done(self):
        text = "## Today\n- [ ] a\n\n## Done\n"
        new, _ = model.complete_item(text, "a")
        self.assertEqual(new, "## Today\n\n## Done\n\n- [x] a\n")

    def test_emptying_today_leaves_single_blank_line(self):
        text = "## Today\n\n- [ ] a\n\n## Done\n"
        new, _ = model.complete_item(text, "a")
        self.assertTrue(new.startswith("## Today\n\n## Done\n"))
        self.assertTrue(model.add_item(new, "b").startswith("## Today\n\n- [ ] b\n\n## Done\n"))

    def test_today_items_and_completion_in_done(self):
        self.assertEqual([i.done for i in model.today_items(SAMPLE)], [False, False, True])
        new, completion = model.complete_item(SAMPLE, "obsidian wiki")
        self.assertTrue(model.completion_in_done(new, completion))
        self.assertFalse(model.completion_in_done(SAMPLE, completion))

    def test_uncheck_today_item_in_place(self):
        new = model.uncheck_today_item(SAMPLE, "already ticked here")
        self.assertIn("- [ ] already ticked here\n\n## Rest", new)
        with self.assertRaises(model.ItemNotFound):
            model.uncheck_today_item(SAMPLE, "obsidian wiki")

    def test_add_rejects_blank(self):
        with self.assertRaises(model.TodoError):
            model.add_item(SAMPLE, "   ")

    def test_touch_updated(self):
        self.assertIn("updated: 2030-01-02", model.touch_updated(SAMPLE, "2030-01-02"))
        self.assertEqual(model.touch_updated("no frontmatter\nupdated: x", "2030"), "no frontmatter\nupdated: x")


D = dt.date
TODAY_D = D(2026, 10, 23)  # a Friday

V2 = """---
updated: 2026-10-20
---

## Today

- [ ] Core assets
- [ ] Jev
- [x] ticked here

## Rest

- [ ] Ignite
- [ ] Jev
- [ ] Talk to Gene \u23f3 2026-10-28
    - [ ] prep notes
- [ ] Search doctor \u23f3 2026-10-23
- [ ] Old thing \u23f3 2026-10-01
- [ ] Bad date \u23f3 2026-13-45

## Done

(note)

- [x] Answer mando
- [x] L&L
    - [x] Add clay
"""


def texts(items):
    return [i.text for i in items]


def section(text, name):
    """Raw lines of a section body (between its heading and the next ## heading)."""
    body = text.split(f"## {name}\n", 1)[1]
    return body.split("\n## ", 1)[0]


class RestParseTests(unittest.TestCase):
    def test_rest_items_strip_marker_and_parse_date(self):
        items = model.rest_items(V2)
        self.assertEqual(
            texts(items), ["Ignite", "Jev", "Talk to Gene", "Search doctor", "Old thing", "Bad date \u23f3 2026-13-45"]
        )
        self.assertEqual(items[2].scheduled, D(2026, 10, 28))
        self.assertEqual(items[2].children, ("    - [ ] prep notes",))
        self.assertEqual(items[2].section, model.REST)
        self.assertIsNone(items[5].scheduled)  # invalid date is not a marker

    def test_no_rest_section(self):
        self.assertEqual(model.rest_items("## Today\n- [ ] a\n## Done\n"), [])

    def test_marker_in_today_is_plain_text(self):
        text = "## Today\n- [ ] a \u23f3 2026-10-01\n## Rest\n## Done\n"
        self.assertEqual(texts(model.today_items(text)), ["a \u23f3 2026-10-01"])
        self.assertEqual(model.promote_due(text, TODAY_D), (text, []))

    def test_due_items(self):
        self.assertEqual(texts(model.due_items(V2, TODAY_D)), ["Search doctor", "Old thing"])

    def test_match_key(self):
        self.assertEqual(model.match_key("  Talk  to GENE \u23f3 2026-10-28"), "talk to gene")


class MoveScheduleTests(unittest.TestCase):
    def test_move_today_to_rest_and_back(self):
        new = model.move_item(V2, "Core assets", model.TODAY, model.REST)
        self.assertEqual(texts(model.pending_today(new)), ["Jev"])
        self.assertEqual(texts(model.rest_items(new))[0], "Core assets")
        back = model.move_item(new, "Core assets", model.REST, model.TODAY)
        self.assertEqual(texts(model.pending_today(back)), ["Core assets", "Jev"])

    def test_move_identifies_by_section(self):
        new = model.move_item(V2, "Jev", model.REST, model.TODAY)  # the Rest copy
        self.assertEqual(texts(model.pending_today(new)), ["Jev", "Core assets", "Jev"])
        self.assertNotIn("Jev", texts(model.rest_items(new)))

    def test_move_to_today_strips_marker_and_keeps_children(self):
        new = model.move_item(V2, "Talk to Gene", model.REST, model.TODAY)
        self.assertIn("## Today\n\n- [ ] Talk to Gene\n    - [ ] prep notes\n- [ ] Core assets", new)
        self.assertNotIn("2026-10-28", new)

    def test_move_missing_item(self):
        with self.assertRaises(model.ItemNotFound):
            model.move_item(V2, "nope", model.TODAY, model.REST)

    def test_snooze_today_item(self):
        new = model.schedule_item(V2, "Core assets", model.TODAY, D(2026, 10, 26), TODAY_D)
        self.assertIn("## Rest\n\n- [ ] Core assets \u23f3 2026-10-26\n- [ ] Ignite", new)
        self.assertNotIn("Core assets", texts(model.pending_today(new)))

    def test_reschedule_rest_item_in_place(self):
        new = model.schedule_item(V2, "Talk to Gene", model.REST, D(2026, 11, 2), TODAY_D)
        self.assertIn("- [ ] Jev\n- [ ] Talk to Gene \u23f3 2026-11-02\n    - [ ] prep notes", new)
        new = model.schedule_item(V2, "Ignite", model.REST, D(2026, 11, 2), TODAY_D)
        self.assertIn("## Rest\n\n- [ ] Ignite \u23f3 2026-11-02\n", new)

    def test_snooze_to_today_or_past_means_move_to_today(self):
        new = model.schedule_item(V2, "Ignite", model.REST, TODAY_D, TODAY_D)
        self.assertEqual(texts(model.pending_today(new))[0], "Ignite")
        self.assertEqual(model.schedule_item(V2, "Jev", model.TODAY, TODAY_D, TODAY_D), V2)

    def test_clear_schedule(self):
        new = model.clear_schedule(V2, "Talk to Gene")
        self.assertIn("- [ ] Talk to Gene\n    - [ ] prep notes", new)
        self.assertIsNone(model.rest_items(new)[2].scheduled)

    def test_promote_due_keeps_order_and_strips_markers(self):
        new, moved = model.promote_due(V2, TODAY_D)
        self.assertEqual(moved, ["Search doctor", "Old thing"])
        self.assertIn("## Today\n\n- [ ] Search doctor\n- [ ] Old thing\n- [ ] Core assets", new)
        self.assertEqual(
            texts(model.rest_items(new)), ["Ignite", "Jev", "Talk to Gene", "Bad date \u23f3 2026-13-45"]
        )
        self.assertEqual(model.promote_due(new, TODAY_D), (new, []))  # idempotent
        later, moved = model.promote_due(new, D(2026, 10, 28))
        self.assertEqual(moved, ["Talk to Gene"])
        self.assertIn("- [ ] Talk to Gene\n    - [ ] prep notes\n- [ ] Search doctor", later)

    def test_promote_emptying_rest(self):
        text = "## Today\n\n## Rest\n\n- [ ] a \u23f3 2026-10-01\n\n## Done\n"
        new, _ = model.promote_due(text, TODAY_D)
        self.assertEqual(new, "## Today\n\n- [ ] a\n\n## Rest\n\n## Done\n")


class CompleteFromRestTests(unittest.TestCase):
    def test_complete_rest_item_drops_marker_undo_restores_it(self):
        new, c = model.complete_item(V2, "Talk to Gene", model.REST)
        self.assertEqual(c.section, model.REST)
        self.assertIn("(note)\n\n- [x] Talk to Gene\n    - [x] prep notes\n- [x] Answer mando", new)
        back = model.undo_completion(new, c)
        self.assertIn("## Rest\n\n- [ ] Talk to Gene \u23f3 2026-10-28\n    - [ ] prep notes\n- [ ] Ignite", back)
        self.assertNotIn("[x] Talk to Gene", back)

    def test_undo_today_completion_goes_to_today(self):
        new, c = model.complete_item(V2, "Jev")
        self.assertEqual(c.section, model.TODAY)
        back = model.undo_completion(new, c)
        self.assertEqual(texts(model.pending_today(back)), ["Jev", "Core assets"])
        self.assertEqual(texts(model.rest_items(back))[1], "Jev")

    def test_undo_rest_completion_without_rest_falls_back_to_today(self):
        new, c = model.complete_item(V2, "Ignite", model.REST)
        no_rest = new.replace("## Rest", "## Later")
        self.assertEqual(texts(model.pending_today(model.undo_completion(no_rest, c)))[0], "Ignite")


class AddToTodayTests(unittest.TestCase):
    def test_exists_in_today(self):
        self.assertEqual(model.add_to_today(V2, " core  ASSETS "), (V2, "exists", None))

    def test_unchecks_ticked_in_today(self):
        new, outcome, _ = model.add_to_today(V2, "Ticked here")
        self.assertEqual(outcome, "unchecked")
        self.assertIn("- [ ] ticked here", new)

    def test_pulls_from_rest_with_marker_removed(self):
        new, outcome, _ = model.add_to_today(V2, "talk to gene")
        self.assertEqual(outcome, "from_rest")
        self.assertIn("## Today\n\n- [ ] Talk to Gene\n    - [ ] prep notes\n", new)
        self.assertEqual(new.count("Talk to Gene"), 1)

    def test_rest_wins_over_done(self):
        text = V2.replace("- [x] Answer mando", "- [x] Ignite")
        new, outcome, _ = model.add_to_today(text, "Ignite")
        self.assertEqual(outcome, "from_rest")
        self.assertIn("- [x] Ignite", new)  # the Done copy is not deleted

    def test_undoes_completion_made_today(self):
        done, c = model.complete_item(V2, "Talk to Gene", model.REST)
        new, outcome, which = model.add_to_today(done, "Talk to Gene", [c])
        self.assertEqual((outcome, which), ("undone", c))
        self.assertIn("## Today\n\n- [ ] Talk to Gene\n    - [ ] prep notes\n", new)  # to Today, no marker
        self.assertNotIn("Talk to Gene", section(new, "Done"))

    def test_reopens_from_done_unticking_children(self):
        new, outcome, _ = model.add_to_today(V2, "l&l")
        self.assertEqual(outcome, "from_done")
        self.assertIn("## Today\n\n- [ ] L&L\n    - [ ] Add clay\n- [ ] Core assets", new)
        self.assertNotIn("L&L", section(new, "Done"))

    def test_new_item(self):
        new, outcome, _ = model.add_to_today(V2, "brand new")
        self.assertEqual(outcome, "added")
        self.assertEqual(texts(model.pending_today(new))[0], "brand new")

    def test_no_fuzzy_matching(self):
        self.assertEqual(model.add_to_today(V2, "Talk")[1], "added")


class RenameDeleteTests(unittest.TestCase):
    def test_rename_keeps_children_and_marker(self):
        new = model.rename_item(V2, model.REST, "Talk to Gene", "  Talk to  Gene re SLP ")
        self.assertIn("- [ ] Talk to Gene re SLP \u23f3 2026-10-28\n    - [ ] prep notes", new)

    def test_rename_today_item_by_section(self):
        new = model.rename_item(V2, model.TODAY, "Jev", "Jev call")
        self.assertEqual(texts(model.pending_today(new)), ["Core assets", "Jev call"])
        self.assertIn("Jev", texts(model.rest_items(new)))

    def test_rename_rejects_empty_and_missing(self):
        with self.assertRaises(model.TodoError):
            model.rename_item(V2, model.TODAY, "Jev", "  ")
        with self.assertRaises(model.ItemNotFound):
            model.rename_item(V2, model.TODAY, "Ignite", "x")

    def test_delete_with_children(self):
        new = model.delete_item(V2, model.REST, "Talk to Gene")
        self.assertNotIn("Gene", new)
        self.assertNotIn("prep notes", new)
        self.assertIn("- [ ] Jev\n- [ ] Search doctor", new)

    def test_delete_ticked_today_row_not_allowed(self):
        with self.assertRaises(model.ItemNotFound):
            model.delete_item(V2, model.TODAY, "ticked here")


class CompletionDateTests(unittest.TestCase):
    def test_complete_stamps_date_and_undo_restores(self):
        new, c = model.complete_item(V2, "Core assets", model.TODAY, D(2026, 10, 23))
        self.assertIn("- [x] Core assets ✅ 2026-10-23", new)
        self.assertEqual(model.undo_completion(new, c), V2)

    def test_no_date_without_today(self):
        new, _ = model.complete_item(V2, "Core assets")
        self.assertNotIn("✅", new)

    def test_reopen_from_done_strips_date(self):
        new, _ = model.complete_item(V2, "Core assets", model.TODAY, D(2026, 10, 23))
        again, outcome, _ = model.add_to_today(new, "Core assets")
        self.assertEqual(outcome, "from_done")
        self.assertIn("- [ ] Core assets", again)
        self.assertNotIn("✅", again)


class ReorderTests(unittest.TestCase):
    def today_texts(self, text):
        return [i.text for i in model.pending_today(text)]

    def rest_texts(self, text):
        return [i.text for i in model.rest_items(text)]

    def test_move_down_and_up_in_today(self):
        new = model.reorder_item(V2, model.TODAY, "Core assets", 0, 1)
        self.assertEqual(self.today_texts(new), ["Jev", "Core assets"])
        self.assertIn("- [x] ticked here", new)
        back = model.reorder_item(new, model.TODAY, "Core assets", 1, 0)
        self.assertEqual(back, V2)

    def test_rest_keeps_markers_and_children(self):
        new = model.reorder_item(V2, model.REST, "Talk to Gene", 2, 0)
        self.assertEqual(self.rest_texts(new)[0], "Talk to Gene")
        self.assertIn("- [ ] Talk to Gene \u23f3 2026-10-28\n    - [ ] prep notes\n- [ ] Ignite", new)
        last = model.reorder_item(V2, model.REST, "Ignite", 0, 5)
        self.assertEqual(self.rest_texts(last)[-1], "Ignite")
        self.assertEqual(len(self.rest_texts(last)), len(self.rest_texts(V2)))

    def test_only_section_changes_and_no_loss(self):
        new = model.reorder_item(V2, model.REST, "Ignite", 0, 3)
        self.assertEqual(sorted(new.split("\n")), sorted(V2.split("\n")))
        self.assertEqual(new.split("## Done")[1], V2.split("## Done")[1])

    def test_same_position_is_noop(self):
        self.assertEqual(model.reorder_item(V2, model.TODAY, "Jev", 1, 1), V2)

    def test_stale_position_rejected(self):
        with self.assertRaises(model.ItemNotFound):
            model.reorder_item(V2, model.TODAY, "Jev", 0, 1)
        with self.assertRaises(model.ItemNotFound):
            model.reorder_item(V2, model.TODAY, "Jev", 9, 0)
        with self.assertRaises(model.TodoError):
            model.reorder_item(V2, model.TODAY, "Core assets", 0, 9)


class NewFileTests(unittest.TestCase):
    def test_template_has_three_sections(self):
        for name in (model.TODAY, model.REST, model.DONE):
            self.assertTrue(model.has_section(model.NEW_FILE_TEMPLATE, name))
        text, _ = model.complete_item(model.add_item(model.NEW_FILE_TEMPLATE, "a"), "a")
        self.assertIn("- [x] a", text)

    def test_ensure_sections_appends_only_missing(self):
        src = "# Notes\n\n## Today\n\n- [ ] x\n"
        out = model.ensure_sections(src)
        self.assertTrue(out.startswith(src))
        self.assertTrue(model.has_section(out, model.DONE))
        self.assertFalse(model.has_section(out, model.REST))
        self.assertEqual(model.ensure_sections(out), out)
        self.assertTrue(model.has_section(model.ensure_sections(""), model.TODAY))


class ParseWhenTests(unittest.TestCase):
    def test_formats(self):
        cases = {
            "2026-10-28": D(2026, 10, 28),
            "10-28": D(2026, 10, 28),
            "1/5": D(2027, 1, 5),
            "10-23": TODAY_D,
            "+3": D(2026, 10, 26),
            "3d": D(2026, 10, 26),
            "today": TODAY_D,
            "Tomorrow": D(2026, 10, 24),
            "tom": D(2026, 10, 24),
            "mon": D(2026, 10, 26),
            "friday": D(2026, 10, 30),  # today is Friday -> next week
            "thu": D(2026, 10, 29),
        }
        for raw, expected in cases.items():
            self.assertEqual(model.parse_when(raw, TODAY_D), expected, raw)

    def test_garbage(self):
        for raw in ("", "soon", "2026-02-30", "13-01", "fr", "3"):
            self.assertIsNone(model.parse_when(raw, TODAY_D), raw)


class StoreTests(unittest.TestCase):
    def test_roundtrip_preserves_crlf_and_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "todos.md"
            p.write_bytes(b"\xef\xbb\xbf" + SAMPLE.replace("\n", "\r\n").encode())
            f = TodoFile(p)
            snap = f.update(lambda t: model.add_item(t, "x"))
            raw = p.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn(b"- [ ] x\r\n", raw)
            self.assertNotIn(b"\r\r", raw)
            self.assertEqual(snap.signature, f.signature())
            self.assertEqual(list(Path(d).iterdir()), [p])  # no temp files left behind

    def test_signature_changes_on_external_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "todos.md"
            p.write_text(SAMPLE, encoding="utf-8")
            f = TodoFile(p)
            before = f.read().signature
            p.write_text(SAMPLE + "more\n", encoding="utf-8")
            self.assertNotEqual(before, f.signature())


if __name__ == "__main__":
    unittest.main()
