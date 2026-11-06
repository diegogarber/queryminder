# Queryminder

Always-on-top desktop card for the `## Today` (and, collapsed, `## Rest`) sections of a Markdown to-do file.
The first run asks which `.md` file to use (pick one, or type a new name to create it
with the three sections); right-click → *Change backing file…* switches later.

- **Start**: double-click `start-queryminder.cmd` on Windows or `start-queryminder.command` on macOS (needs Python 3 on PATH; on macOS with Homebrew also `brew install python-tk@3.15`, matching your Python version).
- **Right-click** on macOS: right button or control-click.
- **Click an item** → done (moved to `## Done`, stays visible struck-through today). Click it again to undo.
- **`+ add item…`** at the bottom → type, Enter. If it already exists in Rest/Done it is moved back instead of duplicated.
- **`REST (n) ▸`** → show/hide the Rest list (click a Rest item to complete it).
- **Right-click an item** → Move to Rest/Today, Snooze until… (adds `⏳ YYYY-MM-DD`; on that day it moves to Today by itself), Edit…, Delete.
- **Top-right tab** or **double-click the header** → shrink to a tile; click the tile to restore. **Drag** the header to move.
- **Right-click** → Undo done, Skins (incl. Dalek), Reload, Open file, Change backing file…, Clean done items (visual only), Exit.
- **Drag an item** up/down to re-order it (click without dragging = done).
- Edits made in Obsidian show up within a second.

One-off file override (not remembered): `python -m queryminder --file "D:\path\todos.md"`.
Autostart on Windows: `Queryminder.lnk` in `shell:startup` launches it at login; delete it to stop.

Autostart on macOS: save this as `~/Library/LaunchAgents/com.queryminder.plist` with your paths, then run `launchctl load` on it (`launchctl unload` and delete it to stop):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.queryminder</string>
  <key>ProgramArguments</key>
  <array><string>/opt/homebrew/bin/python3</string><string>-m</string><string>queryminder</string></array>
  <key>WorkingDirectory</key><string>/path/to/queryminder</string>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
```

Docs: [scope](docs/SCOPE.md) · [architecture](docs/ARCHITECTURE.md). Tests: `python -m unittest -v`.

## License

Licensed under the GPL-3.0. See [LICENSE](LICENSE).
