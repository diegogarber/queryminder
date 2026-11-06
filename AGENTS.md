# AGENTS.md — Queryminder

Always-on-top desktop card (Windows and macOS) that shows/edits the `## Today` and
`## Rest` sections of the user's Obsidian to-do list. Read `docs/SCOPE.md` (what) and
`docs/ARCHITECTURE.md` (how) before changing behaviour; keep both up to date
with any behaviour change.

## Critical rules

- **The configured data file (settings `file`) is live user data**
  (never hard-code its path).
  Never run tests, smoke scripts or experiments against it. Copy it to a temp
  dir and use `--file <copy>` (or `QUERYMINDER_FILE`). Reading it to understand
  the format is fine.
- The Markdown file is the single source of truth. Do not add caches/databases.
- Preserve everything in the file the app doesn't own: frontmatter, intro text,
  other sections, line endings (CRLF/LF), BOM. Only `## Today`, `## Rest`,
  `## Done` and the frontmatter `updated:` field may be modified.
- File conventions: items `- [ ] text` / `- [x] text`; indented lines are
  sub-items and move with their parent; new and moved items go at the **top**
  of their section; completed items go at the **top** of Done (most recent
  first).
- All edits go through `TodoFile.update()` (re-read → edit → atomic write).
  Never write from stale in-memory text.
- Identify items by (section, text), never by line index.
- Adding to Today is duplicate-aware (`model.add_to_today`): never create a
  second copy of something already in Today/Rest/Done; never delete copies.
- Done items stay visible (struck-through) for the day they were completed.
  "Done today" comes from the app's `done_today` log in settings (+ `[x]`
  items still under Today).
- Dates the app writes: the completion date `✅ YYYY-MM-DD` on the top-level
  line of items it completes into Done (stripped when reopened from Done), and
  the schedule marker `⏳ YYYY-MM-DD` on open top-level Rest items: a one-shot alarm, stripped whenever the item leaves
  Rest (moved, promoted, completed, pulled by add). Markers elsewhere are
  ignored and left untouched. Spec: `docs/SCOPE.md` §12.

## Code layout

- `queryminder/model.py` — pure str→str parsing/editing. No I/O, no Tk. All
  file-format logic belongs here, with unit tests.
- `queryminder/store.py` — encoding/newline-preserving I/O, atomic write,
  `PermissionError` retry, `(mtime_ns, size)` signature for polling.
- `queryminder/compat.py` — OS differences (single instance, open file, transparent
  colour, menu events, wheel). No Tk import.
- `queryminder/macos.py` — Objective-C runtime calls via ctypes (screens, Spaces, Dock icon).
- `queryminder/picker.py` — file dialog (choose/create backing file);
  `queryminder/ui.py` — Tkinter `App`; `queryminder/skins.py` — skins as data
  (add a skin = append to `SKINS`; optional header animations = `ANIMATIONS[mascot]`); `queryminder/settings.py` —
  `settings.json` (`%APPDATA%\queryminder\`, or `~/Library/Application Support/queryminder/` on macOS; `APPDATA` overrides it everywhere); `queryminder/monitors.py` — monitor
  enumeration + pure placement (`fit`, `is_reachable`); keep placement logic
  pure and unit tested.

## Stack & commands

- Python 3.10+ (developed on 3.14) + Tkinter, **standard library only**. Don't
  add runtime dependencies without a strong reason.
- Run: `start-queryminder.cmd` (Windows), `start-queryminder.command` (macOS) or
  `python -m queryminder --file <path>`
  (`--allow-multiple` bypasses the single-instance check — needed if the user's
  instance is already running).
- Test: `python -m unittest -v` (must pass before finishing any change).
- UI changes: verify visually with a throwaway script that runs `App` on a temp
  copy and grabs screenshots with `PIL.ImageGrab` (keep such scripts under
  `.pi/`, which is git-ignored); isolate settings by pointing `APPDATA` at a temp
  dir.

## Autostart

Windows: autostart is a `Queryminder.lnk` shortcut in the user's Startup folder running
`pythonw.exe -m queryminder` from the project dir. If the project folder or Python
install moves, update the shortcut. Remove the shortcut to disable autostart.
macOS: a LaunchAgent (template in the README).

## Windows/Tk gotchas

- Window is `overrideredirect` + `-topmost`; on Windows the root bg `#ff00fe` is a
  transparent colour key — don't use that colour in skins.
- Entry focus in a borderless window needs `focus_force()`.
- `tk_popup()` (right-click menu) blocks in a modal loop but `after()` timers keep
  firing. Never raise/re-assert `-topmost` or move the window while
  `App._menu_open` is True, or the card covers its own menu.
- Rotated canvas text doesn't work with bitmap fonts (Fixedsys) — the stamp
  uses Consolas.
- Pixel sizes must go through `App.px()` (DPI scaling).
- Screen coordinates are physical pixels and can be negative (monitor left of
  primary). Never validate positions with `winfo_screenwidth`/`vrootwidth`;
  use `monitors.work_areas()`.
- `winfo_x/y` are stale right after `geometry()` until `update_idletasks()`.
- Bash heredocs in this harness can eat backslashes; write scripts with
  backslashes to a file instead.
- macOS (`docs/ARCHITECTURE.md` § macOS): the window uses `-stylemask ""`, not
  `overrideredirect`. `screencapture`/`ImageGrab` need Screen Recording permission, and a
  scripted `tk_popup` blocks until someone dismisses the native menu, so don't call it
  in smoke scripts. Windows gotchas above about `-topmost` still apply.
- In bash heredocs, watch backslashes in Windows strings (e.g. the mutex name
  `Local\\QueryminderSingleInstance`).
