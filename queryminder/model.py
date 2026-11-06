"""Pure, side-effect-free parsing and editing of the to-do Markdown file.

All functions take and return text with ``\\n`` line endings. File-level
concerns (encoding, BOM, CRLF, atomic writes) live in :mod:`queryminder.store`.

File convention (see docs/SCOPE.md):

    ## Today      <- pending items shown in the app
    ## Rest       <- everything else that is open (shown collapsed)
    ## Done       <- completed items, most recent at the top

An *item* is a top-level (unindented) ``- [ ] text`` line plus any following
indented, non-blank lines (sub-items / continuation lines). Items move as a
block so nested children are never orphaned.

An open top-level Rest item may end with a schedule marker ``⏳ YYYY-MM-DD``:
a one-shot "move me to Today on that date" alarm, stripped whenever the item
leaves Rest. Markers anywhere else are ignored (kept as plain text).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Iterable

TODAY = "today"
REST = "rest"
DONE = "done"
MARKER = "\u23f3"  # ⏳ (Obsidian Tasks "scheduled")
DONE_MARKER = "✅"  # ✅ (Obsidian Tasks "done"); written on items completed via the app

ITEM_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<bullet>[-*+]) \[(?P<mark>[ xX])\](?: (?P<text>.*))?$")
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.*?)\s*#*\s*$")
DONE_DATE_RE = re.compile(r"\s*✅\s*\d{4}-\d{2}-\d{2}\s*$")
UPDATED_RE = re.compile(r"^updated:\s*.*$")
MARKER_RE = re.compile(r"^(?P<text>.*?)\s*\u23f3\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$")


class TodoError(Exception):
    """Base error for model problems shown to the user."""


class SectionNotFound(TodoError):
    pass


class ItemNotFound(TodoError):
    pass


@dataclass(frozen=True)
class TodoItem:
    text: str  # for open Rest items: without the schedule marker
    done: bool
    children: tuple[str, ...] = ()
    scheduled: dt.date | None = None  # open Rest items only
    section: str = TODAY


@dataclass(frozen=True)
class Completion:
    """What a completion changed; used to undo it."""

    text: str
    original_block: tuple[str, ...]
    done_block: tuple[str, ...]
    section: str = TODAY  # where the item came from (undo puts it back there)


@dataclass(frozen=True)
class Section:
    heading_index: int
    start: int  # first line after the heading
    end: int  # exclusive: next heading of same/higher level, or EOF
    level: int


# --------------------------------------------------------------------------- parsing


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _join(lines: list[str]) -> str:
    return "\n".join(lines)


def _frontmatter_end(lines: list[str]) -> int:
    """Index of the first line after YAML frontmatter (0 if there is none)."""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return i + 1
    return 0


def find_section(lines: list[str], name: str) -> Section | None:
    """Find a heading whose title equals ``name`` (case-insensitive)."""
    in_fence = False
    found: tuple[int, int] | None = None
    for i in range(_frontmatter_end(lines), len(lines)):
        line = lines[i]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group("hashes"))
        if found is not None and level <= found[1]:
            return Section(found[0], found[0] + 1, i, found[1])
        if found is None and m.group("title").strip().lower() == name:
            found = (i, level)
    if found is not None:
        return Section(found[0], found[0] + 1, len(lines), found[1])
    return None


def has_section(text: str, name: str) -> bool:
    return find_section(_lines(text), name) is not None


def _is_top_item(line: str) -> bool:
    m = ITEM_RE.match(line)
    return bool(m) and m.group("indent") == ""


def _block_end(lines: list[str], start: int, limit: int) -> int:
    """Exclusive end of the item block that starts at ``start``."""
    i = start + 1
    while i < limit and lines[i].strip() and lines[i][:1] in (" ", "\t"):
        i += 1
    return i


def _top_items(lines: list[str], sec: Section) -> list[tuple[int, int]]:
    """(start, end) spans of each top-level item in a section."""
    spans = []
    i = sec.start
    while i < sec.end:
        if _is_top_item(lines[i]):
            end = _block_end(lines, i, sec.end)
            spans.append((i, end))
            i = end
        else:
            i += 1
    return spans


def _item_text(line: str) -> str:
    """Full item text (including any marker)."""
    m = ITEM_RE.match(line)
    assert m
    return (m.group("text") or "").strip()


def _item_done(line: str) -> bool:
    m = ITEM_RE.match(line)
    assert m
    return m.group("mark") in "xX"


def split_marker(text: str) -> tuple[str, dt.date | None]:
    """``"call ⏳ 2026-10-28"`` -> ``("call", date(2026, 10, 28))``. Invalid dates are no marker."""
    m = MARKER_RE.match(text)
    if m:
        try:
            return m.group("text").strip(), dt.date.fromisoformat(m.group("date"))
        except ValueError:
            pass
    return text, None


def _display_text(line: str, section: str) -> str:
    """Text an item is shown and identified by in ``section``."""
    text = _item_text(line)
    if section == REST and not _item_done(line):
        text = split_marker(text)[0]
    return text


def _with_text(line: str, text: str, mark: str | None = None) -> str:
    """Rebuild an item line with new text (and optionally a new checkbox mark)."""
    m = ITEM_RE.match(line)
    assert m
    mark = m.group("mark") if mark is None else mark
    return f"{m.group('indent')}{m.group('bullet')} [{mark}]" + (f" {text}" if text else "")


def _strip_marker(line: str) -> str:
    bare, when = split_marker(_item_text(line))
    return _with_text(line, bare) if when else line


def _strip_done_date(line: str) -> str:
    """Drop a trailing ``✅ YYYY-MM-DD`` from an item line."""
    return DONE_DATE_RE.sub("", line) if ITEM_RE.match(line) else line


def match_key(text: str) -> str:
    """Duplicate-detection key: markers removed, whitespace collapsed, case-folded."""
    text = DONE_DATE_RE.sub("", text)
    return " ".join(split_marker(text)[0].split()).casefold()


def _require(lines: list[str], name: str) -> Section:
    sec = find_section(lines, name)
    if sec is None:
        raise SectionNotFound(f'No "## {name.title()}" section in the file')
    return sec


def _make_item(lines: list[str], start: int, end: int, section: str) -> TodoItem:
    line = lines[start]
    done = _item_done(line)
    scheduled = split_marker(_item_text(line))[1] if section == REST and not done else None
    return TodoItem(_display_text(line, section), done, tuple(lines[start + 1 : end]), scheduled, section)


def pending_today(text: str) -> list[TodoItem]:
    """Unchecked top-level items under ``## Today``, in file order."""
    return [i for i in today_items(text) if not i.done]


