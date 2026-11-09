"""HiveMind top-bar art: brain in a jar + circuit board.

Single source of truth for the geometry. Emits either

  * mode="css"   -> one SVG whose moving parts carry classes/custom properties,
                    animated by topbar.css (inline-SVG delivery), or
  * mode="frame" -> a fully static SVG for one instant `t` of the loop,
                    rasterised into a sprite sheet (pre-rendered delivery).

Keeping both behind one module means the two delivery techniques are drawing
exactly the same picture, so a side-by-side comparison is about the technique
and nothing else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------- dimensions
JAR_W = 76          # jar occupies x 0..76
BOARD_W = 560       # board strip occupies x 76..636 in bar coordinates;
                    # wider than it usually shows, so it crops from the
                    # RIGHT instead of being letterboxed at wide layouts
BAR_W = JAR_W + BOARD_W
BAR_H = 88

FLUID_TOP = 20.0    # y where the meniscus sits
FLUID_BOT = 66.0    # y of the fluid floor

# ------------------------------------------------------------------- palette
INK_GLASS = "#d9c6ff"
METAL_HI = "#b9a7d6"
METAL_MID = "#6f5f92"
METAL_LO = "#372a55"
BOARD_BASE = "#1b1030"
BOARD_EDGE = "#4a2f78"
TRACE_DIM = "#5c3f91"
PAD_GOLD = "#e0b457"
SPARK = "#eadcff"


# ------------------------------------------------------------------- bubbles
@dataclass(frozen=True)
class Bubble:
    x: float        # resting x inside the jar
    r: float        # radius
    period: float   # seconds for one rise
    phase: float    # 0..1 offset into the rise
    drift: float    # horizontal sway amplitude


# Always present. Slow, sparse, small -- this is the "idle" soft bubbling.
IDLE_BUBBLES = [
    Bubble(28.0, 1.5, 4.6, 0.00, 1.6),
    Bubble(45.0, 1.1, 5.4, 0.35, 1.2),
    Bubble(36.0, 1.8, 6.1, 0.62, 2.0),
    Bubble(52.0, 1.0, 5.0, 0.18, 1.0),
    Bubble(22.0, 1.2, 6.8, 0.80, 1.4),
    Bubble(40.0, 0.9, 4.2, 0.47, 0.9),
]

# Added on top of the idle set when active: denser, fatter, faster.
ACTIVE_BUBBLES = [
    Bubble(25.0, 2.1, 2.2, 0.10, 2.2),
    Bubble(33.0, 1.4, 1.8, 0.55, 1.5),
    Bubble(43.0, 2.4, 2.6, 0.28, 2.4),
    Bubble(49.0, 1.6, 2.0, 0.72, 1.8),
    Bubble(30.0, 1.1, 1.6, 0.90, 1.1),
    Bubble(55.0, 1.9, 2.4, 0.40, 2.0),
    Bubble(19.0, 1.3, 2.1, 0.05, 1.3),
    Bubble(38.0, 2.6, 3.0, 0.66, 2.6),
]

ACTIVE_SPEEDUP = 2.1   # idle bubbles also hurry up when active


def _bubble_at(b: Bubble, t: float, speedup: float) -> tuple[float, float, float]:
    """(x, y, opacity) for bubble `b` at time `t`."""
    p = ((t / (b.period / speedup)) + b.phase) % 1.0
    y = FLUID_BOT - p * (FLUID_BOT - FLUID_TOP)
    x = b.x + b.drift * math.sin(p * math.pi * 3.0)
    if p < 0.08:
        o = p / 0.08
    elif p > 0.82:
        o = max(0.0, (1.0 - p) / 0.18)
    else:
        o = 1.0
    return x, y, o * 0.85


# ----------------------------------------------------------- circuit traces
# Paths run from a pad out on the board back toward the jar, so a travelling
# dash reads as charge flowing *into* the brain. pathLength="100" lets the
# dash maths be identical in CSS and in Python.
TRACES = [
    "M544 24 L500 24 L486 30 L268 30 L214 30 L196 44 L132 44 L120 52 L64 52",
    "M528 60 L470 60 L456 52 L284 52 L246 52 L232 38 L170 38 L158 48 L106 48 L96 56 L64 56",
    "M548 70 L420 70 L406 66 L258 66 L208 66 L190 58 L140 58 L128 52 L64 52",
    "M512 16 L460 16 L446 20 L276 20 L228 20 L212 28 L158 28 L146 44 L100 44 L88 50 L64 50",
    "M536 44 L478 44 L464 72 L240 72 L186 72 L172 62 L124 62 L112 56 L64 56",
]

# How often each trace fires while idle (seconds) -- deliberately out of sync
# and long, so idle reads as the occasional stray spark.
IDLE_TRACE_PERIOD = [7.3, 9.1, 6.4, 11.2, 8.6]
IDLE_TRACE_PHASE = [0.0, 0.31, 0.58, 0.14, 0.77]
ACTIVE_TRACE_PERIOD = [1.25, 1.55, 1.05, 1.75, 1.4]

DASH = 16.0          # visible dash length in pathLength units
VISIBLE_FRAC = 0.42  # fraction of an idle cycle the spark is actually running


# Cables from the board's connector header into the jar's base.
CABLES = [
    ("M64 54 C42 54 32 72 0 73", 3.4, "#7b58b8"),
    ("M64 58 C46 58 36 77 0 78", 3.0, "#5e4292"),
    ("M64 62 C50 62 40 82 0 83", 2.6, "#452f6e"),
]


def _esc(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


# ---------------------------------------------------------------------- defs
def defs() -> str:
    return f"""<defs>
  <linearGradient id="hm-glass" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#ffffff" stop-opacity=".30"/>
    <stop offset=".22" stop-color="#ffffff" stop-opacity=".05"/>
    <stop offset=".62" stop-color="#2a1545" stop-opacity=".18"/>
    <stop offset=".88" stop-color="#ffffff" stop-opacity=".16"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity=".04"/>
  </linearGradient>
  <linearGradient id="hm-fluid" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#7b3fd4" stop-opacity=".55"/>
    <stop offset=".55" stop-color="#53219b" stop-opacity=".72"/>
    <stop offset="1" stop-color="#2d0f5c" stop-opacity=".88"/>
  </linearGradient>
  <linearGradient id="hm-metal" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{METAL_HI}"/>
    <stop offset=".38" stop-color="{METAL_MID}"/>
    <stop offset=".62" stop-color="{METAL_LO}"/>
    <stop offset="1" stop-color="{METAL_MID}"/>
  </linearGradient>
  <linearGradient id="hm-brain" x1=".2" y1="0" x2=".8" y2="1">
    <stop offset="0" stop-color="#e9b9ff"/>
    <stop offset=".45" stop-color="#bd78f5"/>
    <stop offset="1" stop-color="#7a35c4"/>
  </linearGradient>
  <linearGradient id="hm-board" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#241539"/>
    <stop offset="1" stop-color="{BOARD_BASE}"/>
  </linearGradient>
  <radialGradient id="hm-halo" cx=".5" cy=".5" r=".5">
    <stop offset="0" stop-color="#c58bff" stop-opacity=".55"/>
    <stop offset="1" stop-color="#c58bff" stop-opacity="0"/>
  </radialGradient>
  <filter id="hm-soft" x="-60%" y="-60%" width="220%" height="220%">
    <feGaussianBlur stdDeviation="1.6"/>
  </filter>
  <filter id="hm-spark" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur stdDeviation="1.1" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <clipPath id="hm-fluid-clip">
    <path d="M15 {FLUID_TOP} h46 v40 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z"/>
  </clipPath>
