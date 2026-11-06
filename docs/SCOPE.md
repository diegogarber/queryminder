# Queryminder — Scope

## Purpose

A small, always-visible desktop card for Windows and macOS that shows the items pending
**today** from the Obsidian to-do list (plus, collapsed, the rest of the open
items), and lets the user tick them off, add, edit, move and schedule them
without opening Obsidian. The visual style loosely follows a retro
"paper checklist" look (cream card, red dotted rules, square checkboxes, red
minimize tab overhanging the top-right corner).

## Data source

A user-chosen Markdown file, stored in settings (`file`). Nothing is hard-coded.
*First run* (no file configured): a file dialog asks for it. It accepts an existing
`.md` file or a new name; a new (or empty) file is created with `## Today`, `## Rest`
and `## Done`. An existing file missing `## Today`/`## Done` is offered the missing
sections appended at the end (nothing else touched). Cancelling the first-run dialog
exits. Right-click → *Change backing file…* runs the same dialog later; the choice is
remembered, today's done log is reset (it belongs to the old file).

This Markdown file is the **only** source of truth. The app keeps no other
copy of the data. File convention:

| Section     | Meaning                                         | Used by app                                   |
|-------------|-------------------------------------------------|-----------------------------------------------|
| `## Today`  | items for today                                 | shown, add, complete, edit, delete, move, snooze |
| `## Rest`   | everything open that is not for today           | shown (collapsible), complete, edit, delete, move, schedule |
| `## Done`   | completed items, **most recent at the top**     | completed items go here; *add* can reopen from here |

Items are `- [ ] text` (open) / `- [x] text` (done). Indented lines below an
item are its sub-items and travel with it. New and moved items go at the
**top** of a section.

**Schedule marker.** An open, top-level item in `## Rest` may end with
`⏳ YYYY-MM-DD` (Obsidian Tasks "scheduled" syntax), e.g.
`- [ ] Talk to Gene ⏳ 2026-10-28`. It is a **one-shot alarm**: "move me to
Today on that date". The app removes it when the item leaves Rest. A marker
anywhere else (Today, Done, a sub-item) or with an invalid date is ignored and
left untouched. Items completed through the app get a
completion date `✅ YYYY-MM-DD` (Obsidian Tasks "done") appended to the top-level
line in `## Done`; sub-items get none. Items ticked in Obsidian get no date.
Reopening an item from Done strips the date.

## In scope (v1)

1. **Always on top** of every other window (re-asserted periodically).
2. **Minimize button** (top-right), or **double-click the header** (title /
   mascot area). Collapses the card into a small tile
   (pending count, or the skin mascot). The window never disappears; clicking
   the tile (or the `+` button) restores it.
3. **Load today's pending items**: every unchecked top-level item under
   `## Today`.
4. **Live reload**: the file is polled every second; edits made by Obsidian,
   OneDrive sync or anything else are picked up automatically.
5. **Click to complete**: clicking an item ticks it (short strike-through
   animation), changes `[ ]` → `[x]` (sub-items too) and moves it to the top
   of `## Done`. **It stays visible in the card** as done (filled box,
   struck-through, below the pending items) for the rest of the day, like the
   reference screenshot. When everything is done a "DONE!" tag appears next to
   the section heading. The heading shows `done/total`. Items ticked `[x]`
   directly inside `## Today` (e.g. in Obsidian) are shown as done too.
   Clicking a done item un-does it (back to the top of Today / unticked).
   "Done today" survives app restarts and resets at midnight.
   Items can also be completed from Rest (see 9); those stay visible
   struck-through at the bottom of the Rest list (not in Today's list or
   count).
6. **Right-click → Skins**: Retro paper (default), Dalek, TARDIS, Green
   terminal, Sticky note, Star Trek (LCARS), Domo-kun, French bulldog. The
   choice is remembered.
7. **Right-click → Exit**.
8. **Add items**: the `+ add item…` field at the bottom (Enter to add, Esc to
   cancel). New items go to the top of Today.
   **No duplicates**: the text is first looked up (case-insensitive,
   whitespace collapsed, schedule marker ignored; no fuzzy matching):
   - already pending in Today → nothing is added, status says so;
   - ticked `[x]` in place in Today → unticked;
   - in Rest (first match) → moved to the top of Today with its sub-items,
     marker removed; Rest wins over Done;
   - completed today through the app → that completion is undone;
   - in Done (most recent match) → moved to the top of Today, unticked
     together with its sub-items, marker removed;
   - otherwise a new item is added. Other copies are never deleted.

### Rest, moving, scheduling, editing (v2)

9. **Rest section**: a collapsible `REST (n) ▸` heading below Today's items,
   **collapsed by default**, open/closed state remembered. It lists the open
   top-level items under `## Rest` in muted ink, with a `⏳ Wed 28` badge for
   scheduled ones. Above ~200 px it scrolls with the mouse wheel. Clicking a
   Rest item completes it, exactly like a Today item, and it stays
   struck-through at the bottom of the Rest list for the day (click = undo,
   back to Rest). The Today count, the
   `DONE!` tag and the tile count are about Today only. If the file has no
   `## Rest` heading the section is hidden and Rest actions are unavailable.
10. **Item menu**: right-click an item → its actions appear at the top of the
    regular menu:
    - Today item: *Move to Rest*, *Snooze until ▸*, *Edit…*, *Delete ▸*
    - Rest item: *Move to Today*, *Snooze until ▸* (*Reschedule* if already
      scheduled), *Clear schedule* (if scheduled), *Edit…*, *Delete ▸*
    - done row: *Undo done*

    Right-click anywhere else shows the regular menu only.