def today_items(text: str) -> list[TodoItem]:
    """All top-level items under ``## Today`` (checked or not), in file order."""
    lines = _lines(text)
    sec = _require(lines, TODAY)
    return [_make_item(lines, s, e, TODAY) for s, e in _top_items(lines, sec)]


def rest_items(text: str) -> list[TodoItem]:
    """Open top-level items under ``## Rest`` (empty if there is no Rest)."""
    lines = _lines(text)
    sec = find_section(lines, REST)
    if sec is None:
        return []
    items = [_make_item(lines, s, e, REST) for s, e in _top_items(lines, sec)]
    return [i for i in items if not i.done]


def due_items(text: str, today: dt.date) -> list[TodoItem]:
    """Scheduled Rest items whose date is on or before ``today``."""
    return [i for i in rest_items(text) if i.scheduled is not None and i.scheduled <= today]


def completion_in_done(text: str, completion: Completion) -> bool:
    """True if the exact block written by ``completion`` is still in ``## Done``."""
    lines = _lines(text)
    done = find_section(lines, DONE)
    if done is None:
        return False
    target = list(completion.done_block)
    return any(lines[s:e] == target for s, e in _top_items(lines, done))


# --------------------------------------------------------------------------- editing


def _check_line(line: str) -> str:
    return _with_text(line, _item_text(line), "x") if ITEM_RE.match(line) else line


def _uncheck_line(line: str) -> str:
    return _with_text(line, _item_text(line), " ") if ITEM_RE.match(line) else line


def _remove_block(lines: list[str], start: int, end: int) -> list[str]:
    """Delete lines[start:end] without leaving a double blank line behind."""
    out = lines[:start] + lines[end:]
    if 0 < start < len(out) and not out[start - 1].strip() and not out[start].strip():
        del out[start]
    return out