</defs>"""


# --------------------------------------------------------------------- brain
# One hemisphere, mirrored, plus gyri and a stem that runs down to the base.
_HEMI = ("M38 23 C33 19.6 25.8 21 23.8 26 C18.6 27.2 16 31.4 18 36 "
         "C13.8 38.4 14 45 19 47 C20.2 52 26 54 30 51 C33 53.6 38 53 38 53 Z")
_GYRI = [
    "M33 24.5 C29 27 30 30.5 27 32",
    "M22.5 28.5 C25.5 31.5 23.5 34.5 20 35.5",
    "M19.5 39 C24 39.5 26.5 43 24 46",
    "M28 50.5 C29.5 46.5 33 45.5 35 47.5",
    "M31 33.5 C34 35 34 39 31 40.5",
]


def brain(mode: str, state: str, t: float) -> str:
    """The brain itself. Pulses (scale + halo) only while active."""
    if mode == "frame":
        if state == "active":
            ph = (t / 1.15) % 1.0
            k = 0.5 - 0.5 * math.cos(ph * 2 * math.pi)
            scale = 1.0 + 0.035 * k
            halo = 0.35 + 0.65 * k
        else:
            ph = (t / 5.2) % 1.0
            k = 0.5 - 0.5 * math.cos(ph * 2 * math.pi)
            scale = 1.0 + 0.008 * k
            halo = 0.18 + 0.12 * k
        wrap_open = (f'<g transform="translate(38 40) scale({_esc(scale * 0.88)}) '
                     f'translate(-38 -40)">')
        halo_attr = f' opacity="{_esc(halo)}"'
        cls = ""
    else:
        wrap_open = '<g class="hm-brain-pulse">'
        halo_attr = ""
        cls = ' class="hm-halo"'

    gyri = "".join(
        f'<path d="{d}" fill="none" stroke="#4d1f86" stroke-opacity=".55" '
        f'stroke-width="1.1" stroke-linecap="round"/>' for d in _GYRI
    )
    half = (f'<path d="{_HEMI}" fill="url(#hm-brain)"/>{gyri}')
    return (
        f'{wrap_open}'
        f'<ellipse{cls}{halo_attr} cx="38" cy="38" rx="24" ry="20" fill="url(#hm-halo)"/>'
        f'<path d="M36.2 51 h3.6 l.7 5.4 a2.3 2.3 0 0 1 -2.3 2.7 h-.4 a2.3 2.3 0 0 1 -2.3 -2.7 z" '
        f'fill="#8a49d6"/>'
        f'<g>{half}</g>'
        f'<g transform="translate(76 0) scale(-1 1)">{half}</g>'
        f'<path d="M38 22.4 C36.4 30 36.4 45 38 53" fill="none" stroke="#45187c" '
        f'stroke-opacity=".7" stroke-width="1.3" stroke-linecap="round"/>'
        f'</g>'
    )


def bubbles(mode: str, state: str, t: float) -> str:
    """Bubble column. Idle = sparse and slow; active = dense and quick."""
    out = []
    if mode == "frame":
        speed = ACTIVE_SPEEDUP if state == "active" else 1.0
        pool = IDLE_BUBBLES + (ACTIVE_BUBBLES if state == "active" else [])
        for b in pool:
            x, y, o = _bubble_at(b, t, speed)
            out.append(
                f'<circle cx="{_esc(x)}" cy="{_esc(y)}" r="{_esc(b.r)}" '
                f'fill="#e7d4ff" opacity="{_esc(o)}"/>'
            )
    else:
        for tag, pool in (("hm-b", IDLE_BUBBLES), ("hm-b hm-b-active", ACTIVE_BUBBLES)):
            for b in pool:
                out.append(
                    f'<circle class="{tag}" cx="{_esc(b.x)}" cy="{_esc(FLUID_BOT)}" '
                    f'r="{_esc(b.r)}" fill="#e7d4ff" '
                    f'style="--p:{_esc(b.period)}s;--d:-{_esc(b.period * b.phase)}s;'
                    f'--sway:{_esc(b.drift)}px"/>'
                )
    return f'<g clip-path="url(#hm-fluid-clip)">{"".join(out)}</g>'


def jar(mode: str, state: str, t: float) -> str:
    """Glass cylinder, fluid, collar, base plinth and the brain inside it."""
    return f"""<g class="hm-jar">
  <path d="M10 70 h56 a4 4 0 0 1 4 4 v8 a4 4 0 0 1 -4 4 h-56 a4 4 0 0 1 -4 -4 v-8 a4 4 0 0 1 4 -4 z"
        fill="url(#hm-metal)"/>
  <rect x="6" y="73" width="64" height="1.6" fill="#cdbbe8" opacity=".35"/>
  <rect x="66" y="75" width="10" height="3" rx="1.5" fill="{METAL_MID}"/>
  <rect x="66" y="79" width="10" height="3" rx="1.5" fill="{METAL_LO}"/>
  <path d="M15 {FLUID_TOP} h46 v40 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z" fill="url(#hm-fluid)"/>
  {brain(mode, state, t)}
  {bubbles(mode, state, t)}
  <ellipse cx="38" cy="{FLUID_TOP}" rx="23" ry="3.4" fill="#b98cf0" opacity=".42"/>
  <path d="M15 14 h46 v52 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z" fill="url(#hm-glass)"/>
  <path d="M15 14 h46 v52 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z" fill="none"
        stroke="{INK_GLASS}" stroke-opacity=".55" stroke-width="1.3"/>
  <path d="M20.5 20 v42" stroke="#ffffff" stroke-opacity=".30" stroke-width="2.4"
        stroke-linecap="round" fill="none"/>
  <path d="M55.5 24 v30" stroke="#ffffff" stroke-opacity=".14" stroke-width="1.6"
        stroke-linecap="round" fill="none"/>
  <rect x="11" y="6" width="54" height="9" rx="3.5" fill="url(#hm-metal)"/>
  <rect x="11" y="8.4" width="54" height="1.6" fill="#d7c9ef" opacity=".4"/>
  <circle cx="18" cy="10.5" r="1.5" fill="{METAL_LO}"/>
  <circle cx="38" cy="10.5" r="1.5" fill="{METAL_LO}"/>
  <circle cx="58" cy="10.5" r="1.5" fill="{METAL_LO}"/>
  <rect x="33" y="2" width="10" height="5" rx="2" fill="{METAL_MID}"/>
