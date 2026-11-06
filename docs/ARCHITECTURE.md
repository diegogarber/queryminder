# Queryminder — Architecture & Implementation

## Technology choice

**Python 3 + Tkinter, standard library only.** Tk ships with the Windows
Python installer, so there is nothing to install, startup is instant and the
footprint is tiny. Windows-specific bits (`ctypes`) are used only for DPI
awareness and the single-instance mutex. No third-party dependencies at
runtime (Pillow is used only by the optional screenshot smoke test).

Run: `start-queryminder.cmd` (uses `pythonw`, no console) or
`python -m queryminder [--file PATH] [--allow-multiple]`.

## Layout

```
queryminder/
  __main__.py   entry point: args, single-instance mutex, DPI awareness, Tk root
  model.py      PURE Markdown parsing/editing (no I/O, no Tk) — fully unit tested
  store.py      file I/O: encoding/BOM/CRLF preservation, atomic write, retry, signature
  settings.py   %APPDATA%\queryminder\settings.json + todo-file path resolution
  picker.py     file dialog to choose / create the backing file (first run, Change backing file…)
  monitors.py   monitor work areas (Win32 EnumDisplayMonitors) + PURE placement logic
  skins.py      skin definitions (pure data) + pixel-art mascots
  ui.py         Tkinter App: window, rendering, polling, actions, context menu
tests/
  test_model.py unittest suite for model
  test_store.py new/incomplete file handling + path resolution
  test_monitors.py placement logic (fit / is_reachable)
  test_skins.py skin / animation data integrity
start-queryminder.cmd
docs/SCOPE.md, docs/ARCHITECTURE.md
```

Dependency direction: `ui → model, store, skins, settings, monitors`. `model` depends on
nothing; keep it that way.

## Data model (`model.py`)

- A **section** is a heading whose title equals `today` / `rest` / `done`
  (case-insensitive, any level) up to the next heading of the same or higher
  level. YAML frontmatter and fenced code blocks are skipped when looking for
  headings. `today` and `done` are required (`SectionNotFound`); `rest` is
  optional (no Rest → empty list, Rest actions raise `SectionNotFound`).
- An **item** is a *top-level* (unindented) `- [ ]` / `- [x]` line (also `*`/`+`
  bullets) plus the following non-blank, indented lines (its block). Blocks
  always move as a unit. `TodoItem(text, done, children, scheduled, section)`.
- **Schedule marker** `⏳ YYYY-MM-DD` at the end of the first line
  (`split_marker`). Only parsed for open items in Rest: there `text` excludes
  it and `scheduled` is a `date`. Elsewhere it is part of `text` and ignored.
  Every operation that takes an item out of Rest strips it (`_strip_marker`).
- Items are identified by **(section, text)**, not line numbers, so edits
  survive the file having changed since it was rendered (the same text can
  exist in Today and Rest). If the item is gone, `ItemNotFound` is raised and
  the UI just reloads.
- All operations are pure `str -> str` functions on `
`-normalized text:
  - `today_items(text)`, `rest_items(text)` (open only), `pending_today(text)`
  - `completion_in_done(text, Completion)` — is that exact done block still in Done?
  - `uncheck_today_item(text, item_text)` — untick an `[x]` item left in Today.
  - `add_item(text, item_text)` — insert `- [ ] item` at the top of Today, no checks.
  - `add_to_today(text, item_text, done_today) -> (text, outcome, completion)` — the
    duplicate-aware add used by the UI (SCOPE §8). Matching uses `match_key`
    (casefold, collapsed whitespace, marker removed). Outcomes: `exists`,
    `unchecked`, `from_rest`, `undone`, `from_done`, `added`.
  - `complete_item(text, item_text, section=TODAY) -> (text, Completion)` —
    check the first *pending* item with that text in Today or Rest (and its
    children; a Rest marker is dropped), move it to the top of Done.
    `Completion` records the source `section` and the exact original block.
  - `undo_completion(text, Completion)` — find the exact done block in Done
    and put the original block back at the top of its source section.
  - `move_item(text, item_text, src, dst)` — top of `dst`, marker stripped.
  - `schedule_item(text, item_text, section, when, today)` — Today → top of
    Rest with marker; Rest → marker set/replaced in place; `when <= today` →
    moves to Today instead. `clear_schedule(text, item_text)`.
  - `promote_due(text, today) -> (text, moved_texts)` — all scheduled Rest
    items with date ≤ today, in order, to the top of Today, markers stripped.
  - `rename_item(text, section, old, new)` — first line only; bullet, mark,
    marker and children kept. `delete_item(text, section, item_text)`.
  - `parse_when(s, today) -> date | None` — the *Pick date…* syntax.
  - `touch_updated(text, iso_date)` — update frontmatter `updated:` if present.
- Insertion "at the top" means before the section's first top-level item (so
  intro paragraphs such as the note under `## Done` stay above the list). In an
  empty section the item is appended after the last non-blank line with blank
  lines around it. Removing a block never leaves a double blank line.

