# Queryminder

Always-on-top desktop card for the `## Today` (and, collapsed, `## Rest`) sections of a Markdown to-do file.
The first run asks which `.md` file to use (pick one, or type a new name to create it
with the three sections); right-click → *Change backing file…* switches later.

- **Start**: double-click `start-queryminder.cmd` (needs Python 3 on PATH).
- **Click an item** → done (moved to `## Done`, stays visible struck-through today). Click it again to undo.
- **`+ add item…`** at the bottom → type, Enter. If it already exists in Rest/Done it is moved back instead of duplicated.
- **`REST (n) ▸`** → show/hide the Rest list (click a Rest item to complete it).
- **Right-click an item** → Move to Rest/Today, Snooze until… (adds `⏳ YYYY-MM-DD`; on that day it moves to Today by itself), Edit…, Delete.
- **Top-right tab** or **double-click the header** → shrink to a tile; click the tile to restore. **Drag** the header to move.
- **Right-click** → Undo done, Skins (incl. Dalek), Reload, Open file, Change backing file…, Clean done items (visual only), Exit.
- **Drag an item** up/down to re-order it (click without dragging = done).
- Edits made in Obsidian show up within a second.

One-off file override (not remembered): `python -m queryminder --file "D:\path\todos.md"`.
Autostart: `Queryminder.lnk` in `shell:startup` launches it at login; delete it to stop.

Docs: [scope](docs/SCOPE.md) · [architecture](docs/ARCHITECTURE.md). Tests: `python -m unittest -v`.