def _insert_at_top(lines: list[str], sec: Section, block: list[str]) -> list[str]:
    """Insert ``block`` before the first top-level item of ``sec``.

    If the section has no items yet, append after the section's last
    non-blank line, keeping blank lines around the list.
    """
    spans = _top_items(lines, sec)
    if spans:
        at = spans[0][0]
        return lines[:at] + block + lines[at:]
    last = sec.heading_index
    for i in range(sec.start, sec.end):
        if lines[i].strip():
            last = i
    new_block = [""] + block
    after = last + 1
    if after < len(lines) and lines[after].strip():
        new_block.append("")
    return lines[:after] + new_block + lines[after:]


def _insert_top_of(lines: list[str], name: str, block: list[str]) -> list[str]:
    return _insert_at_top(lines, _require(lines, name), block)


def _find_pending(lines: list[str], section: str, item_text: str) -> tuple[int, int]:
    """Span of the first open item shown as ``item_text`` in ``section``."""
    sec = _require(lines, section)
    for start, end in _top_items(lines, sec):
        if not _item_done(lines[start]) and _display_text(lines[start], section) == item_text:
            return start, end
    raise ItemNotFound(f'"{item_text}" is no longer pending in {section.title()}')


def clean_item_text(raw: str) -> str:
    text = " ".join(raw.split())
    if not text:
        raise TodoError("Item text is empty")
    return text


def uncheck_today_item(text: str, item_text: str) -> str:
    """Un-tick a checked item that was left in ``## Today`` (in place)."""
    lines = _lines(text)
    sec = _require(lines, TODAY)
    for start, _end in _top_items(lines, sec):
        if _item_done(lines[start]) and _item_text(lines[start]) == item_text:
            lines[start] = _uncheck_line(lines[start])
            return _join(lines)
    raise ItemNotFound(f'"{item_text}" is not checked in Today')


def add_item(text: str, item_text: str) -> str:
    """Add a new unchecked item at the top of ``## Today`` (no duplicate check)."""
    item_text = clean_item_text(item_text)
    return _join(_insert_top_of(_lines(text), TODAY, [f"- [ ] {item_text}"]))


def add_to_today(
    text: str, item_text: str, done_today: Iterable[Completion] = ()
) -> tuple[str, str, Completion | None]:
    """Duplicate-aware add (docs/SCOPE.md §8).

    Returns ``(new_text, outcome, completion)``; ``outcome`` is one of
    ``exists``, ``unchecked``, ``from_rest``, ``undone``, ``from_done``, ``added``.
    ``completion`` is the entry of ``done_today`` that was undone (``undone`` only).
    """
    item_text = clean_item_text(item_text)
    key = match_key(item_text)
    lines = _lines(text)
    today = _require(lines, TODAY)
    _require(lines, DONE)
    today_spans = _top_items(lines, today)
    for start, _end in today_spans:
        if not _item_done(lines[start]) and match_key(_item_text(lines[start])) == key:
            return text, "exists", None
    for start, _end in today_spans:
        if _item_done(lines[start]) and match_key(_item_text(lines[start])) == key:
            return uncheck_today_item(text, _item_text(lines[start])), "unchecked", None
    rest = find_section(lines, REST)
    if rest is not None:
        for start, _end in _top_items(lines, rest):
            if not _item_done(lines[start]) and match_key(_item_text(lines[start])) == key:
                return move_item(text, _display_text(lines[start], REST), REST, TODAY), "from_rest", None
    for c in done_today:
        if match_key(c.text) == key and completion_in_done(text, c):
            return _undo_to(text, c, TODAY), "undone", c
    done = _require(lines, DONE)
    for start, end in _top_items(lines, done):
        if match_key(_item_text(lines[start])) == key:
            block = [_uncheck_line(_strip_done_date(_strip_marker(lines[start])))] + [_uncheck_line(x) for x in lines[start + 1 : end]]
            remaining = _remove_block(lines, start, end)
            return _join(_insert_top_of(remaining, TODAY, block)), "from_done", None
    return add_item(text, item_text), "added", None