- `reorder_item(text, section, item_text, from_pos, to_pos)` — move an open item
  within Today/Rest; positions index the open top-level items in file order and
  `from_pos` must hold `item_text` (else `ItemNotFound`).

## File handling (`store.py`)

- **Read**: bytes → detect UTF-8 BOM and CRLF → decode → normalize to `\n`.
- **Write**: restore the original newline style and BOM, write to a temp file
  in the same directory (`.queryminder-*.tmp`), then `os.replace` (atomic on
  NTFS). `PermissionError` (OneDrive/Obsidian briefly locking the file) is
  retried with backoff.
- **Read-modify-write**: `TodoFile.update(fn)` *always re-reads* the file
  immediately before applying an edit, so changes made elsewhere since the last
  poll are never clobbered.
- **Change detection**: `signature()` = `(mtime_ns, size)`. The UI polls it
  every 1 s via `root.after` (no watcher thread, no dependency; works with
  OneDrive placeholders and atomic-rename writers that break file watchers).
  After our own write the stored signature is updated, so we don't reload
  our own change.

## UI (`ui.py`)

- Borderless (`overrideredirect`) and `-topmost`; topmost is re-asserted every
  5 polls because Windows occasionally demotes it.
- The root background is a colour key (`#ff00fe`) made transparent with
  `-transparentcolor`, which allows the minimize tab to overhang the card's
  top-right corner like the reference screenshot.
- Two views inside one window: the **card** and the **tile** (minimized).
  Toggled by the tab button, a `<Double-Button-1>` on the header widgets
  (`make_draggable(..., on_double=...)`), or a click on the tile. On
  toggle the window's top-right corner stays fixed.
- **Done today**: completion dates (`✅`) exist only on items completed via the app, so "done today" still comes from a log of
  `Completion`s made today (`done_log`, persisted in settings as
  `done_today: {date, items}` and dropped when the date changes). The card
  shows pending items, then `DoneRow`s = logged completions whose block is
  still in `## Done` + `[x]` items inside `## Today`. Clicking a DoneRow
  undoes it (`undo_completion` or `uncheck_today_item`). Items completed in
  Obsidian by moving them to Done themselves are not shown as done (no way to
  know they were done today).
- Re-rendering of the items list happens only when `(items, done_rows,
  rest, rest_open, error, date)` changes, so polling doesn't flicker and the
  add-item field keeps its text. While an inline field is open (`editing`:
  Edit… / Pick date…) rendering is deferred entirely and item clicks are
  ignored, so the 1 s poll can't destroy the field.
- **Rest** is a second list below Today's items, behind a `REST (n) ▸` toggle
  (`rest_open` in settings). Its rows live in a canvas-based scroll area
  (max ~200 px, mouse wheel while hovering). Clicking a Rest row completes it
  (`complete_item(..., REST)`); `DoneRow`s whose completion came from Rest are
  rendered at the bottom of the Rest list instead of under Today.
- **Item menu**: each row binds `<Button-3>` and returns `"break"`, so the
  global `bind_all` handler doesn't fire twice; `show_menu(event, row)` puts the
  item actions above the regular entries. Delete's confirmation is a submenu.
- **Housekeeping on every write**: `edit(fn)` applies
  `touch_updated(promote_due(fn(text)))`. `load()` additionally performs an
  empty edit when `due_items()` is non-empty, so due items move at start-up,
  on any poll and after midnight even if nothing else happens.
- **Add** calls `add_to_today(text, entry, done_log)`; an `undone` outcome also
  removes that completion from `done_log`.
- Click → box filled + strike-through → after 450 ms `complete()` writes the
  file. A `busy` flag blocks double clicks and pauses reloads meanwhile.
- `bind_all("<Button-3>")` gives the context menu everywhere; it is rebuilt on
  each popup so the skin radio buttons and the undo label are current. While
  it is open (`_menu_open`), the periodic topmost re-assert and placement
  check are paused: `tk_popup` is modal but timers still fire, and re-setting
  `-topmost` would raise the card above its own menu.
- Sizes are multiplied by the DPI scale (`winfo_fpixels('1i') / 96`); the
  process is made per-monitor DPI aware for crisp text.
- A skin change rebuilds all widgets (`build()`); skins are plain data.
- Settings (skin, x, y, minimized, rest_open, done_today, optional file) are saved on
  move, skin change, minimize/Rest toggle and exit. `done_today` items store
  `text`, `original`, `done` and `section`.

## Window placement (`monitors.py`)

- `work_areas()` enumerates monitors via `EnumDisplayMonitors` /
  `GetMonitorInfoW` → `Monitor(work: Rect, primary)`. Work area excludes the
  taskbar. Coordinates are physical virtual-screen pixels (process is DPI
  aware, same as Tk), so left/top monitors are negative. Falls back to Tk's
  screen size if the call fails.
- `fit(x, y, w, h, monitors)` (pure): no saved position, no overlap with any
  monitor, or header strip not grabbable → `default_position` (primary,
  top-right, 40 px margin). Otherwise clamp inside the work area of the
  monitor with the largest overlap.