</g>"""


# --------------------------------------------------------------------- board
_CHIPS = [
    (178, 26, 34, 18),
    (236, 34, 26, 14),
    (124, 62, 30, 10),
    (330, 28, 40, 22),
    (430, 48, 34, 16),
    (392, 14, 26, 10),
]
_PADS = [(544, 24), (528, 60), (548, 70), (512, 16), (536, 44),
         (268, 30), (284, 52), (258, 66), (276, 20), (240, 72)]
_VIAS = [(150, 22), (206, 54), (170, 70), (222, 18), (118, 36), (292, 40),
         (134, 50), (252, 24), (198, 74), (108, 24), (318, 56), (372, 66),
         (412, 36), (452, 26), (492, 54), (302, 18), (474, 68), (356, 72),
         (502, 40), (418, 60)]


def _board_components() -> str:
    chips = "".join(
        f'<g><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2.5" fill="#120a20" '
        f'stroke="#56398c" stroke-width=".8"/>'
        f'<rect x="{x + 2}" y="{y + 2}" width="{w - 4}" height="2" rx="1" '
        f'fill="#6c4ba8" opacity=".5"/>'
        f'<circle cx="{x + 5}" cy="{y + h - 4}" r="1.2" fill="{PAD_GOLD}" opacity=".7"/></g>'
        for x, y, w, h in _CHIPS
    )
    pads = "".join(
        f'<circle cx="{x}" cy="{y}" r="3" fill="none" stroke="{PAD_GOLD}" stroke-width="1.4" '
        f'opacity=".8"/><circle cx="{x}" cy="{y}" r="1.1" fill="#120a20"/>'
        for x, y in _PADS
    )
    vias = "".join(
        f'<circle cx="{x}" cy="{y}" r="1.4" fill="none" stroke="{TRACE_DIM}" '
        f'stroke-width=".9" opacity=".75"/>' for x, y in _VIAS
    )
    header = (
        '<rect x="56" y="48" width="12" height="20" rx="2" fill="#150c26" '
        f'stroke="{METAL_MID}" stroke-width="1"/>'
        + "".join(f'<rect x="58" y="{y}" width="8" height="2" rx="1" fill="{PAD_GOLD}" '
                  f'opacity=".85"/>' for y in (51, 56, 61))
    )
    return (
        f'{chips}{pads}{vias}{header}'
        '<text x="546" y="71" text-anchor="end" font-family="ui-monospace,monospace" '
        'font-size="9" font-weight="700" letter-spacing="2.4" fill="#b78ff0" '
        'opacity=".92">HIVEMIND</text>'
        '<text x="546" y="24" text-anchor="end" font-family="ui-monospace,monospace" '
        'font-size="4.6" letter-spacing="1.1" fill="#6b4ea3" opacity=".75">REV A</text>'
    )


def _board_base() -> str:
    dim = "".join(
        f'<path d="{d}" fill="none" stroke="{TRACE_DIM}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>' for d in TRACES
    )
    return (
        f'<rect x="50" y="10" width="504" height="68" rx="6" fill="url(#hm-board)" '
        f'stroke="{BOARD_EDGE}" stroke-width="1.2"/>'
        f'<rect x="54" y="14" width="496" height="60" rx="4" fill="none" '
        f'stroke="{BOARD_EDGE}" stroke-width=".7" stroke-dasharray="3 4" opacity=".6"/>'
        f'{dim}'
    )


def _cables() -> str:
    out = []
    for d, w, col in CABLES:
        out.append(f'<path d="{d}" fill="none" stroke="#0f0820" stroke-width="{w + 1.6}" '
                   f'stroke-linecap="round"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{w}" '
                   f'stroke-linecap="round"/>')
        out.append(f'<path d="{d}" fill="none" stroke="#ffffff" stroke-opacity=".18" '
                   f'stroke-width="{w * 0.34:.2f}" stroke-linecap="round"/>')
    return "".join(out)


def _spark_progress(i: int, state: str, t: float) -> float | None:
    """Where along trace `i` the spark is at time `t`, or None if it is dark."""
    if state == "active":
        period = ACTIVE_TRACE_PERIOD[i]
        return ((t / period) + IDLE_TRACE_PHASE[i]) % 1.0
    period = IDLE_TRACE_PERIOD[i]
    cycle = ((t / period) + IDLE_TRACE_PHASE[i]) % 1.0
    if cycle > VISIBLE_FRAC:
        return None
    return cycle / VISIBLE_FRAC


def _spark_path(d: str, offset: float, width: float, opacity: float,
                dash: float = DASH) -> str:
    return (
        f'<path d="{d}" pathLength="100" fill="none" stroke="{SPARK}" '
        f'stroke-width="{_esc(width)}" stroke-linecap="round" stroke-linejoin="round" '
        f'stroke-dasharray="{_esc(dash)} 100" stroke-dashoffset="{_esc(offset)}" '
        f'opacity="{_esc(opacity)}"/>'
    )


def electricity(mode: str, state: str, t: float) -> str:
    """Charge travelling along the board traces, outer pads inward."""
    out = []
    for i, d in enumerate(TRACES):
        if mode == "frame":
            p = _spark_progress(i, state, t)
            if p is None:
                continue
            out.append(_spark_path(d, -(p * (100.0 + DASH)),
                                   1.7 if state == "active" else 1.4,
                                   1.0 if state == "active" else 0.75))
        else:
            period = IDLE_TRACE_PERIOD[i]
            out.append(
                f'<path class="hm-spark" d="{d}" pathLength="100" fill="none" '
                f'stroke="{SPARK}" stroke-linecap="round" stroke-linejoin="round" '
                f'stroke-dasharray="{_esc(DASH)} 100" '
                f'style="--p:{_esc(period)}s;--pa:{_esc(ACTIVE_TRACE_PERIOD[i])}s;'
                f'--d:{_esc(-period * IDLE_TRACE_PHASE[i])}s"/>'
            )
    return f'<g filter="url(#hm-spark)">{"".join(out)}</g>'


def cable_charge(mode: str, state: str, t: float) -> str:
    """Charge continuing down the cables and into the jar's base."""
    out = []
    for i, (d, w, _col) in enumerate(CABLES):
        if mode == "frame":
            period = (1.45 + 0.25 * i) if state == "active" else (8.2 + 1.7 * i)
            vis = 1.0 if state == "active" else 0.3
            cycle = ((t / period) + (0.2 * i + 0.45)) % 1.0
            if cycle > vis:
                continue
            p = cycle / vis
            out.append(_spark_path(d, -(p * (100.0 + 22.0)),
                                   w * 0.55, 0.95 if state == "active" else 0.7, 22.0))
        else:
            period = 8.2 + 1.7 * i
            out.append(
                f'<path class="hm-cable-spark" d="{d}" pathLength="100" fill="none" '
                f'stroke="{SPARK}" stroke-linecap="round" stroke-dasharray="22 100" '
                f'style="--p:{_esc(period)}s;--pa:{_esc(1.45 + 0.25 * i)}s;'
                f'--d:{_esc(-period * (0.2 * i + 0.45))}s;--w:{_esc(w * 0.55)}"/>'
            )
    return f'<g filter="url(#hm-spark)">{"".join(out)}</g>'


