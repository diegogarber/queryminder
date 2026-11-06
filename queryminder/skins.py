"""Skin definitions. A skin is pure data; ui.py renders it.

To add a skin: add a ``Skin(...)`` to ``SKINS``. Nothing else needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skin:
    key: str
    label: str
    paper: str  # card background
    ink: str  # item text
    muted: str  # secondary text (footer, placeholder)
    accent: str  # title, headings, dotted rules, stamp
    border: str  # card outline
    check: str  # checkbox outline / fill when ticking
    button_bg: str  # minimize button
    button_fg: str
    title: str = "TODAY"  # header text; "{date}" is replaced
    section: str = "PENDING"
    empty: str = "Nothing pending. Nice."
    stamp: str = "DONE!"
    flash: str = "done!"  # footer message after completing an item
    check_shape: str = "square"  # "square" | "circle" | "paw" (square, paw print when ticked)
    fonts: tuple[str, ...] = ("Cascadia Mono", "Consolas", "Courier New")
    mascot: str | None = None  # key into MASCOTS
    rule: str = "dots"  # separator: "dots" | "lcars" (colour bars) | "teeth" (Domo mouth) | "paws"
    rule_colors: tuple[str, ...] = ()  # palette for "lcars" rules
    # Header mascot animations (ANIMATIONS[mascot]): a random one plays after a random
    # idle pause of anim_idle = (min, max) seconds, or right away when the mascot is clicked.
    anim_idle: tuple[float, float] = (25.0, 90.0)
    extra: dict = field(default_factory=dict)


SKINS: list[Skin] = [
    Skin(
        key="paper",
        label="Retro paper",
        paper="#f7efe1",
        ink="#2b2b2b",
        muted="#9a8f80",
        accent="#c8323c",
        border="#2b2b2b",
        check="#2b2b2b",
        button_bg="#d63a3a",
        button_fg="#ffffff",
        title="··· TODAY · {date} ···",
        section="PHASE 1: TODAY",
    ),
    Skin(
        key="dalek",
        label="Dalek",
        paper="#232323",
        ink="#f2c14e",
        muted="#8c7a4a",
        accent="#ff4b2b",
        border="#c9962b",
        check="#c9962b",
        button_bg="#c9962b",
        button_fg="#1a1a1a",
        title="EXTERMINATE!",
        section="TARGETS FOR {date}",
        empty="ALL TARGETS EXTERMINATED.",
        stamp="EXTERMINATED",
        flash="EXTERMINATED!",
        check_shape="circle",
        fonts=("Fixedsys", "Consolas", "Courier New"),
        mascot="dalek",
    ),
    Skin(
        key="tardis",
        label="TARDIS",
        paper="#0f3b78",
        ink="#f4f7ff",
        muted="#8fa9d6",
        accent="#ffffff",
        border="#082650",
        check="#f4f7ff",
        button_bg="#082650",
        button_fg="#ffffff",
        title="POLICE · PUBLIC CALL · BOX",
        section="{date} · BIGGER ON THE INSIDE",
        empty="All of time and space is free.",
        stamp="SORTED",
        flash="allons-y!",
        mascot="tardis",
    ),
    Skin(
        key="terminal",
        label="Green terminal",
        paper="#0c120c",
        ink="#39ff6a",
        muted="#1f8a3a",
        accent="#7dff9b",
        border="#39ff6a",
        check="#39ff6a",
        button_bg="#39ff6a",
        button_fg="#0c120c",
        title="> todo --today {date}",
        section="$ grep '\\[ \\]'",
        empty="0 results. exit 0",
        stamp="OK",
        flash="[ OK ]",
        fonts=("Lucida Console", "Consolas", "Courier New"),
    ),
    Skin(
        key="sticky",
        label="Sticky note",
        paper="#fff59d",
        ink="#3e3a1e",
        muted="#a59c4f",
        accent="#e65100",
        border="#e0c94a",
        check="#3e3a1e",
        button_bg="#e65100",
        button_fg="#ffffff",
        title="today · {date}",
        section="don't forget",
        stamp="YAY",
        fonts=("Segoe Print", "Comic Sans MS", "Segoe UI"),
    ),
    Skin(
        key="lcars",
        label="Star Trek (LCARS)",
        paper="#000000",
        ink="#ffcc99",
        muted="#9999cc",
        accent="#ff9900",
        border="#cc6699",
        check="#99ccff",
        button_bg="#ff9966",
        button_fg="#000000",
        title="CAPTAIN'S LOG",
        section="STARDATE {stardate}",
        empty="All systems nominal.",
        stamp="MAKE IT SO",
        flash="Engage!",
        fonts=("Bahnschrift SemiCondensed", "Arial Narrow", "Segoe UI"),
        mascot="delta",
        rule="lcars",
        rule_colors=("#ff9900", "#cc99cc", "#ffcc99", "#9999cc", "#cc6666", "#ff9966"),
    ),
    Skin(
        key="domo",
        label="Domo-kun",
        paper="#6b3d17",
        ink="#fff3e0",
        muted="#c9a07a",
        accent="#e8352b",
        border="#3e2109",
        check="#fff3e0",
        button_bg="#e8352b",
        button_fg="#ffffff",
        title="CUCUUUUU!!!",
        section="NOM NOM LIST · {date}",
        empty="Domo is full.",
        stamp="NOM!",
        flash="*chomp*",
        fonts=("Cascadia Mono SemiBold", "Consolas", "Courier New"),
        mascot="domo",
        rule="teeth",
    ),
    Skin(
        key="frenchie",
        label="French bulldog",
        paper="#f5e9d8",
        ink="#3b2a20",
        muted="#a08670",
        accent="#e2677a",
        border="#8d6e63",
        check="#3b2a20",
        button_bg="#3b2a20",
        button_fg="#f5e9d8",
        title="WOOF · {date}",
        section="GOOD BOY TASKS",
        empty="Nap time. Zzz...",
        stamp="GOOD BOY!",
        flash="*snort snort*",
        check_shape="paw",
        fonts=("Segoe UI Semibold", "Segoe UI", "Consolas"),
        mascot="frenchie",
        rule="paws",
    ),
]

SKINS_BY_KEY = {s.key: s for s in SKINS}
DEFAULT_SKIN = "paper"


def get_skin(key: str | None) -> Skin:
    return SKINS_BY_KEY.get(key or DEFAULT_SKIN, SKINS_BY_KEY[DEFAULT_SKIN])


# Pixel-art mascots: one char per pixel, "." is transparent.
MASCOTS: dict[str, tuple[list[str], dict[str, str]]] = {
    "dalek": (
        [
            "....LL........",
            "...DDDD.......",
            "..DDDDDDEEEEb.",
            "..DDDDDD......",
            "..KKKKKK......",
            "..GGGGGG......",
            ".GGGGGGGG-==..",
            ".GGGGGGGG.....",
            ".GoGoGoGo.....",
            "GoGoGoGoGo....",
            "GGoGoGoGoG....",
            "GoGoGoGoGo....",
            "GGoGoGoGoG....",
            "KKKKKKKKKK....",
        ],
        {
            "L": "#ffcc33",
            "D": "#b9b9b9",
            "E": "#5a5a5a",
            "b": "#4fc3ff",
            "K": "#111111",
            "G": "#c9962b",
            "o": "#5a3e12",
            "-": "#8a8a8a",
            "=": "#d9d9d9",
            # only used by animation frames
            "l": "#5c4a1a",  # dome light off
            "R": "#ff4b2b",  # death ray
            "W": "#fff4c2",  # ray core / eye flash
        },
    ),
    "delta": (  # Starfleet insignia
        [
            "......G......",
            ".....GGG.....",
            ".....GGG.....",
            "....GGGGG....",
            "....GGKGG....",
            "...GGGKGGG...",
            "...GGKKKGG...",
            "..GGGGKGGGG..",
            "..GGGGKGGGG..",
            ".GGGGG.GGGGG.",
            ".GGGG...GGGG.",
            "GGGG.....GGGG",
            "GG.........GG",
        ],
        {"G": "#e8b84a", "K": "#000000"},
    ),
    "domo": (
        [
            ".BBBBBBBBBBB.",
            "BBBBBBBBBBBBB",
            "BBBKKBBBKKBBB",
            "BBBKKBBBKKBBB",
            "BBBBBBBBBBBBB",
            "BWWWWWWWWWWWB",
            "BRWRWRWRWRWRB",
            "BRRRRRRRRRRRB",
            "BWRWRWRWRWRWB",
            "BWWWWWWWWWWWB",
            "BBBBBBBBBBBBB",
            ".BBBB...BBBB.",
            ".BBB.....BBB.",
        ],
        {"B": "#8a5326", "K": "#000000", "W": "#ffffff", "R": "#d32f2f", "k": "#2a1608"},  # k: shut eyes (animation)
    ),
    "frenchie": (
        [
            "BB........BB",
            "BPB......BPB",
            "BPPB....BPPB",
            "BPPBFFFFBPPB",
            ".BFFFFFFFFB.",
            ".FFKFFFFKFF.",
            ".FFFFFFFFFF.",
            ".FFFMMMMFFF.",
            ".FFMMKKMMFF.",
            "..FMMMMMMF..",
            "..FFMTTMFF..",
            "...FFFFFF...",
        ],
        {"B": "#a07850", "P": "#f4a7b0", "F": "#d9b38c", "K": "#111111", "M": "#4a3a30", "T": "#e2677a"},
    ),
    "tardis": (
        [
            ".....L.....",
            "....BBB....",
            ".BBBBBBBBB.",
            ".BKKKKKKKB.",
            ".BBBBBBBBB.",
            ".BWWBBBWWB.",
            ".BWWBBBWWB.",
            ".BBBBBBBBB.",
            ".BbbBBBbbB.",
            ".BbbBBBbbB.",
            ".BBBBBBBBB.",
            ".BbbBBBbbB.",
            ".BbbBBBbbB.",
            "BBBBBBBBBBB",
        ],
        {"L": "#fff7b0", "B": "#1d4f9c", "K": "#0a0a0a", "W": "#e8f0ff", "b": "#163d7a"},
    ),
}


# --------------------------------------------------------------------------- animations
#
# Optional, per mascot. An Animation is a list of Frames; each frame is a full sprite
# (same palette as the mascot, "." transparent) shown for ``ms`` milliseconds, and may
# temporarily replace the header title. The sprite is restored when it ends. Frames
# may be wider than the base sprite (e.g. a death ray): the header canvas is sized to
# the widest frame. Add animations for a mascot = add an entry to ANIMATIONS.


@dataclass(frozen=True)
class Frame:
    rows: tuple[str, ...]
    ms: int
    title: str | None = None  # temporary header text; None = normal title


@dataclass(frozen=True)
class Animation:
    name: str
    frames: tuple[Frame, ...]
    repeat: tuple[int, int] = (1, 1)  # the frame list is played a random number of times
    weight: float = 1.0  # relative chance of being picked


def _rows(base: list[str], width: int, **replace: str) -> tuple[str, ...]:
    """Copy of ``base`` padded to ``width``; ``r<N>="..."`` replaces row N."""
    rows = list(base)
    for k, v in replace.items():
        rows[int(k[1:])] = v
    return tuple(r.ljust(width, ".") for r in rows)


def _shift(rows: tuple[str, ...], dx: int) -> tuple[str, ...]:
    return tuple(("." * dx + r)[: len(r)] for r in rows)


def _dalek_animations() -> tuple[Animation, ...]:
    base = MASCOTS["dalek"][0]
    w = 22  # 14 px Dalek + room for the death ray
    B = _rows(base, w)
    lights_off = _rows(base, w, r0="....ll........")
    eye_up = _rows(base, w, r1="...DDDDEEEEb..", r2="..DDDDDD......")
    eye_down = _rows(base, w, r2="..DDDDDD......", r3="..DDDDDDEEEEb.")
    eye_flash = _rows(base, w, r2="..DDDDDDEEEEW.")
    stalk_short = _rows(base, w, r2="..DDDDDDEEb...")
    stalk_front = _rows(base, w, r2="..DDDDDDb.....")
    gun = ".GGGGGGGG-=="

    def ray(beam: str, lights: bool = True, eye: str = "b") -> tuple[str, ...]:
        return _rows(base, w, r0="....LL........" if lights else "....ll........",
                     r2=f"..DDDDDDEEEE{eye}.", r6=gun + beam)

    # Each animation runs roughly 3-6 s.
    scan = Animation("scan", (
        Frame(eye_up, 380), Frame(B, 200), Frame(eye_down, 380), Frame(B, 200),
    ), repeat=(3, 5))
    look = Animation("look", (
        Frame(stalk_short, 200), Frame(stalk_front, 1200), Frame(stalk_short, 200), Frame(B, 600),
        Frame(eye_flash, 250), Frame(B, 150), Frame(eye_flash, 250), Frame(B, 400),
    ), repeat=(1, 2))
    shout = Animation("exterminate", tuple(
        f for word in ("EX-", "EX-TER-", "EX-TER-MI-", "EX-TER-MI-NATE!")
        for f in (Frame(B, 420, word), Frame(lights_off, 160, word))
    ) + tuple(
        f for _ in range(6) for f in (Frame(B, 200, "EX-TER-MI-NATE!"), Frame(lights_off, 200, "EX-TER-MI-NATE!"))
    ) + (Frame(B, 600, "EX-TER-MI-NATE!"),), weight=1.2)
    full, pulse = ray("RWWWWWWRRR", eye="W"), ray("RRWWWWWWRR", eye="W")
    fire = Animation("fire", tuple(
        f for _ in range(4) for f in (Frame(lights_off, 150), Frame(B, 150))
    ) + (
        Frame(ray("RR"), 90), Frame(ray("RRRRR"), 90), Frame(ray("RWWRRRRR"), 90),
    ) + tuple(
        f for _ in range(4) for f in (Frame(full, 120, "EXTERMINATE!"), Frame(pulse, 120, "EXTERMINATE!"))
    ) + (
        Frame(ray("R.R.R.R.R.", lights=False), 120, "EXTERMINATE!"),
        Frame(ray(".R...R...R", lights=False), 120),
        Frame(B, 500),
    ), repeat=(1, 2), weight=1.2)
    glide = Animation("glide", tuple(
        Frame(_shift(B, dx), 170) for dx in range(1, 7)
    ) + (
        Frame(_shift(eye_up, 6), 350), Frame(_shift(B, 6), 200),
        Frame(_shift(eye_down, 6), 350), Frame(_shift(B, 6), 300),
    ) + tuple(
        Frame(_shift(B, dx), 170) for dx in range(5, -1, -1)
    ) + (Frame(B, 300),))
    return (scan, look, shout, fire, glide)


def _domo_animations() -> tuple[Animation, ...]:
    base = MASCOTS["domo"][0]
    w = 17  # 13 px Domo + room to waddle / shake
    B = _rows(base, w)
    # eyes (rows 2-3)
    half = _rows(base, w, r2="BBBBBBBBBBBBB")
    shut = _rows(base, w, r2="BBBBBBBBBBBBB", r3="BBBKKBBBKKBBB".replace("KK", "kk"))
    left = _rows(base, w, r2="BBKKBBBKKBBBB", r3="BBKKBBBKKBBBB")
    right = _rows(base, w, r2="BBBBKKBBBKKBB", r3="BBBBKKBBBKKBB")
    # mouth (rows 4-10)
    closed = _rows(base, w, r5="BBBBBBBBBBBBB", r6="BWWWWWWWWWWWB", r7="BWRWRWRWRWRWB",
                   r8="BWWWWWWWWWWWB", r9="BBBBBBBBBBBBB")
    wide = _rows(base, w, r2="BBBBBBBBBBBBB", r3="BBBkkBBBkkBBB",  # eyes squeezed
                 r4="BWWWWWWWWWWWB", r5="BRWRWRWRWRWRB", r6="BRRRRRRRRRRRB", r7="BRRRRRRRRRRRB",
                 r8="BRRRRRRRRRRRB", r9="BWRWRWRWRWRWB", r10="BWWWWWWWWWWWB")
    # legs (rows 11-12)
    step_l = _rows(base, w, r12="........BBB..")
    step_r = _rows(base, w, r12=".BBB.........")

    # Each animation runs roughly 3-6 s.
    look = Animation("look", (
        Frame(B, 500), Frame(half, 90), Frame(shut, 120), Frame(half, 90), Frame(B, 600),
        Frame(left, 900), Frame(B, 300), Frame(right, 900), Frame(B, 400),
        Frame(half, 90), Frame(shut, 120), Frame(half, 90), Frame(B, 300),
    ))
    chomp = Animation("chomp", tuple(
        f for word in ("NOM", "NOM NOM", "NOM NOM NOM!")
        for f in (Frame(wide, 260, word), Frame(closed, 220, word), Frame(B, 200, word))
    ) + (Frame(closed, 500, "*chomp*"), Frame(B, 300)), repeat=(1, 2))
    cucu = Animation("cucuuu", tuple(
        Frame(wide if i % 2 == 0 else _shift(wide, 1), ms, word)
        for i, (word, ms) in enumerate((
            ("CU", 350), ("CUCU", 350), ("CUCUU", 250), ("CUCUUU", 250), ("CUCUUUU", 250),
            ("CUCUUUUU", 250), ("CUCUUUUUU", 250), ("CUCUUUUUUU!", 250), ("CUCUUUUUUUU!!", 250),
            ("CUCUUUUUUUUU!!!", 250), ("CUCUUUUUUUUU!!!", 250), ("CUCUUUUUUUUU!!!", 250),
        ))
    ) + (Frame(closed, 400, "CUCUUUUUUUUU!!!"), Frame(B, 500)), weight=1.3)
    waddle = Animation("waddle", tuple(
        Frame(_shift(step_l if dx % 2 else step_r, dx), 220) for dx in range(1, 5)
    ) + (
        Frame(_shift(B, 4), 300), Frame(_shift(left, 4), 600), Frame(_shift(B, 4), 300),
    ) + tuple(
        Frame(_shift(step_l if dx % 2 else step_r, dx), 220) for dx in range(3, -1, -1)
    ) + (Frame(B, 300),))
    return (look, chomp, cucu, waddle)


ANIMATIONS: dict[str, tuple[Animation, ...]] = {
    "dalek": _dalek_animations(),
    "domo": _domo_animations(),
}