11. **Move** Today ↔ Rest: the item (with sub-items) goes to the top of the
    other section; a schedule marker is removed. A move is a plain move (no
    duplicate check, nothing is ever merged or deleted).
12. **Schedule ("Snooze until…")**: submenu with *Tomorrow*, the next six
    days (e.g. *Sun 25*), *In 2 weeks*, and *Pick date…* (inline field that
    accepts `2026-10-28`, `10-28`, `fri`/`friday`, `+3`, `today`, `tomorrow`;
    a weekday means its next occurrence after today).

    | Action | On | Result |
    |---|---|---|
    | Snooze until X | Today item | moves to the top of Rest with `⏳ X` |
    | Snooze until X | Rest item | marker set/replaced, item stays in place |
    | Snooze until a date ≤ today | any | same as *Move to Today* |
    | Clear schedule | scheduled Rest item | marker removed |
    | Move to Today | scheduled Rest item | moves now, marker removed |
    | Date arrives (≤ today) | scheduled Rest item | auto-moves to the top of Today, marker removed |
    | Tick done | scheduled Rest item | goes to Done without the marker |
    | Undo that | | back to the top of **Rest with its original marker** (auto-moves again if now due) |
    | Undo a Today completion | | back to Today as it was (no marker) |
    | Add "X" | X scheduled in Rest | pulled to Today, marker removed |

    Due items are checked at start-up, on every poll and at midnight; overdue
    ones (app was not running) move too. Several due items keep their Rest
    order. Dates only, local midnight; no times, no repetition, no reminders.
13. **Edit…**: the item's text becomes an inline field (Enter saves, Esc
    cancels; an empty text cancels). Only the item's own text changes:
    checkbox, sub-items and schedule marker are kept. Done rows can't be
    edited (done-today tracking relies on their text). Reloads don't redraw
    the list while editing.
14. **Delete ▸ Delete "…"**: the confirmation is the submenu entry. Removes
    the item with its sub-items (and marker). Not offered for done rows.

15. **Animated header mascot** (optional, per skin; Dalek and Domo-kun). Now
    and then (random pause, Dalek 25–90 s) the header mascot plays a randomly
    picked animation (weighted, never the same one twice in a row), some of
    them a random number of times. Clicking the mascot plays one right away
    (double-click still minimizes). Animations may briefly change the header
    title. When minimized the tile's mascot plays them too (sprite only, the
    tile count stays; clicking the tile still restores). The tile keeps its
    compact size: wide frames (death ray, glide) briefly draw over the count. Dalek animations: eyestalk *scan*,
    *look* (turns its eye to you), *EX-TER-MI-NATE!* (word by word, dome
    lights flashing), *fire* (death ray), *glide*.
    Domo-kun (title `CUCUUUUU!!!`): *look* (blinks, looks left/right),
    *chomp* (NOM NOM NOM!), *cucuuu* (mouth wide open, shaking, the title
    stretches to `CUCUUUUUUUUU!!!`), *waddle*.

### Small extras included

- Right-click → *Undo done* (latest item completed today).
- Right-click → *Clean done items*: **visual only** — hides today's struck-through
  done rows from the card (clears the done-today log, hides ticked Today rows
  for the session). The file is never modified; reopening still works via add.
- **Re-ordering**: drag a pending item (Today or Rest) up/down; a line shows the drop
  position. A click without dragging still completes it. Only the item (with sub-items and marker) moves;
  checked items and everything else stay put.
- Right-click → *Change backing file…* (see Data source).
- Right-click → *Reload now*, *Open todos.md* (default `.md` app).
- Drag the header / tile to move the window; position, skin and minimized
  state persist across restarts.
- **Multi-monitor aware position**: on start the saved position is checked
  against the monitors that exist now. Saved on a monitor that is gone (e.g.
  laptop undocked) → moves to the primary monitor's top-right corner. Partly
  off-screen (resolution changed) → nudged fully inside that monitor. While
  running, if the window becomes unreachable (monitor unplugged) it is moved
  back within ~5 s. Monitors left of/above the primary (negative coordinates)
  are supported.
- Frontmatter `updated:` is set to today's date whenever the app writes.
- Single instance: launching it twice does nothing.
- Starts automatically at login (Windows: Startup-folder shortcut; macOS: LaunchAgent, see README).
- Friendly in-card error if the file or the `## Today` / `## Done` headings are
  missing; it recovers automatically once fixed.

## Out of scope (v1)

- Reordering items within a section; editing sub-items; drag-and-drop.
- Recurring items, times of day, notifications, reminders.
- Multiple lists or files at once, sync of its own.
- Taskbar / Alt-Tab presence (it is a borderless widget; exit via right-click).
- Installer. It is run from source with the system Python.

## Acceptance checks

- With the sample file, the card shows exactly `remote hermes / to-do things`
  and `obsidian wiki`.
- Adding `- [ ] x` under `## Today` in Obsidian shows `x` within ~1 s.
- Clicking an item removes it from the card and the file shows it as the first
  `- [x]` under `## Done`; nothing else in the file changes except `updated:`.
- Line endings, BOM and all other content in the file are preserved.
- Snoozing a Today item to tomorrow moves it to the top of Rest as
  `- [ ] text ⏳ <tomorrow>`; with the clock past that date it is back at the
  top of Today without the marker within ~1 s.
- Adding the text of a Rest item moves it instead of creating a duplicate.