def board(mode: str, state: str, t: float) -> str:
    """Board strip: substrate and traces, charge, then components over the top
    (traces run *under* the chips, as they would on a real board)."""
    if mode == "frame":
        glow = (f'<rect x="50" y="10" width="504" height="68" rx="6" fill="url(#hm-halo)" '
                f'opacity="{".28" if state == "active" else ".07"}"/>')
    else:
        glow = ('<rect class="hm-board-glow" x="50" y="10" width="504" height="68" rx="6" '
                'fill="url(#hm-halo)"/>')
    return (
        f'<g class="hm-board">{_board_base()}{glow}'
        f'{electricity(mode, state, t)}{_board_components()}'
        f'{_cables()}{cable_charge(mode, state, t)}</g>'
    )


# ------------------------------------------------------------------ assembly
def svg_defs_block() -> str:
    """Hidden SVG holding the shared gradients/filters for the inline version."""
    return (f'<svg class="hm-defs" width="0" height="0" aria-hidden="true" focusable="false" '
            f'xmlns="http://www.w3.org/2000/svg">{defs()}</svg>')


def svg_jar_css() -> str:
    return (f'<svg class="hm-jar-svg" viewBox="0 0 {JAR_W} {BAR_H}" width="{JAR_W}" '
            f'height="{BAR_H}" aria-hidden="true" focusable="false" '
            f'xmlns="http://www.w3.org/2000/svg">{jar("css", "idle", 0.0)}</svg>')