def complete_item(
    text: str, item_text: str, section: str = TODAY, today: dt.date | None = None
) -> tuple[str, Completion]:
    """Check the first pending item with ``item_text`` in ``section`` (Today or
    Rest) and move it (with its children, also checked) to the top of ``## Done``.
    A Rest schedule marker is dropped. If ``today`` is given, the item line gets
    a ``✅ YYYY-MM-DD`` completion date."""
    lines = _lines(text)
    _require(lines, DONE)
    start, end = _find_pending(lines, section, item_text)
    original = lines[start:end]
    first = _strip_marker(original[0]) if section == REST else original[0]
    if today is not None:
        first = f"{first} {DONE_MARKER} {today.isoformat()}"
    done_block = [_check_line(first)] + [_check_line(line) for line in original[1:]]
    remaining = _remove_block(lines, start, end)
    result = _insert_top_of(remaining, DONE, done_block)
    return _join(result), Completion(item_text, tuple(original), tuple(done_block), section)


def _undo_to(text: str, completion: Completion, section: str) -> str:
    """Move ``completion``'s done block back to the top of ``section`` as it was
    (marker only kept when going back to Rest)."""
    lines = _lines(text)
    done = _require(lines, DONE)
    _require(lines, section)
    target = list(completion.done_block)
    for start, end in _top_items(lines, done):
        if lines[start:end] == target:
            remaining = _remove_block(lines, start, end)
            block = list(completion.original_block)
            if section != REST:
                block[0] = _strip_marker(block[0]) if completion.section == REST else block[0]
            return _join(_insert_top_of(remaining, section, block))
    raise ItemNotFound(f'"{completion.text}" is no longer in Done')


def undo_completion(text: str, completion: Completion) -> str:
    """Move a completed block from ``## Done`` back to the top of the section it came
    from, exactly as it was (a Rest item gets its schedule marker back)."""
    section = completion.section
    if section == REST and not has_section(text, REST):
        section = TODAY
    return _undo_to(text, completion, section)


def move_item(text: str, item_text: str, src: str, dst: str) -> str:
    """Move an open item (with children) from ``src`` to the top of ``dst``;
    a Rest schedule marker is removed."""
    lines = _lines(text)
    _require(lines, dst)
    start, end = _find_pending(lines, src, item_text)
    block = [_strip_marker(lines[start]) if src == REST else lines[start]] + lines[start + 1 : end]
    remaining = _remove_block(lines, start, end)
    return _join(_insert_top_of(remaining, dst, block))


def schedule_item(text: str, item_text: str, section: str, when: dt.date, today: dt.date) -> str:
    """Snooze until ``when``: Today item -> top of Rest with marker; Rest item ->
    marker set/replaced in place. ``when <= today`` means "move to Today now"."""
    lines = _lines(text)
    if when <= today:
        if section == TODAY:
            _find_pending(lines, TODAY, item_text)  # still raise if it is gone
            return text
        return move_item(text, item_text, REST, TODAY)
    _require(lines, REST)
    start, end = _find_pending(lines, section, item_text)
    bare = split_marker(_item_text(lines[start]))[0] if section == REST else _item_text(lines[start])
    first = _with_text(lines[start], f"{bare} {MARKER} {when.isoformat()}")
    if section == REST:
        lines[start] = first
        return _join(lines)
    block = [first] + lines[start + 1 : end]
    remaining = _remove_block(lines, start, end)
    return _join(_insert_top_of(remaining, REST, block))


def clear_schedule(text: str, item_text: str) -> str:
    lines = _lines(text)
    start, _end = _find_pending(lines, REST, item_text)
    lines[start] = _strip_marker(lines[start])
    return _join(lines)


def promote_due(text: str, today: dt.date) -> tuple[str, list[str]]:
    """Move every scheduled Rest item due on/before ``today`` to the top of Today
    (keeping their order), markers removed. Returns the new text and moved texts."""
    lines = _lines(text)
    rest = find_section(lines, REST)
    if rest is None or find_section(lines, TODAY) is None:
        return text, []
    moved: list[str] = []
    blocks: list[str] = []
    for start, end in reversed(_top_items(lines, rest)):  # bottom-up: spans stay valid
        line = lines[start]
        if _item_done(line):
            continue
        bare, when = split_marker(_item_text(line))
        if when is not None and when <= today:
            moved.insert(0, bare)
            blocks[:0] = [_strip_marker(line)] + lines[start + 1 : end]
            lines = _remove_block(lines, start, end)
    if not moved:
        return text, []
    return _join(_insert_top_of(lines, TODAY, blocks)), moved


