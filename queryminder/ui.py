"""Tkinter UI: an always-on-top, borderless to-do card.

Interaction summary
  * left-click an item        -> mark done, move it to "## Done" (Today or Rest)
  * type in the bottom field  -> Enter adds to the top of "## Today" (duplicate-aware)
  * "REST (n)" heading         -> show / hide the Rest list
  * top-right button          -> collapse to a small tile / restore
  * drag the header or tile   -> move the window (position is remembered)
  * right-click an item       -> move, snooze, edit, delete (+ the regular menu)
  * right-click anywhere      -> menu: add, undo, reload, open file, skins, exit
"""

from __future__ import annotations

import datetime as dt
import math
import random
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from typing import Callable

from . import compat, macos, model, monitors, picker, settings as settings_mod
from .model import REST, TODAY, Completion, TodoError, TodoItem
from .skins import ANIMATIONS, MASCOTS, SKINS, Frame, Skin, get_skin
from .store import Snapshot, TodoFile

TRANSPARENT = compat.TRANSPARENT  # root background: see-through
POLL_MS = 1000
TOPMOST_EVERY = 5  # polls
COMPLETE_DELAY_MS = 450  # strike-through animation before the item moves
PLACEHOLDER = "add item…"
REST_MAX_H = 200  # px before the Rest list scrolls
DATE_HINT = "date: fri · +3 · 10-28 · 2026-10-28 — Enter / Esc"


@dataclass(frozen=True)
class DoneRow:
    """An item done today. ``completion`` is set if the app moved it to Done (undo = move back);
    None if it was ticked in place inside ## Today (undo = untick)."""

    item: TodoItem
    completion: Completion | None


def _today_iso() -> str:
    return dt.date.today().isoformat()


def _stardate() -> str:
    """Playful TNG-style stardate: 1000 units per year since 1900, e.g. 126802.7."""
    d = dt.date.today()
    days = 366 if d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0) else 365
    return f"{(d.year - 1900) * 1000 + (d.timetuple().tm_yday - 1) * 1000 / days:.1f}"


def _today_label() -> str:
    return dt.date.today().strftime("%a %b %d").upper()


def _short_date(d: dt.date) -> str:
    """``Wed 28``; adds the month when it is not the current month."""
    label = f"{d:%a} {d.day}"
    today = dt.date.today()
    return label if (d.year, d.month) == (today.year, today.month) else f"{label} {d:%b}"


def _clip(text: str, n: int = 30) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"