def svg_board_css() -> str:
    return (f'<svg class="hm-board-svg" viewBox="0 0 {BOARD_W} {BAR_H}" '
            f'preserveAspectRatio="xMinYMid slice" aria-hidden="true" focusable="false" '
            f'xmlns="http://www.w3.org/2000/svg">{board("css", "idle", 0.0)}</svg>')


def svg_bar_frame(state: str, t: float) -> str:
    """One static frame of the whole bar segment, for rasterising."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BAR_W} {BAR_H}" '
        f'width="{BAR_W}" height="{BAR_H}">{defs()}'
        f'{jar("frame", state, t)}'
        f'<g transform="translate({JAR_W} 0)">{board("frame", state, t)}</g>'
        f'</svg>'
    )


# ----------------------------------------------------------------------- icon
# The app icon is a DIFFERENT DRAWING of the same object, not a scaled-down
# copy of the top bar. At 16 px the bar's 1.3-unit glass outline, 1.1-unit
# gyri, bubbles, rivets and blur filters are all sub-pixel and composite into
# a purple smudge. So: fewer parts, thicker strokes, flat high-contrast fills.
#
# Flat fills rather than the gradients in defs() also mean the icon SVG is
# self-contained, with no <defs> ids that could collide with the inline
# top-bar SVG when both are present in one document.

ICON_BOX = 64
ICON_PLATE_BG = "#1b0f30"   # top stop of the top bar's gradient
ICON_BODY_BG = "#12091f"    # app.css body background
ICON_RADIUS = 8             # 12.5% of ICON_BOX

ICON_FLUID = "#2a0f52"
ICON_BRAIN = "#c98bf5"
ICON_BRAIN_EDGE = "#2a0f52"
ICON_METAL = "#6f5f92"
ICON_GLASS = "#d9c6ff"

# "plate": rounded square, 48-unit content box -> 8 units of padding.
# "maskable": full bleed. The safe zone is the circle of radius 40% of the
# icon, and the largest square inside that circle is 0.8/sqrt(2) = 56.5% of
# the width; 55% leaves a little margin. Launchers may crop to any shape, and
# everything outside the square is plain background, so nothing can be cut.
_ICON_FIT = {
    "plate": 48.0 / BAR_H,       # 0.545
    "maskable": 0.55 * ICON_BOX / BAR_H,
}


def icon_jar() -> str:
    """The jar alone, redrawn to stay legible at favicon sizes."""
    hemi = (f'<path d="{_HEMI}" fill="{ICON_BRAIN}" stroke="{ICON_BRAIN_EDGE}" '
            f'stroke-width="1.6" stroke-linejoin="round"/>')
    return f"""<g>
  <path d="M10 70 h56 a4 4 0 0 1 4 4 v8 a4 4 0 0 1 -4 4 h-56 a4 4 0 0 1 -4 -4 v-8 a4 4 0 0 1 4 -4 z"
        fill="{ICON_METAL}"/>
  <path d="M15 {FLUID_TOP} h46 v40 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z" fill="{ICON_FLUID}"/>
  <g transform="translate(38 40) scale(.8) translate(-38 -40)">
    <path d="M36.2 51 h3.6 l.7 5.4 a2.3 2.3 0 0 1 -2.3 2.7 h-.4 a2.3 2.3 0 0 1 -2.3 -2.7 z"
          fill="{ICON_BRAIN}" stroke="{ICON_BRAIN_EDGE}" stroke-width="1.6" stroke-linejoin="round"/>
    {hemi}
    <g transform="translate(76 0) scale(-1 1)">{hemi}</g>
  </g>
  <path d="M15 14 h46 v52 a6 6 0 0 1 -6 6 h-34 a6 6 0 0 1 -6 -6 z" fill="none"
        stroke="{ICON_GLASS}" stroke-width="3" stroke-linejoin="round"/>
  <path d="M21 22 v38" stroke="#ffffff" stroke-opacity=".38" stroke-width="3"
        stroke-linecap="round" fill="none"/>
  <rect x="11" y="5" width="54" height="11" rx="4" fill="{ICON_METAL}"/>