- `is_reachable(x, y, w, monitors)` (pure): ≥ 40×10 px of the top 24 px strip
  is on one monitor.
- `App.ensure_on_screen(full)`: `full=True` (startup, minimize toggle) applies
  `fit`; `full=False` (every 5 polls) only rescues an unreachable window, so a
  window the user deliberately parks half off-screen is left alone. Skipped
  while dragging. Any correction is saved immediately.

## Skins (`skins.py`)

`Skin` fields: colours (`paper`, `ink`, `muted`, `accent`, `border`, `check`,
`button_bg/fg`), texts (`title`, `section`, `empty`, `stamp`, `flash`, where
`{date}` expands to e.g. `TUE OCT 20` and `{stardate}` to a playful stardate
such as `126802.7`), `check_shape` (`square`/`circle`),
font preference list, optional `mascot` key into `MASCOTS` (pixel art: one
character per pixel, `.` transparent, palette dict), `rule` separator style
(`dots`, `lcars` segmented colour bars using `rule_colors`, `teeth` = Domo's
red mouth with white teeth, `paws` = trail of paw prints). `check_shape` also
accepts `paw` (square box, paw print when ticked). Add a skin by
appending to `SKINS` — the menu picks it up automatically. A saved skin key that
no longer exists falls back to the default.

The Dalek skin: gunmetal card, bronze border, gold text, round "bump"
checkboxes, a pixel-art Dalek in the header and the tile, "EXTERMINATE!"
title and an "EXTERMINATED" stamp when the list is empty.

The Star Trek (LCARS) skin: black card, orange/peach/lilac TNG computer
palette, condensed font (Bahnschrift SemiCondensed), LCARS colour bars as
separators, a Starfleet delta mascot, "CAPTAIN'S LOG" / "STARDATE …" headings
and a "MAKE IT SO" stamp.

The Domo-kun skin: brown fur card, red/white teeth separators, pixel Domo,
"NOM!" stamp. The French bulldog skin: fawn/cream card, paw-print separators
and checkmarks, pixel Frenchie face with bat ears, "GOOD BOY!" stamp.

### Header animations

Data in `skins.py`: `ANIMATIONS[mascot] = (Animation, ...)`; an `Animation` is
`name`, `frames`, `repeat=(min, max)` and `weight`; a `Frame` is a full sprite
(`rows`, same palette as the mascot; extra colours only used by frames go in
that palette too), a duration `ms` and an optional temporary header `title`.
Frames may be wider than the base sprite: the header canvas is sized to the
widest frame. `Skin.anim_idle = (min_s, max_s)` is the random pause between
animations. Helpers `_rows(base, width, r<N>=...)` / `_shift` build frames.

`ui.App`: `schedule_anim()` arms one `after()` with a random delay;
`play_anim()` (also the mascot's single-click handler) picks a weighted random
animation other than the last one, and `_anim_step()` draws the frames
(`draw_sprite`) chained with `after()`, then restores sprite + title and
reschedules. The target is picked when an animation starts: the header
canvas (`anim_canvas`, 3 px, title animated) or, when minimized, the tile's
(`tile_anim_canvas`, 2 px, sprite only; for animated skins the tile count is
drawn on that canvas by `set_tile_text`, under the "sprite"-tagged items, and
the canvas is sized like the old sprite + label so the tile stays compact); toggling mid-animation lets it finish
where it started. `build()` increments `_anim_gen`; pending steps of destroyed
widgets see a different generation and stop. `render()` leaves the title alone
while one plays.
`tests/test_skins.py` checks frame data (known colours, heights, durations).

## Configuration

Todo file path precedence: `--file` > `QUERYMINDER_FILE` env var > `"file"` in
settings.json. No built-in default: if none is set, `__main__` shows `picker.choose_file`
and stores the answer in settings (`--file` overrides are never persisted).
`store.inspect_file / initialise_file / add_missing_sections` back the picker;
`model.NEW_FILE_TEMPLATE` / `ensure_sections` define the three sections.

## Testing

- `python -m unittest -v` — model and store tests (pure, fast, temp files).
- UI is verified manually / with a throwaway smoke script that runs the App on
  a **temp copy** of the file and grabs screenshots (`PIL.ImageGrab`). Never
  point tests at the real todos.md.

## Known limitations

- Two items with identical text in the same section: the first pending one is
  acted on.
- Due items are only moved while the app runs (any machine running it); two
  machines on OneDrive could both try — re-read-before-write makes the second
  a no-op in practice.
- Items whose text is edited in Obsidian between render and click are reported
  as "no longer pending" and the list reloads.
- "Done today" only knows about items completed through the app (or ticked
  in place in Today); it is per machine (stored in %APPDATA%).
- Borderless windows don't appear in the taskbar / Alt-Tab.

## Autostart

Autostart is a `Queryminder.lnk` shortcut in the user's Startup folder running
`pythonw.exe -m queryminder` from the project dir. If the project folder or Python
install moves, update the shortcut. Remove the shortcut to disable autostart.