def rename_item(text: str, section: str, old: str, new: str) -> str:
    """Change an open item's own text; checkbox, children and Rest marker are kept."""
    new = clean_item_text(new)
    lines = _lines(text)
    start, _end = _find_pending(lines, section, old)
    if section == REST:
        when = split_marker(_item_text(lines[start]))[1]
        if when is not None and split_marker(new)[1] is None:
            new = f"{new} {MARKER} {when.isoformat()}"
    lines[start] = _with_text(lines[start], new)
    return _join(lines)


def reorder_item(text: str, section: str, item_text: str, from_pos: int, to_pos: int) -> str:
    """Move an open item (with children) inside ``section`` (Today or Rest).

    Positions count the section's open top-level items in file order; ``to_pos`` is
    the item's index among them after the move. ``from_pos`` must hold ``item_text``
    (guards against a file that changed under us). Checked items and anything else
    in the section stay where they are; schedule markers are kept."""
    lines = _lines(text)
    sec = _require(lines, section)
    open_spans = [(s, e) for s, e in _top_items(lines, sec) if not _item_done(lines[s])]
    if not 0 <= from_pos < len(open_spans) or _display_text(lines[open_spans[from_pos][0]], section) != item_text:
        raise ItemNotFound(f'"{item_text}" is no longer at that position in {section.title()}')
    if not 0 <= to_pos < len(open_spans):
        raise TodoError("Invalid position")
    if to_pos == from_pos:
        return text
    start, end = open_spans[from_pos]
    block = lines[start:end]
    rest_lines = lines[:start] + lines[end:]
    sec2 = _require(rest_lines, section)
    spans = [(s, e) for s, e in _top_items(rest_lines, sec2) if not _item_done(rest_lines[s])]
    at = spans[to_pos][0] if to_pos < len(spans) else spans[-1][1]
    return _join(rest_lines[:at] + block + rest_lines[at:])


NEW_FILE_TEMPLATE = "# To-dos\n\n## Today\n\n## Rest\n\n## Done\n"


def ensure_sections(text: str, names: Iterable[str] = (TODAY, DONE)) -> str:
    """Append any missing ``## <Name>`` sections (in the order given) at the end."""
    out = text
    for name in names:
        if find_section(_lines(out), name) is None:
            out = out.rstrip("\n") + ("\n\n" if out.strip() else "") + f"## {name.title()}\n"
    return out if out == text else out.rstrip("\n") + "\n"


def delete_item(text: str, section: str, item_text: str) -> str:
    """Remove an open item with its children."""
    lines = _lines(text)
    start, end = _find_pending(lines, section, item_text)
    return _join(_remove_block(lines, start, end))


# --------------------------------------------------------------------------- dates

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_when(raw: str, today: dt.date) -> dt.date | None:
    """Parse *Pick date…* input: ``2026-10-28``, ``10-28`` / ``10/28`` (next
    occurrence), ``fri`` / ``friday`` (next occurrence after today), ``+3`` /
    ``3d``, ``today``, ``tomorrow`` / ``tom``. Returns None if not understood."""
    s = raw.strip().lower()
    if not s:
        return None
    if s == "today":
        return today
    if s in ("tomorrow", "tom", "tmr"):
        return today + dt.timedelta(days=1)
    m = re.fullmatch(r"\+(\d{1,3})d?|(\d{1,3})d", s)
    if m:
        return today + dt.timedelta(days=int(m.group(1) or m.group(2)))
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})", s)
    if m:
        try:
            d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
        return d if d >= today else d.replace(year=today.year + 1)
    if len(s) >= 3:
        for i, name in enumerate(_WEEKDAYS):
            if name.startswith(s):
                return today + dt.timedelta(days=(i - today.weekday()) % 7 or 7)
    return None


def touch_updated(text: str, date_iso: str) -> str:
    """Set ``updated:`` in the YAML frontmatter, if both exist."""
    lines = _lines(text)
    end = _frontmatter_end(lines)
    for i in range(1, max(end - 1, 1)):
        if UPDATED_RE.match(lines[i]):
            lines[i] = f"updated: {date_iso}"
            return _join(lines)
    return text