</g>"""


def svg_icon(variant: str = "plate") -> str:
    """A standalone square icon SVG.

    variant "plate"    -> rounded card, for the favicon and the `any` PWA icons.
    variant "maskable" -> full bleed and opaque, for the `maskable` PWA icons
                          and apple-touch-icon (iOS composites alpha onto black,
                          so a rounded plate there would show a dark halo).
    """
    if variant not in _ICON_FIT:
        raise ValueError(f"unknown icon variant {variant!r}")
    scale = _ICON_FIT[variant]
    dx = (ICON_BOX - JAR_W * scale) / 2
    dy = (ICON_BOX - BAR_H * scale) / 2
    if variant == "plate":
        bg = (f'<rect width="{ICON_BOX}" height="{ICON_BOX}" rx="{ICON_RADIUS}" '
              f'fill="{ICON_PLATE_BG}"/>')
        dy = 8.0   # optically centred: the jar reads bottom-heavy
    else:
        bg = f'<rect width="{ICON_BOX}" height="{ICON_BOX}" fill="{ICON_PLATE_BG}"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON_BOX} {ICON_BOX}" '
        f'width="{ICON_BOX}" height="{ICON_BOX}" role="img" '
        f'aria-label="HiveMind: a brain in a jar">{bg}'
        f'<g transform="translate({_esc(dx)} {_esc(dy)}) scale({_esc(scale)})">{icon_jar()}</g>'
        f'</svg>'
    )