class App:
    def __init__(self, root: tk.Tk, todo_file: TodoFile, settings: dict):
        self.root = root
        self.file = todo_file
        self.settings = settings
        self.skin: Skin = get_skin(settings.get("skin"))
        if compat.IS_MAC:  # Aqua's default scale depends on the Tk version: pin it so fonts match px()
            root.tk.call("tk", "scaling", 96 / 72)
        self.s = max(1.0, root.winfo_fpixels("1i") / 96.0)  # DPI scale for pixel sizes
        self.width = self.px(300)

        self.items: list[TodoItem] = []  # pending, shown first
        self.done_rows: list[DoneRow] = []  # done today, shown struck-through below
        self.rest: list[TodoItem] = []  # open items in ## Rest
        self.has_rest = False
        self.rest_open = bool(settings.get("rest_open", False))
        # True while an inline field (Edit… / Pick date…) is open: rendering is deferred
        # so the 1 s poll can't destroy it, and item clicks are ignored.
        self.editing = False
        self._row_widgets: dict[tuple[str, str], tuple[tk.Frame, tk.Label]] = {}
        self._promoted: list[str] = []
        self.error: str | None = None
        self.last_sig = None
        self.hidden_done: set[str] = set()  # ticked-in-Today rows hidden by "Clean done items" (session only)
        self.done_log: list[Completion] = self._load_done_log()  # completions made today
        self.minimized = bool(settings.get("minimized", False))
        self.busy = False
        self.status = ""
        self.status_is_error = False
        self._status_job: str | None = None
        self._poll_count = 0
        self._date = _today_iso()
        self._drag: dict | None = None
        self._reorder: dict | None = None  # item drag-and-drop state (see item_row)
        self._pending_rows: dict[str, list[tk.Frame]] = {}  # section -> open-item row frames, in order
        # True while the right-click menu is open. On Windows tk_popup() runs a modal loop
        # but after() timers keep firing; re-asserting -topmost then would raise the card
        # above its own menu, so the periodic topmost/placement refresh is paused.
        self._menu_open = False
        # Header animation state (see schedule_anim / play_anim).
        self.anim_canvas: tk.Canvas | None = None
        self.tile_anim_canvas: tk.Canvas | None = None
        self._anim_job: str | None = None
        self._anim_gen = 0
        self._anim_last: str | None = None
        self._anim_playing = False

        self.make_borderless()
        root.attributes("-topmost", True)
        try:
            if compat.IS_MAC:
                root.attributes("-transparent", True)
            else:
                root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        root.configure(bg=TRANSPARENT)
        for seq in compat.MENU_EVENTS:
            root.bind_all(seq, self.show_menu)
        root.protocol("WM_DELETE_WINDOW", self.exit)
        if compat.IS_MAC:
            root.createcommand("tk::mac::Quit", self.exit)  # Cmd-Q / Dock > Quit

        # Restore the saved position; ensure_on_screen() below validates it against the
        # monitors that exist *now* (e.g. a second monitor that has been unplugged).
        x, y = settings.get("x"), settings.get("y")
        saved = (x, y) if isinstance(x, int) and isinstance(y, int) else None
        start = saved or monitors.default_position(self.width, self.current_monitors())
        if compat.IS_MAC:  # Aqua places a new window when idle, overwriting a position set before that
            root.update_idletasks()
        root.geometry(f"+{start[0]}+{start[1]}")

        self.outer: tk.Frame | None = None
        self.build()
        self.load()
        self.ensure_on_screen(full=True)
        if compat.IS_MAC:
            root.update_idletasks()  # the window must exist
            try:
                macos.show_everywhere()
            except (OSError, AttributeError, ValueError):
                pass  # the card still works, just with a Dock icon and on one Space
        root.after(POLL_MS, self.poll)

    # ------------------------------------------------------------------ helpers

    def make_borderless(self) -> None:
        """No title bar. On Tk 9 Aqua, overrideredirect leaves the title bar or, if the window
        is withdrawn first, a window that can't take keyboard focus; an empty style mask has
        neither problem. Tk 8.6 has no -stylemask."""
        if compat.IS_MAC:
            try:
                self.root.attributes("-stylemask", "")
                self.root.geometry("")  # or the window stops following its content's height
                return
            except tk.TclError:
                pass
        self.root.overrideredirect(True)

    def px(self, n: float) -> int:
        return int(round(n * self.s))

    def current_monitors(self) -> list[monitors.Monitor]:
        found = monitors.work_areas()
        if found:
            return found
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        return [monitors.Monitor(monitors.Rect(0, 0, sw, sh), primary=True)]

    def ensure_on_screen(self, full: bool) -> None:
        """Keep the window on an existing monitor.

        full=True: also nudge it fully inside its monitor (startup, minimize toggle).
        full=False: only rescue it if it can no longer be grabbed (periodic check,
        so a window the user parks half off-screen is left alone).
        """
        if self._drag or self._menu_open:
            return
        self.root.update_idletasks()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        mons = self.current_monitors()
        if not full and monitors.is_reachable(x, y, w, mons):
            return
        nx, ny = monitors.fit(x, y, w, h, mons)
        if (nx, ny) != (x, y):
            self.root.geometry(f"+{nx}+{ny}")
            self.root.update_idletasks()
            self.save_settings()

    def font(self, size: int, bold: bool = False, overstrike: bool = False) -> tkfont.Font:
        families = set(tkfont.families(self.root))
        family = next((f for f in self.skin.fonts if f in families), "Courier New")
        return tkfont.Font(
            root=self.root,
            family=family,
            size=size,
            weight="bold" if bold else "normal",
            overstrike=overstrike,
        )

    def bind_menu(self, widget: tk.Widget) -> None:
        """Open the menu from this widget without also running its own click binding
        (control-click is a <Button-1> to anything not bound to it specifically)."""

        def context(e):
            self.show_menu(e)
            return "break"  # don't also run the global bind_all menu

        for seq in compat.MENU_EVENTS:
            widget.bind(seq, context)

    def fmt(self, template: str) -> str:
        return template.replace("{date}", _today_label()).replace("{stardate}", _stardate())

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        """(Re)build every widget for the current skin."""
        if self.outer is not None:
            self.outer.destroy()
        self._anim_gen += 1  # orphan any running animation of the old widgets
        self._anim_playing = False
        sk = self.skin
        self.f_title = self.font(10, bold=True)
        self.f_item = self.font(10)
        self.f_item_done = self.font(10, overstrike=True)
        self.f_small = self.font(8, bold=True)
        self.f_tiny = self.font(7)
        self.f_tiny_done = self.font(7, overstrike=True)
        mono = "Consolas" if "Consolas" in tkfont.families(self.root) else "Menlo"
        self.f_tag = tkfont.Font(root=self.root, family=mono, size=8, weight="bold")
        # Stamp text is rotated, which bitmap fonts (e.g. Fixedsys) cannot do: use TrueType.
        self.f_stamp = tkfont.Font(root=self.root, family=mono, size=14, weight="bold")

        self.outer = outer = tk.Frame(self.root, bg=TRANSPARENT)
        outer.pack()

        # --- expanded card -------------------------------------------------
        self.card = card = tk.Frame(
            outer, bg=sk.paper, highlightthickness=self.px(2), highlightbackground=sk.border, highlightcolor=sk.border
        )

        header = tk.Frame(card, bg=sk.paper, cursor="fleur")
        header.pack(fill="x", padx=self.px(12), pady=(self.px(10), self.px(4)))
        self.anim_canvas = None
        self.tile_anim_canvas = None
        if sk.mascot:
            animated = bool(ANIMATIONS.get(sk.mascot))
            m = self.mascot_canvas(header, sk.mascot, self.px(3), animated=animated)
            m.pack(side="left", padx=(0, self.px(6)))
            # Click = play an animation now (if the mascot has any); double-click = minimize.
            self.make_draggable(m, on_click=self.play_anim if animated else None, on_double=self.toggle_minimized)
            if animated:
                self.anim_canvas = m
                m.configure(cursor="hand2")
        self.title_lbl = tk.Label(
            header, text=self.fmt(sk.title), bg=sk.paper, fg=sk.accent, font=self.f_title, cursor="fleur"
        )
        self.title_lbl.pack(side="left", fill="x", expand=True)
        # Header: drag to move, double-click = same as the "–" button (minimize).
        self.make_draggable(header, on_double=self.toggle_minimized)
        self.make_draggable(self.title_lbl, on_double=self.toggle_minimized)

        self.dotted_rule(card)

        sec = tk.Frame(card, bg=sk.paper)
        sec.pack(fill="x", padx=self.px(12), pady=(self.px(8), self.px(4)))
        self.section_lbl = tk.Label(sec, text="", bg=sk.paper, fg=sk.accent, font=self.f_small, anchor="w")
        self.section_lbl.pack(side="left")
        self.sec_stamp = tk.Canvas(
            sec, width=self.px(90), height=self.px(22), bg=sk.paper, highlightthickness=0
        )
        self.sec_stamp.pack(side="left", padx=(self.px(8), 0))

        self.items_frame = tk.Frame(card, bg=sk.paper)
        self.items_frame.pack(fill="x", padx=self.px(12), pady=(0, self.px(6)))

        # Rest: heading toggle + (when open) a scrollable list. Filled by render().
        self.rest_frame = tk.Frame(card, bg=sk.paper)
        self.rest_frame.pack(fill="x", padx=self.px(12), pady=(0, self.px(4)))

        self.dotted_rule(card)

        add = tk.Frame(card, bg=sk.paper)
        add.pack(fill="x", padx=self.px(12), pady=(self.px(6), self.px(2)))
        plus = tk.Label(add, text="+", bg=sk.paper, fg=sk.accent, font=self.f_title, cursor="hand2")
        plus.pack(side="left", padx=(0, self.px(6)))
        self.entry = tk.Entry(
            add,
            bg=sk.paper,
            fg=sk.muted,
            insertbackground=sk.ink,
            relief="flat",
            highlightthickness=0,
            font=self.f_item,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self._entry_focus_in)
        self.entry.bind("<FocusOut>", self._entry_focus_out)
        self.entry.bind("<Button-1>", lambda e: self.entry.focus_force())
        self.entry.bind("<Return>", lambda e: self.add_from_entry())
        self.entry.bind("<Escape>", self._entry_escape)
        plus.bind("<Button-1>", lambda e: self.focus_entry())
        self.bind_menu(plus)

        self.status_lbl = tk.Label(card, text="", bg=sk.paper, fg=sk.muted, font=self.f_tiny, anchor="e")
        self.status_lbl.pack(fill="x", padx=self.px(10), pady=(0, self.px(4)))

        # --- minimized tile ------------------------------------------------
        self.tile = tk.Frame(
            outer, bg=sk.paper, highlightthickness=self.px(2), highlightbackground=sk.border, cursor="hand2"
        )
        if sk.mascot:
            # Same animations as the header (sprite only; the tile count stays). Animated:
            # the count is drawn on the mascot canvas so the tile stays compact and wide
            # frames (death ray, glide) pass over it.
            animated = self.anim_canvas is not None
            tm = self.mascot_canvas(self.tile, sk.mascot, self.px(2), animated=animated)
            tm.pack(side="left", padx=(self.px(4), self.px(4) if animated else 0), pady=0 if animated else self.px(4))
            self.make_draggable(tm, on_click=self.restore)
            if animated:
                self.tile_anim_canvas = tm
                sprite_h = len(MASCOTS[sk.mascot][0]) * self.px(2)
                h = max(sprite_h + 2 * self.px(4), self.f_title.metrics("linespace") + 2 * self.px(6))
                tm.configure(height=h)
                tm.sprite_dy = (h - sprite_h) // 2  # type: ignore[attr-defined]
                self.draw_sprite(tm, sk.mascot, MASCOTS[sk.mascot][0], self.px(2))
        self.tile_lbl: tk.Label | None = None
        if self.tile_anim_canvas is None:
            self.tile_lbl = tk.Label(self.tile, text="", bg=sk.paper, fg=sk.accent, font=self.f_title, cursor="hand2")
            self.tile_lbl.pack(side="left", padx=self.px(8), pady=self.px(6))
            self.make_draggable(self.tile_lbl, on_click=self.restore)
        self.make_draggable(self.tile, on_click=self.restore)

        # --- minimize / restore button (overhangs the top-right corner) ----
        self.min_btn = tk.Label(
            outer,
            text="–",
            bg=sk.button_bg,
            fg=sk.button_fg,
            font=self.f_title,
            width=2,
            cursor="hand2",
        )
        self.min_btn.bind("<Button-1>", lambda e: self.toggle_minimized())
        self.bind_menu(self.min_btn)

        self.rendered: tuple | None = None
        self.editing = False
        self.layout()
        self.render()
        self.set_status(self.status, self.status_is_error, sticky=True)
        self.schedule_anim()

    def layout(self) -> None:
        """Show either the card or the tile, keeping the top-right corner fixed."""
        self.root.update_idletasks()
        right = self.root.winfo_rootx() + self.root.winfo_width()
        top = self.root.winfo_rooty()
        had_size = self.root.winfo_width() > 1

        self.card.pack_forget()
        self.tile.pack_forget()
        target = self.tile if self.minimized else self.card
        target.pack(padx=(0, self.px(10)), pady=(self.px(8), 0))
        self.min_btn.configure(text="+" if self.minimized else "–")
        self.min_btn.place(relx=1.0, x=0, y=self.px(14), anchor="ne")
        self.min_btn.lift()

        if had_size:
            self.root.update_idletasks()
            self.root.geometry(f"+{right - self.root.winfo_width()}+{top}")

    def dotted_rule(self, parent: tk.Widget) -> None:
        sk = self.skin
        if sk.rule == "lcars":
            self.lcars_rule(parent)
            return
        if sk.rule == "teeth":
            self.teeth_rule(parent)
            return
        if sk.rule == "paws":
            self.paws_rule(parent)
            return
        h = self.px(3)
        c = tk.Canvas(parent, width=self.width, height=h, bg=self.skin.paper, highlightthickness=0)
        c.pack(fill="x", padx=self.px(10))
        step, dot = self.px(5), self.px(2)
        for x in range(0, self.width, step):
            c.create_rectangle(x, 0, x + dot, dot, fill=self.skin.accent, outline="")

    def teeth_rule(self, parent: tk.Widget) -> None:
        """Domo-kun's mouth: red band with white teeth top and bottom."""
        sk, h, t = self.skin, self.px(10), self.px(10)
        c = tk.Canvas(parent, width=self.width, height=h, bg=sk.paper, highlightthickness=0)
        c.pack(fill="x", padx=self.px(10), pady=self.px(2))
        c.create_rectangle(0, 0, self.width, h, fill=sk.accent, outline="")
        for x in range(0, self.width, t):
            c.create_polygon(x, 0, x + t, 0, x + t / 2, h * 0.5, fill="#ffffff", outline="")
            c.create_polygon(x + t / 2, h, x + t * 1.5, h, x + t, h * 0.5, fill="#ffffff", outline="")

    def paws_rule(self, parent: tk.Widget) -> None:
        """A trail of little paw prints."""
        sk, h, step = self.skin, self.px(10), self.px(24)
        c = tk.Canvas(parent, width=self.width, height=h + self.px(2), bg=sk.paper, highlightthickness=0)
        c.pack(fill="x", padx=self.px(10))
        for i, x in enumerate(range(self.px(4), self.width - self.px(10), step)):
            dy = self.px(2) if i % 2 else 0  # alternate like footsteps
            self.draw_paw(c, x, dy, self.px(10), sk.muted)

    def draw_paw(self, c: tk.Canvas, x: float, y: float, size: float, color: str) -> None:
        """Paw print fitting in a size x size box at (x, y)."""
        s = size / 10
        c.create_oval(x + 2.5 * s, y + 4.5 * s, x + 7.5 * s, y + 9.5 * s, fill=color, outline="")  # pad
        for tx, ty in ((0.5, 3.0), (2.8, 0.5), (5.2, 0.5), (7.5, 3.0)):  # toes
            c.create_oval(x + tx * s, y + ty * s, x + (tx + 2.2) * s, y + (ty + 2.6) * s, fill=color, outline="")

    def lcars_rule(self, parent: tk.Widget) -> None:
        """Segmented LCARS bar: coloured blocks with gaps, rounded outer ends."""
        sk, h, gap = self.skin, self.px(8), self.px(3)
        c = tk.Canvas(parent, width=self.width, height=h, bg=sk.paper, highlightthickness=0)
        c.pack(fill="x", padx=self.px(10), pady=self.px(2))
        widths = (0.32, 0.08, 0.22, 0.05, 0.18, 0.15)  # fractions of the bar
        colors = sk.rule_colors or (sk.accent,)
        x = 0.0
        for i, frac in enumerate(widths):
            w = self.width * frac - gap
            color = colors[i % len(colors)]
            x0, x1 = x, x + w
            if i == 0:  # rounded left cap
                c.create_oval(x0, 0, x0 + h, h, fill=color, outline="")
                x0 += h / 2
            if i == len(widths) - 1:  # rounded right cap
                x1 = self.width
                c.create_oval(x1 - h, 0, x1, h, fill=color, outline="")
                x1 -= h / 2
            c.create_rectangle(x0, 0, x1, h, fill=color, outline="")
            x += w + gap

    def mascot_canvas(self, parent: tk.Widget, key: str, p: int, animated: bool = False) -> tk.Canvas:
        """Pixel-art mascot. ``animated``: sized to fit the widest animation frame too."""
        rows, _palette = MASCOTS[key]
        sprites = [rows] + ([f.rows for a in ANIMATIONS.get(key, ()) for f in a.frames] if animated else [])
        w = max(len(r) for s in sprites for r in s) * p
        h = max(len(s) for s in sprites) * p
        c = tk.Canvas(parent, width=w, height=h, bg=self.skin.paper, highlightthickness=0, cursor="fleur")
        self.draw_sprite(c, key, rows, p)
        return c

    def draw_sprite(self, c: tk.Canvas, key: str, rows, p: int) -> None:
        """(Re)draw the sprite (canvas items tagged "sprite"), on top of any other items
        such as the tile's count, so e.g. a death ray passes over it. ``c.sprite_dy``
        (optional) shifts it down."""
        palette = MASCOTS[key][1]
        dy = getattr(c, "sprite_dy", 0)
        c.delete("sprite")
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in palette:
                    c.create_rectangle(
                        x * p, dy + y * p, (x + 1) * p, dy + (y + 1) * p, fill=palette[ch], outline="", tags="sprite"
                    )

    def set_tile_text(self, text: str) -> None:
        """Minimized tile count. Animated skins draw it on the mascot canvas (compact tile;
        wide frames draw over it), sized to the base sprite + text like the plain label."""
        if self.tile_lbl is not None:
            self.tile_lbl.configure(text=text)
            return
        c, sk = self.tile_anim_canvas, self.skin
        assert c is not None and sk.mascot
        p, gap = self.px(2), self.px(8)
        base_w = max(len(r) for r in MASCOTS[sk.mascot][0]) * p
        anim_w = max(len(r) for a in ANIMATIONS[sk.mascot] for f in a.frames for r in f.rows) * p
        c.delete("count")
        c.create_text(
            base_w + gap, int(c.cget("height")) // 2, text=text, anchor="w", fill=sk.accent, font=self.f_title, tags="count"
        )
        c.tag_lower("count")
        c.configure(width=max(anim_w, base_w + gap + self.f_title.measure(text) + gap))

    # ------------------------------------------------------------------ header animation
    #
    # Optional per skin (skins.ANIMATIONS[mascot]). After a random idle pause
    # (skin.anim_idle seconds) a random animation (weighted, never the same twice in a
    # row when there is a choice) plays a random number of times. Clicking the mascot
    # plays one right away. Nothing runs while minimized. build() bumps _anim_gen so
    # callbacks belonging to destroyed widgets (skin change) die quietly.

    def schedule_anim(self) -> None:
        if self._anim_job:
            self.root.after_cancel(self._anim_job)
            self._anim_job = None
        if self.anim_canvas is None:
            return
        lo, hi = self.skin.anim_idle
        self._anim_job = self.root.after(int(random.uniform(lo, hi) * 1000), self.play_anim)

    def play_anim(self) -> None:
        self._anim_job = None
        if self.anim_canvas is None or self._anim_playing:
            return
        # Play on whichever mascot is visible: header (card) or tile (minimized, no title).
        if self.minimized and self.tile_anim_canvas is not None:
            target = (self.tile_anim_canvas, self.px(2), False)
        else:
            target = (self.anim_canvas, self.px(3), True)
        anims = ANIMATIONS.get(self.skin.mascot or "", ())
        choices = [a for a in anims if a.name != self._anim_last] or list(anims)
        anim = random.choices(choices, weights=[a.weight for a in choices])[0]
        self._anim_last = anim.name
        frames = list(anim.frames) * random.randint(*anim.repeat)
        self._anim_playing = True
        self._anim_step(self._anim_gen, target, frames, 0)

    def _anim_step(self, gen: int, target: tuple, frames: list[Frame], i: int) -> None:
        """``target`` = (canvas, pixel size, whether to animate the header title)."""
        if gen != self._anim_gen:
            return  # widgets were rebuilt
        c, p, titled = target
        sk = self.skin
        assert sk.mascot
        if i >= len(frames):
            self.draw_sprite(c, sk.mascot, MASCOTS[sk.mascot][0], p)
            if titled:
                self.title_lbl.configure(text=self.fmt(sk.title))
            self._anim_playing = False
            self.schedule_anim()
            return
        f = frames[i]
        self.draw_sprite(c, sk.mascot, f.rows, p)
        if titled:
            self.title_lbl.configure(text=self.fmt(f.title) if f.title else self.fmt(sk.title))
        self.root.after(f.ms, lambda: self._anim_step(gen, target, frames, i + 1))

    def make_draggable(
        self,
        widget: tk.Widget,
        on_click: Callable[[], None] | None = None,
        on_double: Callable[[], None] | None = None,
    ) -> None:
        def press(e):
            self._drag = {"x": e.x_root, "y": e.y_root, "wx": self.root.winfo_x(), "wy": self.root.winfo_y(), "moved": False}

        def motion(e):
            if not self._drag:
                return
            dx, dy = e.x_root - self._drag["x"], e.y_root - self._drag["y"]
            if abs(dx) + abs(dy) > 3:
                self._drag["moved"] = True
            if self._drag["moved"]:
                self.root.geometry(f"+{self._drag['wx'] + dx}+{self._drag['wy'] + dy}")

        def release(e):
            drag, self._drag = self._drag, None
            if drag is None:  # the press opened the menu instead (control-click)
                return
            if drag["moved"]:
                self.save_settings()
            elif on_click:
                on_click()

        widget.bind("<ButtonPress-1>", press)
        widget.bind("<B1-Motion>", motion)
        widget.bind("<ButtonRelease-1>", release)
        self.bind_menu(widget)
        if on_double:
            widget.bind("<Double-Button-1>", lambda e: on_double())

    # ------------------------------------------------------------------ render

    def render(self) -> None:
        if self.editing or self._reorder:
            return
        key = (
            tuple(self.items), tuple(self.done_rows), tuple(self.rest), self.has_rest, self.rest_open,
            self.error, self._date,
        )
        if key == self.rendered:
            return
        self.rendered = key
        sk = self.skin
        self._row_widgets = {}
        self._pending_rows = {}
        for w in self.items_frame.winfo_children():
            w.destroy()
        for w in self.rest_frame.winfo_children():
            w.destroy()
        if not self._anim_playing:
            self.title_lbl.configure(text=self.fmt(sk.title))

        today_done = [r for r in self.done_rows if r.item.section != REST]
        n, d = len(self.items), len(today_done)
        self.section_lbl.configure(
            text=f"{self.fmt(sk.section)}  ({d}/{n + d})" if not self.error else "⚠ PROBLEM"
        )
        self.set_tile_text("!" if self.error else (str(n) if n else "✓"))
        self.sec_stamp.delete("all")
        if not self.error and not n and d:  # everything for today is done: "DONE!" tag
            self.draw_stamp(self.sec_stamp, self.px(45), self.px(11), sk.stamp, self.f_tag, 6)

        if self.error:
            tk.Label(
                self.items_frame,
                text=self.error,
                bg=sk.paper,
                fg=sk.accent,
                font=self.f_item,
                wraplength=self.width - self.px(30),
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=self.px(4))
            return
        if not self.items and not today_done:
            self.stamp(self.items_frame)
        for item in self.items:
            self.item_row(self.items_frame, item)
        for row in today_done:
            self.item_row(self.items_frame, row.item, done_row=row)
        self.render_rest()

    def render_rest(self) -> None:
        """``REST (n) ▸`` toggle and, when open, the Rest items in a scroll area."""
        if not self.has_rest:
            return
        sk = self.skin
        rest_done = [r for r in self.done_rows if r.item.section == REST]  # completed from Rest today
        toggle = tk.Label(
            self.rest_frame, text=f"REST ({len(self.rest)}) {'▾' if self.rest_open else '▸'}",
            bg=sk.paper, fg=sk.muted, font=self.f_small, anchor="w", cursor="hand2",
        )
        toggle.pack(fill="x", pady=(self.px(2), self.px(2)))
        toggle.bind("<Button-1>", lambda e: self.toggle_rest())
        self.bind_menu(toggle)
        toggle.bind("<Enter>", lambda e: toggle.configure(fg=sk.accent))
        toggle.bind("<Leave>", lambda e: toggle.configure(fg=sk.muted))
        if not self.rest_open or not (self.rest or rest_done):
            return
        canvas = tk.Canvas(
            self.rest_frame, bg=sk.paper, highlightthickness=0, width=self.width - self.px(14), height=1,
            yscrollincrement=self.px(10),
        )
        canvas.pack(fill="x")
        inner = tk.Frame(canvas, bg=sk.paper)
        win = canvas.create_window(0, 0, window=inner, anchor="nw")
        widgets: list[tk.Widget] = [canvas, inner]
        for item in self.rest:
            widgets += self.item_row(inner, item)
        for row in rest_done:
            widgets += self.item_row(inner, row.item, done_row=row)
        inner.update_idletasks()
        h = inner.winfo_reqheight()
        canvas.configure(height=min(h, self.px(REST_MAX_H)), scrollregion=(0, 0, 0, h))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        if h > self.px(REST_MAX_H):
            def wheel(e):
                canvas.yview_scroll(compat.wheel_units(e.delta), "units")
                return "break"

            leftover = [0.0]  # trackpad pixels not yet worth a whole scroll unit

            def touchpad(e):  # Tk 9 reports trackpads separately, in pixels
                dy = float(self.root.tk.splitlist(self.root.tk.call("tk::PreciseScrollDeltas", e.delta))[1])
                step = self.px(10)
                units = int((leftover[0] + dy) / step)
                leftover[0] += dy - units * step
                if units:
                    canvas.yview_scroll(-units, "units")
                return "break"

            for w in widgets:
                w.bind("<MouseWheel>", wheel)
                if compat.IS_MAC:
                    try:
                        w.bind("<TouchpadScroll>", touchpad)
                    except tk.TclError:  # Tk 8.6 has no such event; flicks arrive as <MouseWheel>
                        break

    def item_row(self, parent: tk.Widget, item: TodoItem, done_row: DoneRow | None = None) -> list[tk.Widget]:
        """A pending item (click = complete) or, with ``done_row``, a done one (click = undo).
        Returns the row's widgets."""
        sk = self.skin
        rest = item.section == REST
        row = tk.Frame(parent, bg=sk.paper, cursor="hand2")
        row.pack(fill="x", pady=self.px(3))
        size = self.px(14)
        box = tk.Canvas(row, width=size, height=size, bg=sk.paper, highlightthickness=0, cursor="hand2")
        box.pack(side="left", anchor="n", pady=(self.px(2), 0), padx=(0, self.px(8)))
        done = done_row is not None
        self.draw_box(box, size, checked=done)
        wrap = self.width - self.px(52)
        extra: list[tk.Widget] = []
        if item.scheduled is not None:
            badge = tk.Label(
                row, text=f"\u23f3 {_short_date(item.scheduled)}", bg=sk.paper, fg=sk.accent,
                font=self.f_tiny, cursor="hand2",
            )
            badge.pack(side="right", anchor="n", pady=(self.px(2), 0), padx=(self.px(4), 0))
            wrap -= self.px(60)
            extra.append(badge)
        body = tk.Frame(row, bg=sk.paper, cursor="hand2")
        body.pack(side="left", fill="x", expand=True)
        base_fg = sk.muted if done or rest else sk.ink
        lbl = tk.Label(
            body, text=item.text, bg=sk.paper, fg=base_fg, font=self.f_item_done if done else self.f_item,
            wraplength=wrap, justify="left", anchor="w", cursor="hand2",
        )
        lbl.pack(fill="x")
        if not done:
            self._row_widgets.setdefault((item.section, item.text), (body, lbl))
            self._pending_rows.setdefault(item.section, []).append(row)
        widgets = [row, box, body, lbl, *extra]
        for child in item.children:
            m = model.ITEM_RE.match(child)
            text = (m.group("text") or "") if m else child.strip().lstrip("-*+ ")
            child_done = bool(m and m.group("mark") in "xX")
            c = tk.Label(
                body, text=f"↳ {text}", bg=sk.paper, fg=sk.muted,
                font=self.f_tiny_done if child_done else self.f_tiny,
                wraplength=wrap, justify="left", anchor="w", cursor="hand2",
            )
            c.pack(fill="x")
            widgets.append(c)

        def enter(_):
            if not self.busy:
                lbl.configure(fg=sk.accent)

        def leave(_):
            lbl.configure(fg=base_fg)

        def context(e):
            self.show_menu(e, item=None if done else item, done_row=done_row)
            return "break"  # don't also run the global bind_all menu

        for w in widgets:
            if done_row is not None:
                w.bind("<Button-1>", lambda e, r=done_row: self.on_done_click(r))
            else:  # click = complete; press-and-drag = reorder
                w.bind("<ButtonPress-1>", lambda e, it=item: self.reorder_press(e, it))
                w.bind("<B1-Motion>", self.reorder_motion)
                w.bind("<ButtonRelease-1>", lambda e, it=item, b=box, l=lbl: self.reorder_release(e, it, b, l))
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            for seq in compat.MENU_EVENTS:
                w.bind(seq, context)
        return widgets

    def draw_box(self, c: tk.Canvas, size: int, checked: bool) -> None:
        c.delete("all")
        sk, w, pad = self.skin, self.px(2), self.px(1)
        shape = c.create_oval if sk.check_shape == "circle" else c.create_rectangle
        if sk.check_shape == "paw":
            shape(pad, pad, size - pad, size - pad, outline=sk.check, width=w)
            if checked:
                inner = size - 4 * pad
                self.draw_paw(c, 2 * pad, 2 * pad, inner, sk.accent)
            return
        if checked:
            shape(pad, pad, size - pad, size - pad, outline=sk.check, width=w, fill=sk.accent)
        else:
            shape(pad, pad, size - pad, size - pad, outline=sk.check, width=w)

    def stamp(self, parent: tk.Widget) -> None:
        sk = self.skin
        h = self.px(70)
        c = tk.Canvas(parent, width=self.width - self.px(30), height=h, bg=sk.paper, highlightthickness=0)
        c.pack(fill="x")
        cx = (self.width - self.px(30)) / 2
        self.draw_stamp(c, cx, h / 2 - self.px(6), sk.stamp, self.f_stamp, 8)
        c.create_text(cx, h - self.px(8), text=sk.empty, fill=sk.muted, font=self.f_tiny)

    def draw_stamp(self, c: tk.Canvas, cx: float, cy: float, text: str, font: tkfont.Font, angle: float) -> None:
        """Rotated rubber-stamp text with a rotated frame around it."""
        sk = self.skin
        c.create_text(cx, cy, text=text, angle=angle, fill=sk.accent, font=font)
        hw = font.measure(text) / 2 + self.px(5)
        hh = font.metrics("linespace") / 2 + self.px(1)
        t = math.radians(angle)
        pts = []
        for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
            pts += [cx + dx * math.cos(t) + dy * math.sin(t), cy - dx * math.sin(t) + dy * math.cos(t)]
        c.create_polygon(pts, outline=sk.accent, fill="", width=self.px(2))

    # ------------------------------------------------------------------ status

    def set_status(self, text: str, error: bool = False, sticky: bool = False) -> None:
        self.status, self.status_is_error = text, error
        if not hasattr(self, "status_lbl"):
            return
        self.status_lbl.configure(text=text, fg=self.skin.accent if error else self.skin.muted)
        if self._status_job:
            self.root.after_cancel(self._status_job)
            self._status_job = None
        if not sticky and not error:
            self._status_job = self.root.after(3000, self.idle_status)

    def idle_status(self) -> None:
        self._status_job = None
        self.set_status(f"synced {dt.datetime.now():%H:%M} · {self.file.path.name}", sticky=True)

    # ------------------------------------------------------------------ data

    def load(self, quiet: bool = False) -> None:
        try:
            snap = self.file.read()
            self.apply(snap)
            if not quiet:
                self.idle_status()
            if not self.busy and model.due_items(snap.text, dt.date.today()):
                self.edit(lambda text: text)  # edit() promotes due Rest items
        except FileNotFoundError:
            self.last_sig = None
            self.items, self.error = [], f"File not found:\n{self.file.path}"
            self.render()
        except (OSError, UnicodeDecodeError) as e:
            self.set_status(f"read failed: {e}", error=True)

    def apply(self, snap: Snapshot) -> None:
        self.last_sig = snap.signature
        try:
            today = model.today_items(snap.text)
            self.items, self.error = [i for i in today if not i.done], None
            # Done today = what we moved to Done today (still there) + items ticked in place in Today.
            self.done_rows = [
                DoneRow(TodoItem(c.text, True, c.done_block[1:], section=c.section), c)
                for c in self.done_log
                if model.completion_in_done(snap.text, c)
            ] + [DoneRow(i, None) for i in today if i.done and i.text not in self.hidden_done]
            self.rest = model.rest_items(snap.text)
            self.has_rest = model.has_section(snap.text, REST)
        except TodoError as e:
            self.items, self.done_rows, self.rest, self.error = [], [], [], str(e)
        self.render()

    def poll(self) -> None:
        try:
            self._poll_count += 1
            if self._poll_count % TOPMOST_EVERY == 0 and not self._menu_open:
                self.root.attributes("-topmost", True)
                self.ensure_on_screen(full=False)  # monitor unplugged / resolution changed
            if _today_iso() != self._date:  # new day: yesterday's done items stop showing
                self._date = _today_iso()
                self.done_log = []
                self.hidden_done.clear()
                self.save_settings()
                self.load(quiet=True)
            if not self.busy and self.file.signature() != self.last_sig:
                self.load()
        finally:
            self.root.after(POLL_MS, self.poll)

    def edit(self, fn: Callable[[str], str]) -> bool:
        """Apply ``fn`` to the freshest file text and write it. Returns success.

        Every write also moves due scheduled Rest items to Today and, if anything
        changed, sets the frontmatter ``updated:`` date."""
        promoted: list[str] = []

        def full(text: str) -> str:
            new, moved = model.promote_due(fn(text), dt.date.today())
            promoted[:] = moved
            return text if new == text else model.touch_updated(new, _today_iso())

        try:
            self.apply(self.file.update(full))
            if promoted:
                self.set_status(f"\u23f3 now for today: {_clip(', '.join(promoted), 40)}")
            return True
        except TodoError as e:
            message = str(e)
        except OSError as e:
            message = f"write failed: {e}"
        self.load(quiet=True)
        self.set_status(message, error=True)
        return False

    # ------------------------------------------------------------------ actions

    def on_item_click(self, item: TodoItem, box: tk.Canvas, lbl: tk.Label) -> None:
        if self.busy or self.editing:
            return
        self.busy = True
        self.draw_box(box, int(box.cget("width")), checked=True)
        lbl.configure(font=self.f_item_done, fg=self.skin.muted)
        self.root.after(COMPLETE_DELAY_MS, lambda: self.complete(item))

    def complete(self, item: TodoItem) -> None:
        done: list[Completion] = []

        def fn(text: str) -> str:
            new, completion = model.complete_item(text, item.text, item.section, dt.date.today())
            done.append(completion)
            self.hidden_done.discard(completion.text)
            self.done_log.append(completion)  # before the write so the re-render shows it as done
            return new

        try:
            if self.edit(fn):
                self.save_settings()
                self.set_status(self.skin.flash)
            elif done and done[-1] in self.done_log:
                self.done_log.remove(done[-1])
                self.load(quiet=True)
        finally:
            self.busy = False

    # --- reordering (docs/SCOPE.md §13)

    def _siblings(self, item: TodoItem) -> list[TodoItem]:
        return self.items if item.section == TODAY else self.rest

    def reorder(self, item: TodoItem, to_pos: int) -> None:
        sibs = self._siblings(item)
        if item not in sibs or self.busy or self.editing:
            return
        from_pos = sibs.index(item)
        if self.edit(lambda t: model.reorder_item(t, item.section, item.text, from_pos, to_pos)):
            self.set_status("moved")

    def reorder_press(self, e, item: TodoItem) -> None:
        self._reorder = {"item": item, "y": e.y_root, "moved": False, "slot": None, "line": None}

    def _slot_at(self, item: TodoItem, y_root: int) -> tuple[int, int] | None:
        """(slot, line y in parent coords): the gap, counted in rows, the pointer is over."""
        rows = [r for r in self._pending_rows.get(item.section, []) if r.winfo_exists()]
        if not rows:
            return None
        slot = len(rows)
        for i, r in enumerate(rows):
            if y_root < r.winfo_rooty() + r.winfo_height() // 2:
                slot = i
                break
        if slot < len(rows):
            y = rows[slot].winfo_y() - self.px(2)
        else:
            y = rows[-1].winfo_y() + rows[-1].winfo_height() + self.px(1)
        return slot, y

    def reorder_motion(self, e) -> None:
        st = self._reorder
        if not st:
            return
        if not st["moved"]:
            if abs(e.y_root - st["y"]) <= 4:
                return
            st["moved"] = True
        item = st["item"]
        hit = self._slot_at(item, e.y_root)
        if hit is None:
            return
        st["slot"], y = hit
        rows = self._pending_rows[item.section]
        if st["line"] is None or not st["line"].winfo_exists():
            st["line"] = tk.Frame(rows[0].master, bg=self.skin.accent, height=self.px(2))
        st["line"].place(x=0, y=y, relwidth=1)
        st["line"].lift()

    def reorder_release(self, e, item: TodoItem, box: tk.Canvas, lbl: tk.Label) -> None:
        st, self._reorder = self._reorder, None
        if not st:
            return
        if st["line"] is not None and st["line"].winfo_exists():
            st["line"].destroy()
        if not st["moved"]:
            self.on_item_click(item, box, lbl)
            return
        sibs = self._siblings(item)
        if st["slot"] is not None and item in sibs:
            frm = sibs.index(item)
            slot = st["slot"]
            to = slot if slot <= frm else slot - 1
            if to != frm:
                self.reorder(item, to)
        self.render()

    def on_done_click(self, row: DoneRow) -> None:
        """Clicking a done item un-does it."""
        if self.busy or self.editing:
            return
        if row.completion is None:
            if self.edit(lambda text: model.uncheck_today_item(text, row.item.text)):
                self.set_status(f"reopened: {row.item.text}")
        else:
            self.undo(row.completion)

    def undo(self, completion: Completion | None = None) -> None:
        """Move a completion (default: the latest shown one) back to Today."""
        if completion is None:
            logged = [r.completion for r in self.done_rows if r.completion is not None]
            if not logged:
                return
            completion = logged[-1]
        if completion in self.done_log:
            self.done_log.remove(completion)
        if self.edit(lambda text: model.undo_completion(text, completion)):
            self.set_status(f"undid: {completion.text}")
        self.save_settings()

    def add_from_entry(self) -> None:
        text = self.entry.get()
        if self.entry.cget("fg") == self.skin.muted or not text.strip():
            return
        result: list = []

        def fn(t: str) -> str:
            new, outcome, completion = model.add_to_today(t, text, self.done_log)
            result[:] = [outcome, completion]
            return new

        if not self.edit(fn):
            return
        outcome, completion = result
        if completion is not None and completion in self.done_log:
            self.done_log.remove(completion)
            self.save_settings()
        self.entry.delete(0, "end")
        self.set_status({
            "exists": "already in Today",
            "unchecked": "reopened",
            "from_rest": "moved from Rest",
            "undone": "undid done",
            "from_done": "reopened from Done",
        }.get(outcome, "added"))

    # --- item menu actions (docs/SCOPE.md §10-14)

    def move(self, item: TodoItem, dst: str) -> None:
        if self.edit(lambda t: model.move_item(t, item.text, item.section, dst)):
            self.set_status(f"moved to {dst.title()}")

    def snooze(self, item: TodoItem, when: dt.date) -> bool:
        if self.edit(lambda t: model.schedule_item(t, item.text, item.section, when, dt.date.today())):
            due = when <= dt.date.today()
            self.set_status("moved to Today" if due else f"\u23f3 {_short_date(when)}")
            return True
        return False

    def clear_schedule(self, item: TodoItem) -> None:
        if self.edit(lambda t: model.clear_schedule(t, item.text)):
            self.set_status("schedule cleared")

    def delete(self, item: TodoItem) -> None:
        if self.edit(lambda t: model.delete_item(t, item.section, item.text)):
            self.set_status(f"deleted: {_clip(item.text)}")

    def clean_done(self) -> None:
        """Visual only: hide today's done rows. The file is never touched."""
        n = len(self.done_rows)
        self.done_log = []
        self.hidden_done.update(r.item.text for r in self.done_rows if r.completion is None)
        self.save_settings()
        self.load(quiet=True)
        self.set_status(f"hid {n} done item{'s' if n != 1 else ''}")

    def start_edit(self, item: TodoItem) -> None:
        def submit(value: str) -> bool:
            if not value.strip() or " ".join(value.split()) == item.text:
                return True  # empty / unchanged = cancel
            if self.edit(lambda t: model.rename_item(t, item.section, item.text, value)):
                self.set_status("edited")
            return True

        self.inline_field(item, item.text, submit, "edit: Enter saves · Esc cancels")

    def pick_date(self, item: TodoItem) -> None:
        def submit(value: str) -> bool:
            if not value.strip():
                return True
            when = model.parse_when(value, dt.date.today())
            if when is None:
                self.set_status(f"? {DATE_HINT}", error=True)
                return False  # keep the field open
            self.snooze(item, when)
            return True

        self.inline_field(item, "", submit, DATE_HINT)

    def inline_field(self, item: TodoItem, initial: str, submit: Callable[[str], bool], hint: str) -> None:
        """Replace the item's label by an Entry. ``submit`` returns False to keep it open."""
        found = self._row_widgets.get((item.section, item.text))
        if found is None or self.editing:
            return
        body, lbl = found
        sk = self.skin
        self.editing = True
        entry = tk.Entry(
            body, bg=sk.paper, fg=sk.ink, insertbackground=sk.ink, relief="flat", font=self.f_item,
            highlightthickness=1, highlightbackground=sk.accent, highlightcolor=sk.accent,
        )
        entry.insert(0, initial)
        entry.pack(fill="x", before=lbl)
        lbl.pack_forget()
        self.set_status(hint, sticky=True)
        closed = False

        def finish(save: bool) -> None:
            nonlocal closed
            if closed:
                return
            if save and submit(entry.get()) is False:
                entry.focus_force()
                return
            closed = True
            self.editing = False
            self.rendered = None
            self.render()
            if not save:
                self.idle_status()

        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<KP_Enter>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))
        entry.bind("<FocusOut>", lambda e: self.root.after(150, lambda: finish(False) if not closed and self.root.focus_get() is not entry else None))
        self.root.focus_force()
        entry.focus_force()
        entry.icursor("end")
        entry.select_range(0, "end")

    def toggle_rest(self) -> None:
        self.rest_open = not self.rest_open
        self.render()
        self.ensure_on_screen(full=True)  # opening it may push the card off the bottom
        self.save_settings()

    def focus_entry(self) -> None:
        if self.minimized:
            self.toggle_minimized()
        self.root.focus_force()
        self.entry.focus_force()

    def _entry_focus_in(self, _=None) -> None:
        if self.entry.cget("fg") == self.skin.muted:
            self.entry.delete(0, "end")
            self.entry.configure(fg=self.skin.ink)

    def _entry_focus_out(self, _=None) -> None:
        if not self.entry.get():
            self.entry.insert(0, PLACEHOLDER)
            self.entry.configure(fg=self.skin.muted)

    def _entry_escape(self, _=None) -> None:
        self.entry.delete(0, "end")
        self.root.focus_set()  # moves focus off the entry -> placeholder returns

    def toggle_minimized(self) -> None:
        self.minimized = not self.minimized
        self.layout()
        self.ensure_on_screen(full=True)  # e.g. restoring near the bottom edge
        self.save_settings()

    def restore(self) -> None:
        if self.minimized:
            self.toggle_minimized()

    def set_skin(self, key: str) -> None:
        self.skin = get_skin(key)
        self.build()
        self.save_settings()

    def change_file(self) -> None:
        """Pick another (or a new) Markdown file to back the card."""
        self._menu_open = True  # pause topmost/placement refresh so the card doesn't cover the dialog
        try:
            if compat.IS_MAC:
                try:
                    macos.activate()
                except (OSError, AttributeError, ValueError):
                    pass
            chosen = picker.choose_file(self.root, self.file.path, title="Change backing file")
        finally:
            self._menu_open = False
        if chosen is None or chosen == self.file.path:
            return
        self.file = TodoFile(chosen)
        self.settings["file"] = str(chosen)
        self.done_log = []  # completions belong to the old file
        self.hidden_done.clear()
        self.rendered = None
        self.last_sig = None
        self.save_settings()
        self.load()

    def open_file(self) -> None:
        try:
            compat.open_path(self.file.path)
        except (OSError, subprocess.SubprocessError) as e:
            self.set_status(f"open failed: {e}", error=True)

    def show_menu(self, event, item: TodoItem | None = None, done_row: DoneRow | None = None) -> None:
        sk = self.skin
        menu = tk.Menu(self.root, tearoff=0)
        if done_row is not None:
            menu.add_command(label=f"Undo done: {_clip(done_row.item.text)}", command=lambda: self.on_done_click(done_row))
            menu.add_separator()
        elif item is not None and not self.editing:
            self.item_menu(menu, item)
            menu.add_separator()
        logged = [r.completion for r in self.done_rows if r.completion is not None]
        if logged:
            last = logged[-1].text
            menu.add_command(label=f"Undo done: {last[:30]}{'…' if len(last) > 30 else ''}", command=self.undo)
        else:
            menu.add_command(label="Undo done", state="disabled")
        menu.add_command(label="Clean done items", command=self.clean_done)
        menu.add_separator()
        skins = tk.Menu(menu, tearoff=0)
        self._skin_var = tk.StringVar(value=sk.key)
        for s in SKINS:
            skins.add_radiobutton(
                label=s.label, value=s.key, variable=self._skin_var, command=lambda k=s.key: self.set_skin(k)
            )
        menu.add_cascade(label="Skins", menu=skins)
        menu.add_command(label="Reload now", command=self.load)
        menu.add_command(label=f"Open {self.file.path.name}", command=self.open_file)
        menu.add_command(label="Change backing file…", command=self.change_file)
        menu.add_separator()
        menu.add_command(label="Exit", command=self.exit)
        self._menu_open = True
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
            self._menu_open = False

    def item_menu(self, menu: tk.Menu, item: TodoItem) -> None:
        """Per-item actions at the top of the context menu."""
        today = dt.date.today()
        menu.add_command(label=_clip(item.text, 36), state="disabled")
        if item.section == TODAY and self.has_rest:
            menu.add_command(label="Move to Rest", command=lambda: self.move(item, REST))
        if item.section == REST:
            menu.add_command(label="Move to Today", command=lambda: self.move(item, TODAY))
        if self.has_rest:
            snooze = tk.Menu(menu, tearoff=0)
            for days in range(1, 8):
                d = today + dt.timedelta(days=days)
                label = f"Tomorrow ({d:%a} {d.day})" if days == 1 else f"{d:%a} {d.day} {d:%b}"
                snooze.add_command(label=label, command=lambda d=d: self.snooze(item, d))
            d = today + dt.timedelta(days=14)
            snooze.add_command(label=f"In 2 weeks ({d:%a} {d.day} {d:%b})", command=lambda: self.snooze(item, d))
            snooze.add_separator()
            snooze.add_command(label="Pick date…", command=lambda: self.pick_date(item))
            menu.add_cascade(label="Reschedule" if item.scheduled else "Snooze until", menu=snooze)
        if item.scheduled is not None:
            menu.add_command(
                label=f"Clear schedule (\u23f3 {_short_date(item.scheduled)})", command=lambda: self.clear_schedule(item)
            )
        menu.add_command(label="Edit…", command=lambda: self.start_edit(item))
        confirm = tk.Menu(menu, tearoff=0)
        confirm.add_command(label=f'Delete "{_clip(item.text)}"', command=lambda: self.delete(item))
        menu.add_cascade(label="Delete", menu=confirm)

    # ------------------------------------------------------------------ lifecycle

    def save_settings(self) -> None:
        self.root.update_idletasks()  # so winfo_x/y reflect any pending geometry change
        self.settings.update(
            skin=self.skin.key, x=self.root.winfo_x(), y=self.root.winfo_y(), minimized=self.minimized,
            rest_open=self.rest_open,
            done_today={
                "date": self._date,
                "items": [
                    {"text": c.text, "original": list(c.original_block), "done": list(c.done_block), "section": c.section}
                    for c in self.done_log
                ],
            },
        )
        settings_mod.save(self.settings)

    def _load_done_log(self) -> list[Completion]:
        data = self.settings.get("done_today")
        if not isinstance(data, dict) or data.get("date") != _today_iso():
            return []
        log = []
        for entry in data.get("items", []):
            try:
                section = REST if entry.get("section") == REST else TODAY
                log.append(Completion(str(entry["text"]), tuple(entry["original"]), tuple(entry["done"]), section))
            except (KeyError, TypeError, AttributeError):
                continue
        return log

    def exit(self) -> None:
        self.save_settings()
        self.root.destroy()
