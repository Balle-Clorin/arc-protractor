"""
Arc Protractor Generator (Streamlit)

Effective length L is fixed; the pivot-to-spindle distance (P2S) is free.
Prints a true-scale arc protractor (PDF/SVG) plus a tracking-error plot.

Geometry (spindle at origin, pivot at distance d, stylus at radius r, L from pivot):
    sin(err + delta) = (L^2 + r^2 - d^2) / (2 L r)
    null radii satisfy   r1 * r2 = L^2 - d^2
                         sin(delta) = (r1 + r2) / (2 L)

License: PolyForm Noncommercial 1.0.0 (see LICENSE).
"""

from pathlib import Path
import io
import math

import numpy as np
import streamlit as st
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ------------------------------------------------------------------ constants
BASE_DIR = Path(__file__).resolve().parent

RI, RO = 60.325, 146.05            # IEC innermost / outermost groove radius, mm
DEFAULT_L = 233.15                 # SME V effective length, mm
DEFAULT_P2S = 215.35               # SME V pivot-to-spindle, mm
ARC_R0, ARC_R1 = 50.0, 150.0       # radius range drawn on the sheet, mm
SPINDLE_HOLE_MM = 7.0
PAPERS = {"A4 landscape": (297.0, 210.0), "US Letter landscape": (279.4, 215.9)}

PRESETS = {                        # published null points for IEC radii
    "Löfgren A (Baerwald)": (66.0, 120.9),
    "Löfgren B": (70.3, 116.6),
    "Stevenson": (60.325, 117.42),
    "Custom null points": None,
}

BASE_FONT = 13
BG = "#1e1e1e"
FG = "#e6e6e6"
GRID = "#3c3c3c"
ACCENT = "#4cc2df"
WARN = "#f2a561"

INK, MID, LIGHT = "#111111", "#7a7a7a", "#c6c6c6"
MM = 72.0 / 25.4                   # millimetres -> points


# ------------------------------------------------------------------ geometry
def geom_from_nulls(L, r1, r2):
    d2 = L * L - r1 * r2
    s = (r1 + r2) / (2.0 * L)
    if d2 <= 0 or s >= 1:
        return None
    return {"L": L, "d": math.sqrt(d2), "r1": r1, "r2": r2, "delta": math.asin(s)}


def track_err(g, r):
    """Tracking error in radians at radius r (scalar or array)."""
    a = (g["L"] ** 2 + np.asarray(r) ** 2 - g["d"] ** 2) / (2.0 * g["L"] * np.asarray(r))
    return np.arcsin(np.clip(a, -1.0, 1.0)) - g["delta"]


def err_stats(g):
    r = np.linspace(RI, RO, 801)
    e = np.degrees(np.abs(track_err(g, r)))
    i = int(np.argmax(e))
    return {"max": float(e[i]), "at": float(r[i]), "rms": float(np.sqrt(np.mean(e ** 2)))}


def best_for_d(L, d, weighted):
    """Fixed L and d: choose the offset angle that minimises RMS error (or RMS error / r)."""
    P = L * L - d * d
    if P <= 0:
        return None
    s_min, s_max = math.sqrt(P) / L, 0.95
    if s_min >= s_max:
        return None
    r = np.linspace(RI, RO, 301)

    def cost(s):
        g = {"L": L, "d": d, "delta": math.asin(s)}
        e = track_err(g, r)
        if weighted:
            e = e / r
        return float(np.mean(e ** 2))

    grid = np.linspace(s_min, s_max, 201)
    k = int(np.argmin([cost(s) for s in grid]))
    lo = grid[max(k - 1, 0)]
    hi = grid[min(k + 1, len(grid) - 1)]
    gr = 0.6180339887
    a, b = hi - gr * (hi - lo), lo + gr * (hi - lo)
    fa, fb = cost(a), cost(b)
    for _ in range(60):
        if fa < fb:
            hi, b, fb = b, a, fa
            a = hi - gr * (hi - lo)
            fa = cost(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + gr * (hi - lo)
            fb = cost(b)
    s = 0.5 * (lo + hi)
    bb = L * s
    q = math.sqrt(max(bb * bb - P, 0.0))
    return bb - q, bb + q


def compute(L, method, preset, n1, n2, d, crit, r1c):
    """Return (geometry dict, label) or (None, error message)."""
    if not 150.0 < L < 400.0:
        return None, "Effective length should be between 150 and 400 mm."
    if method == "align":
        if PRESETS[preset] is None:
            r1, r2 = n1, n2
        else:
            r1, r2 = PRESETS[preset]
        if not 0 < r1 < r2:
            return None, "The inner null must be smaller than the outer null."
        g = geom_from_nulls(L, r1, r2)
        if g is None:
            return None, "These null points do not work with this effective length."
        return g, preset
    if not 0 < d < L:
        return None, "Pivot-to-spindle must be positive and shorter than the effective length."
    P = L * L - d * d
    if crit in ("rms", "dist"):
        res = best_for_d(L, d, crit == "dist")
        if res is None:
            return None, "No alignment exists for this pivot-to-spindle distance."
        r1, r2 = res
        label = "Lowest distortion for this P2S" if crit == "dist" else "Lowest average error for this P2S"
    elif crit == "stev":
        r1, r2 = RI, P / RI
        label = "Inner null at 60.325 mm"
    else:
        if r1c <= 0:
            return None, "Enter an inner null radius."
        r1, r2 = r1c, P / r1c
        if r2 < r1:
            r1, r2 = r2, r1
        label = "Your inner null"
    g = geom_from_nulls(L, r1, r2)
    if g is None:
        return None, "No valid alignment for these values."
    g["d"] = d
    return g, label


# --------------------------------------------------------------- sheet scene
def text_box(p):
    w = len(p["s"]) * p["size"] * 0.6 + 1.0
    x0 = p["x"] - w / 2 if p["anchor"] == "middle" else (p["x"] - w if p["anchor"] == "end" else p["x"])
    return x0, p["y"] - p["size"] * 0.85, w, p["size"] * 1.15


def build_scene(g, label, paper, mirror):
    W, H = PAPERS[paper]
    M, FOOT = 10.0, 40.0
    mir = -1.0 if mirror else 1.0
    L, d = g["L"], g["d"]
    loc = []

    def tip(r):
        yp = (r * r - L * L + d * d) / (2 * d)
        return mir * math.sqrt(max(0.0, r * r - yp * yp)), yp

    def line(a, b, w, c, dash=None):
        loc.append({"t": "l", "a": a, "b": b, "w": w, "c": c, "dash": dash})

    def poly(pts, w, c):
        loc.append({"t": "p", "pts": pts, "w": w, "c": c, "dash": None})

    def circ(x, y, r, w, c, dash=None):
        loc.append({"t": "c", "x": x, "y": y, "r": r, "w": w, "c": c, "dash": dash})

    def text(x, y, s, size, anchor="middle", bold=False, c=INK, halo=False):
        loc.append({"t": "t", "x": x, "y": y, "s": s, "size": size, "anchor": anchor,
                    "bold": bold, "c": c, "halo": halo})

    def near_null(r, tol):
        return abs(r - g["r1"]) < tol or abs(r - g["r2"]) < tol

    def patch(r, title):
        px, py = tip(r)
        er = (px / r, py / r)
        et = (-er[1], er[0])

        def at(a, b):
            return (px + a * et[0] + b * er[0], py + a * et[1] + b * er[1])

        for k in range(-6, 7):                       # lines parallel to the cantilever
            b = 2.0 * k
            ctr, maj = k == 0, k % 5 == 0
            line(at(-20, b), at(20, b), 0.18 if ctr else (0.12 if maj else 0.07),
                 INK if ctr else (MID if maj else LIGHT))
        for k in range(-10, 11):                     # lines along the radius
            a = 2.0 * k
            ctr, maj = k == 0, k % 5 == 0
            line(at(a, -12), at(a, 12), 0.18 if ctr else (0.12 if maj else 0.07),
                 INK if ctr else (MID if maj else LIGHT))
        text(px, py + 25, title, 2.9, "middle", True)
        text(px, py + 28.6, "cantilever parallel to the long grid lines", 2.1, "middle", False, MID)

    patch(g["r1"], f"INNER NULL {g['r1']:.2f} mm")
    patch(g["r2"], f"OUTER NULL {g['r2']:.2f} mm")

    # pivot axis
    line((0, -28), (0, 60), 0.15, MID, (1.5, 1.2))
    poly([(-1.6, 55.5), (0, 60), (1.6, 55.5)], 0.15, MID)
    text(3.5, 58.2, f"TO PIVOT, {d:.2f} mm from spindle", 2.4, "start", False, MID)

    # spindle marks and centring rings
    line((-14, 0), (14, 0), 0.12, MID)
    line((0, -14), (0, 14), 0.12, MID)
    circ(0, 0, SPINDLE_HOLE_MM / 2, 0.2, INK, (0.9, 0.6))
    for rr in (5.5, 7.5, 9.5):
        circ(0, 0, rr, 0.08, LIGHT)
    circ(0, 0, 0.3, 0.2, INK)
    text(0, -18.5, f"SPINDLE: punch {SPINDLE_HOLE_MM:.0f} mm hole", 2.4)

    # arc (tip path)
    pts = [tip(ARC_R0 + (ARC_R1 - ARC_R0) * i / 240) for i in range(241)]
    poly(pts, 0.2, INK)

    # radius ticks across the arc (normal to the arc = along the arm)
    for r in range(int(ARC_R0), int(ARC_R1) + 1, 5):
        px, py = tip(r)
        nx, ny = px / L, (py - d) / L
        ten = r % 10 == 0
        ln = 3.2 if ten else 1.8
        line((px - nx * ln, py - ny * ln), (px + nx * ln, py + ny * ln), 0.18 if ten else 0.12, INK)
        if ten and not near_null(r, 11) and abs(r - RI) > 6 and abs(r - RO) > 6:
            text(px + nx * 6.8, py + ny * 6.8 - 0.8, str(r), 2.3, "middle", False, MID, True)
    for r, name in ((RI, "inner groove 60.3"), (RO, "outer groove 146.05")):
        px, py = tip(r)
        nx, ny = px / L, (py - d) / L
        line((px - nx * 6, py - ny * 6), (px + nx * 6, py + ny * 6), 0.25, INK)
        text(px + nx * 10.5, py + ny * 10.5 - 0.8, name, 2.3, "middle", True, INK, True)

    # centre the drawing above the footer
    xs, ys = [], []
    for p in loc:
        if p["t"] == "l":
            xs += [p["a"][0], p["b"][0]]; ys += [p["a"][1], p["b"][1]]
        elif p["t"] == "p":
            xs += [q[0] for q in p["pts"]]; ys += [q[1] for q in p["pts"]]
        elif p["t"] == "c":
            xs += [p["x"] - p["r"], p["x"] + p["r"]]; ys += [p["y"] - p["r"], p["y"] + p["r"]]
        else:
            x0, _, w, _ = text_box(p)
            xs += [x0, x0 + w]; ys += [p["y"] + p["size"] * 0.3, p["y"] - p["size"]]
    avail_w, avail_h = W - 2 * M, H - 2 * M - FOOT
    ox = M + (avail_w - (max(xs) - min(xs))) / 2 - min(xs)
    oy = M + (avail_h - (max(ys) - min(ys))) / 2 + max(ys)
    fits = (max(xs) - min(xs)) <= avail_w and (max(ys) - min(ys)) <= avail_h

    out = []
    for p in loc:
        q = dict(p)
        if p["t"] == "l":
            q["a"] = (ox + p["a"][0], oy - p["a"][1]); q["b"] = (ox + p["b"][0], oy - p["b"][1])
        elif p["t"] == "p":
            q["pts"] = [(ox + z[0], oy - z[1]) for z in p["pts"]]
        else:
            q["x"] = ox + p["x"]; q["y"] = oy - p["y"]
        out.append(q)

    top = H - M - FOOT
    s = err_stats(g)

    def ftxt(y, txt, size, bold=False, c=INK):
        out.append({"t": "t", "x": M, "y": top + y, "s": txt, "size": size, "anchor": "start",
                    "bold": bold, "c": c, "halo": False})

    ftxt(4, f"ARC PROTRACTOR  |  {label}", 3.8, True)
    ftxt(10.5, f"Effective length {L:.2f} mm     Pivot-to-spindle {d:.2f} mm     "
               f"Overhang {L - d:.2f} mm     Offset angle {math.degrees(g['delta']):.2f} deg", 2.9)
    ftxt(15.8, f"Null points {g['r1']:.2f} mm and {g['r2']:.2f} mm     "
               f"Peak tracking error {s['max']:.2f} deg at {s['at']:.1f} mm     RMS {s['rms']:.2f} deg", 2.9)
    ftxt(22.5, "1  Print at 100% (actual size, no fit-to-page) and check the 100 mm bar below.  "
               "2  Punch the spindle hole with a 7 mm punch.", 2.5, False, MID)
    ftxt(27, "3  Hole over the spindle, turn the sheet until the pivot axis points at the arm pivot.  "
             "4  The stylus must sit on the arc along its whole length.", 2.5, False, MID)
    bx, by = W - M - 100, top + FOOT - 3
    out.append({"t": "t", "x": bx - 2.5, "y": by + 1, "s": "100 mm", "size": 2.6, "anchor": "end",
                "bold": True, "c": INK, "halo": False})
    out.append({"t": "l", "a": (bx, by), "b": (bx + 100, by), "w": 0.2, "c": INK, "dash": None})
    for i in range(11):
        h = 2.6 if i % 5 == 0 else 1.5
        out.append({"t": "l", "a": (bx + 10 * i, by - h), "b": (bx + 10 * i, by + h),
                    "w": 0.2, "c": INK, "dash": None})
    return {"w": W, "h": H, "prims": out, "fits": fits}


def draw_sheet(sc, dpi=110):
    """Draw the scene with 1 data unit = 1 mm on a figure of exactly the paper size."""
    W, H = sc["w"], sc["h"]
    with plt.rc_context({"lines.scale_dashes": False, "pdf.fonttype": 42}):
        fig = plt.figure(figsize=(W / 25.4, H / 25.4), dpi=dpi, facecolor="white")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis("off")
        for p in sc["prims"]:
            dash = None if not p.get("dash") else (0, tuple(v * MM for v in p["dash"]))
            if p["t"] == "l":
                ax.plot([p["a"][0], p["b"][0]], [p["a"][1], p["b"][1]], color=p["c"],
                        lw=p["w"] * MM, solid_capstyle="butt",
                        **({"linestyle": dash} if dash else {}))
            elif p["t"] == "p":
                xs, ys = zip(*p["pts"])
                ax.plot(xs, ys, color=p["c"], lw=p["w"] * MM, solid_capstyle="butt", solid_joinstyle="round")
            elif p["t"] == "c":
                ax.add_patch(plt.Circle((p["x"], p["y"]), p["r"], fill=False, ec=p["c"], lw=p["w"] * MM,
                                        **({"linestyle": dash} if dash else {})))
            else:
                ha = {"middle": "center", "end": "right", "start": "left"}[p["anchor"]]
                kw = {}
                if p["halo"]:
                    kw["bbox"] = dict(facecolor="white", edgecolor="none", pad=0.6)
                ax.text(p["x"], p["y"], p["s"], fontsize=p["size"] * MM, ha=ha, va="baseline",
                        color=p["c"], fontweight="bold" if p["bold"] else "normal", **kw)
    return fig


@st.cache_data(show_spinner=False)
def render_sheet(L, r1, r2, d, label, paper, mirror):
    """Return (png, pdf, svg, fits) for the given geometry. Cached so reruns stay cheap."""
    g = geom_from_nulls(L, r1, r2)
    g["d"] = d
    sc = build_scene(g, label, paper, mirror)
    fig = draw_sheet(sc)
    out = {}
    for fmt in ("png", "pdf", "svg"):
        buf = io.BytesIO()
        fig.savefig(buf, format=fmt, dpi=110)      # no bbox_inches: keeps the exact paper size
        out[fmt] = buf.getvalue()
    plt.close(fig)
    return out["png"], out["pdf"], out["svg"], sc["fits"]


# -------------------------------------------------------------- error figure
def error_figure(g, label):
    r = np.linspace(48, 150, 800)
    e = np.degrees(track_err(g, r))
    ymax = max(1.0, math.ceil(float(np.max(np.abs(e))) * 2) / 2)
    fig, ax = plt.subplots(figsize=(11, 4.6), facecolor=BG)
    ax.set_facecolor(BG)
    ax.axvspan(RI, RO, color=ACCENT, alpha=0.08, lw=0)
    ax.axhline(0, color="#8a8a8a", lw=1.2)
    ax.plot(r, e, color=ACCENT, lw=2.4)
    for rv in (g["r1"], g["r2"]):
        ax.plot([rv], [0], "o", ms=9, mfc=BG, mec=WARN, mew=2.4, zorder=5)
        ax.annotate(f"{rv:.2f}", (rv, 0), xytext=(0, 12), textcoords="offset points",
                    ha="center", color=WARN, fontsize=BASE_FONT - 1)
    ax.set_xlim(48, 150)
    ax.set_ylim(-ymax, ymax)
    ax.set_xlabel("Radius from spindle (mm)", color=FG, fontsize=BASE_FONT)
    ax.set_ylabel("Tracking error (deg)", color=FG, fontsize=BASE_FONT)
    ax.tick_params(colors=FG, labelsize=BASE_FONT - 1)
    ax.grid(True, color=GRID, lw=0.8)
    for sp in ax.spines.values():
        sp.set_color(GRID)
    s = err_stats(g)
    ax.text(0.02, 0.03,
            f"{label}\nL = {g['L']:.2f} mm   P2S = {g['d']:.2f} mm   overhang = {g['L'] - g['d']:.2f} mm\n"
            f"offset = {math.degrees(g['delta']):.2f} deg   nulls {g['r1']:.2f} / {g['r2']:.2f} mm\n"
            f"peak {s['max']:.2f} deg at {s['at']:.1f} mm   RMS {s['rms']:.2f} deg",
            transform=ax.transAxes, fontsize=BASE_FONT - 2, color=FG, va="bottom", ha="left",
            family="monospace", bbox=dict(facecolor=BG, edgecolor=GRID, boxstyle="round,pad=0.5"))
    fig.tight_layout()
    return fig


# ------------------------------------------------ fixing a miss at the outer groove
R_MATCH, R_CHECK = 60.0, 146.0     # tip matched on the arc at 60 mm, miss read at 146 mm


def _theta(d, L, r):
    """Angle at the spindle between the pivot axis and the stylus."""
    return math.acos((d * d + r * r - L * L) / (2.0 * d * r))


def _alpha(d, L, r):
    """Angle at the arm pivot between the spindle and the stylus."""
    return math.acos((d * d + L * L - r * r) / (2.0 * d * L))


def miss_at_check(d, L, dp, Lp, r1=R_MATCH, r2=R_CHECK):
    """Real arm (pivot distance d, effective length L) on a protractor drawn for (dp, Lp).
    The protractor is turned so the tip is on the arc at r1. Returns the tip's distance from
    the arc at r2, measured along the arm. Positive = past the arc, away from the pivot."""
    phi = _theta(d, L, r1) - _theta(dp, Lp, r1)
    a = _theta(d, L, r2) - phi
    D = math.sqrt(dp * dp + r2 * r2 - 2.0 * dp * r2 * math.cos(a))
    return D - Lp


def _bisect(f, lo, hi):
    flo = f(lo)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


def rule_factors(dp, Lp, r1=R_MATCH, r2=R_CHECK):
    """First-order factors: P2S change = X / k_p2s, overhang change = X / k_ovh."""
    a1, a2 = _alpha(dp, Lp, r1), _alpha(dp, Lp, r2)
    k_p2s = math.sin(a2 - a1) / math.sin(a1)
    k_ovh = math.sin(a2) / math.sin(a1) - 1.0
    return k_p2s, k_ovh


def actual_p2s(dp, Lp, X, r1=R_MATCH):
    """Pivot-to-spindle of the real arm if its effective length equals Lp."""
    return _bisect(lambda d: miss_at_check(d, Lp, dp, Lp, r1) - X, dp - 10.0, dp + 10.0)


def actual_length(dp, Lp, X, r1=R_MATCH):
    """Effective length of the real arm if its pivot-to-spindle equals dp."""
    return _bisect(lambda L: miss_at_check(dp, L, dp, Lp, r1) - X, Lp - 10.0, Lp + 10.0)


def overhang_example_figure(dp, Lp, extra=2.0):
    """Worked example: P2S fixed, effective length `extra` mm longer than the protractor's (overhang too long).
    Drawn as seen by a person standing in front of the turntable: the arm pivot is at the top of the picture,
    'past the arc' is toward the viewer (down), and positive numbers are drawn below the reference line."""
    from matplotlib.patches import Rectangle, Polygon, FancyArrowPatch
    good, muted = "#7fd48a", "#8a8a8a"
    L_real = Lp + extra
    X = miss_at_check(dp, L_real, dp, Lp, R_MATCH, R_CHECK)              # tip set on the arc at 60 mm, read at 146 mm
    alt_at_60 = miss_at_check(dp, L_real, dp, Lp, R_CHECK, R_MATCH)      # tip set on the arc at 146 mm, read at 60 mm
    _, k_ovh = rule_factors(dp, Lp)
    rule = abs(X) / k_ovh
    r = np.linspace(50, 150, 400)
    g_60 = np.array([miss_at_check(dp, L_real, dp, Lp, R_MATCH, x) for x in r])
    g_146 = np.array([miss_at_check(dp, L_real, dp, Lp, R_CHECK, x) for x in r])
    side = "behind" if X < 0 else "past"

    fig = plt.figure(figsize=(14.5, 14.0), facecolor=BG)
    gs = fig.add_gridspec(3, 3, height_ratios=[1.0, 0.75, 0.80], width_ratios=[1, 1, 1.25],
                          left=0.055, right=0.985, top=0.885, bottom=0.135, hspace=0.34, wspace=0.12)
    fig.suptitle("Example: overhang too long. How to read the miss and fix it", color=FG,
                 fontsize=BASE_FONT + 5, fontweight="bold", x=0.055, ha="left", y=0.99)
    fig.text(0.055, 0.940, f"Fixed P2S = {dp:.2f} mm.  Protractor for L = {Lp:.2f} mm (overhang {Lp - dp:.2f} mm).  "
             f"Real arm: L = {L_real:.2f} mm (overhang {L_real - dp:.2f} mm), {extra:.1f} mm too long.",
             color=muted, fontsize=BASE_FONT - 1, ha="left")
    fig.text(0.055, 0.913, f"Protractor turned so the tip is on the arc at {R_MATCH:.0f} mm, then checked at {R_CHECK:.0f} mm.  "
             f"Rule of thumb: overhang change = {1 / k_ovh:.2f} x |X| = {rule:.1f} mm.",
             color=muted, fontsize=BASE_FONT - 1, ha="left")

    def style(ax):
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_color(GRID)
        ax.tick_params(colors=FG, labelsize=BASE_FONT - 2)

    def zoom(ax, title, tip_gap, ok):
        """Local view from the front: arm pivot at the top, 'past the arc' (+) is down toward the viewer."""
        style(ax)
        ax.set_xlim(-4.5, 4.5); ax.set_ylim(3.0, -4.6); ax.set_aspect("equal")        # y inverted: + is down
        ax.set_xticks([]); ax.set_yticks([])
        for yy in np.arange(-4, 3.1, 1.0):
            ax.axhline(yy, color=GRID, lw=0.7, zorder=0)
        for xx in np.arange(-4, 4.1, 1.0):
            ax.axvline(xx, color=GRID, lw=0.7, zorder=0)
        ax.axhline(0, color=FG, lw=2.4, zorder=2)
        yt = max(-4.3, min(2.6, tip_gap))
        ax.plot([0, 0], [yt, -4.6], color=ACCENT, lw=5, solid_capstyle="butt", zorder=3)   # cantilever runs up to the pivot
        ax.plot([0], [yt], "o", ms=10, mfc=BG, mec=good if ok else WARN, mew=2.6, zorder=5)
        ax.text(0.2, -4.35, "toward pivot", color=muted, fontsize=BASE_FONT - 3, ha="left", va="top")
        ax.text(-4.3, -0.18, "arc", color=FG, fontsize=BASE_FONT - 2, ha="left", va="bottom")
        ax.set_title(title, color=FG, fontsize=BASE_FONT, loc="left", pad=8)
        if not ok:
            ax.annotate("", xy=(1.9, yt), xytext=(1.9, 0), arrowprops=dict(arrowstyle="<->", color=WARN, lw=2))
            ax.text(2.25, yt / 2, f"X = {tip_gap:+.1f} mm\n{'behind' if tip_gap < 0 else 'past'} the arc",
                    color=WARN, fontsize=BASE_FONT - 1, va="center", ha="left")
        else:
            ax.text(2.0, -0.5, "on the arc", color=good, fontsize=BASE_FONT - 1, va="bottom", ha="left")
        ax.plot([-4.2, -3.2], [2.55, 2.55], color=FG, lw=2)
        ax.text(-3.7, 2.3, "1 mm", color=FG, fontsize=BASE_FONT - 3, ha="center", va="bottom")
        ax.text(4.3, 2.3, "toward you", color=muted, fontsize=BASE_FONT - 3, ha="right", va="bottom")

    zoom(fig.add_subplot(gs[0, 0]), "1. At 60 mm: tip on the arc", 0.0, True)
    zoom(fig.add_subplot(gs[0, 1]), "2. At 146 mm: read the miss", X, False)

    # headshell sketch, seen from the front: pivot at the top, stylus pointing down toward the viewer
    ax3 = fig.add_subplot(gs[0, 2]); style(ax3)
    ax3.set_xlim(-24, 56); ax3.set_ylim(-44, 26); ax3.set_aspect("equal"); ax3.set_xticks([]); ax3.set_yticks([])
    ax3.set_title("3. Slide the cartridge back, toward the pivot", color=FG, fontsize=BASE_FONT, loc="left", pad=8)
    ax3.add_patch(Polygon([[-6, 20], [6, 20], [8, -6], [-8, -6]], closed=True, fc="#2c2c2c", ec=muted, lw=1.5))   # arm tube
    ax3.add_patch(Rectangle((-12, -26), 24, 20, fc="#2c2c2c", ec=muted, lw=1.5))                                    # headshell
    for sx in (-5.5, 5.5):
        ax3.add_patch(Rectangle((sx - 1.3, -23), 2.6, 14, fc=BG, ec=muted, lw=1.2))                                 # slots
    shift = 4.0                                                    # drawn exaggerated
    ax3.add_patch(Rectangle((-8, -29 - shift), 16, 19, fc="none", ec=WARN, lw=1.8, ls="--"))                        # before: forward (down)
    ax3.add_patch(Polygon([[-1.1, -29 - shift], [1.1, -29 - shift], [0, -34 - shift]], closed=True,
                          fc="none", ec=WARN, lw=1.5, ls="--"))
    ax3.add_patch(Rectangle((-8, -29), 16, 19, fc="#2f4a52", ec=ACCENT, lw=2.2))                                    # after: moved up
    ax3.add_patch(Polygon([[-1.1, -29], [1.1, -29], [0, -34]], closed=True, fc=ACCENT, ec=ACCENT, lw=1))            # stylus at the front
    ax3.text(0, -19, "cartridge", color=FG, fontsize=BASE_FONT - 2, ha="center", va="center")
    ax3.add_patch(FancyArrowPatch((-16, -33), (-16, -25), arrowstyle="->", mutation_scale=18, color=ACCENT, lw=2.4))
    ax3.text(0, 23.5, "toward pivot", color=muted, fontsize=BASE_FONT - 3, ha="center", va="center")
    ax3.text(15, 20, f"Shorten overhang by {rule:.1f} mm", color=FG, fontsize=BASE_FONT - 1,
             fontweight="bold", ha="left", va="center")
    ax3.text(15, 14, f"= {1 / k_ovh:.2f} x |X| = {1 / k_ovh:.2f} x {abs(X):.1f} mm", color=muted,
             fontsize=BASE_FONT - 2, ha="left", va="center")
    ax3.plot([15, 19], [6, 6], color=WARN, lw=2, ls="--")
    ax3.text(21, 6, "before: too long", color=WARN, fontsize=BASE_FONT - 2, ha="left", va="center")
    ax3.plot([15, 19], [0, 0], color=ACCENT, lw=2.2)
    ax3.text(21, 0, "after: corrected", color=ACCENT, fontsize=BASE_FONT - 2, ha="left", va="center")
    ax3.text(15, -13, "Then set the tip on the arc\nat 60 mm again and\nre-check 146 mm.", color=FG,
             fontsize=BASE_FONT - 2, ha="left", va="center")
    ax3.text(15, -38, "(shift drawn exaggerated)", color=muted, fontsize=BASE_FONT - 3, ha="left", va="center")

    # plot: + (past the arc, toward the viewer) is drawn BELOW the reference line
    ax4 = fig.add_subplot(gs[2, :]); style(ax4)
    ax4.axvspan(RI, RO, color=ACCENT, alpha=0.07, lw=0)
    ax4.axhline(0, color=FG, lw=1.6)
    ax4.plot(r, np.full_like(r, extra), color=muted, lw=2.0, ls=(0, (4, 3)),
             label=f"protractor not turned: tip {extra:.1f} mm past the arc at every radius (= the overhang error)")
    ax4.plot(r, g_146, color=WARN, lw=2.0, ls=":",
             label=f"protractor turned so the tip is on the arc at {R_CHECK:.0f} mm: past the arc at 60 mm ({alt_at_60:+.1f} mm)")
    ax4.plot(r, g_60, color=WARN, lw=2.8,
             label=f"protractor turned so the tip is on the arc at {R_MATCH:.0f} mm: {side} the arc at 146 mm ({X:+.1f} mm)")
    ax4.plot(r, np.zeros_like(r), color=good, lw=2.8, ls=(0, (6, 3)),
             label="after the fix: tip on the arc at every radius")
    for rv, gv in ((R_MATCH, 0.0), (R_CHECK, 0.0), (R_CHECK, X), (R_MATCH, alt_at_60)):
        ax4.plot([rv], [gv], "o", ms=9, mfc=BG, mec=WARN, mew=2.2, zorder=5)
    ax4.set_xlim(50, 150); ax4.set_ylim(extra + 2.3, X - 1.4)                # inverted: + at the bottom
    ax4.text(52, extra + 1.6, "+ past the arc (toward you, away from the pivot)", color=muted, fontsize=BASE_FONT - 2, va="center")
    ax4.text(52, X - 0.95, "\u2212 behind the arc (toward the pivot)", color=muted, fontsize=BASE_FONT - 2, va="center")
    # true-shape view: the arc and the tip paths drawn in sheet coordinates (spindle at the bottom, pivot toward
    # the top), with the gap to the arc exaggerated so the curved shapes can be seen.
    axi = fig.add_subplot(gs[1, :]); style(axi)
    kx = 6.0
    pv = np.array([dp, 0.0])

    def tip_xy(r1, rr):
        phi = _theta(dp, L_real, r1) - _theta(dp, Lp, r1)
        a = _theta(dp, L_real, rr) - phi
        return np.array([rr * math.cos(a), rr * math.sin(a)])

    def exaggerated(r1):
        arc, tip = [], []
        for rr in r:
            v = tip_xy(r1, rr) - pv
            D = float(np.hypot(*v)); e = v / D
            arc.append(pv + Lp * e); tip.append(pv + (Lp + kx * (D - Lp)) * e)
        return np.array(arc), np.array(tip)

    arc60, tip60 = exaggerated(R_MATCH)
    arc146, tip146 = exaggerated(R_CHECK)
    axi.plot(arc60[:, 1], arc60[:, 0], color=FG, lw=2.0, label="the arc on the protractor")
    axi.plot(tip146[:, 1], tip146[:, 0], color=WARN, lw=1.8, ls=":", label="tip path, protractor set at 146 mm")
    axi.plot(tip60[:, 1], tip60[:, 0], color=WARN, lw=2.8, label="tip path, protractor set at 60 mm")
    for rv, col in ((R_MATCH, good), (R_CHECK, WARN)):
        k_ = int(np.argmin(abs(r - rv)))
        axi.plot([tip60[k_, 1]], [tip60[k_, 0]], "o", ms=8, mfc=BG, mec=col, mew=2)
    axi.set_title(f"True curve shapes seen on the sheet: the arc and the tip paths (radius ticks in mm; gap to the arc exaggerated x{kx:.0f})",
                  color=FG, fontsize=BASE_FONT - 1, loc="left", pad=8)
    axi.set_xlabel("Position along the record (mm)", color=FG, fontsize=BASE_FONT - 2)
    axi.set_ylabel("toward pivot  \u2192", color=FG, fontsize=BASE_FONT - 2)
    axi.legend(loc="upper left", frameon=True, facecolor=BG, edgecolor=GRID,
               labelcolor=FG, fontsize=BASE_FONT - 3)
    for rv in range(60, 150, 20):
        k_ = int(np.argmin(abs(r - rv)))
        axi.plot([arc60[k_, 1]], [arc60[k_, 0]], "|", color=FG, ms=10)
        axi.text(arc60[k_, 1], arc60[k_, 0] - 3.5, f"{rv}", color=muted, fontsize=BASE_FONT - 3, ha="center", va="top")
    axi.grid(True, color=GRID, lw=0.6)
    ax4.set_xlabel("Radius from spindle (mm)", color=FG, fontsize=BASE_FONT)
    ax4.set_ylabel("Tip minus arc, along the arm (mm)", color=FG, fontsize=BASE_FONT)
    ax4.grid(True, color=GRID, lw=0.8)
    leg = ax4.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=1, frameon=True, facecolor=BG,
                     edgecolor=GRID, fontsize=BASE_FONT - 3)
    for t in leg.get_texts():
        t.set_color(FG)
    return fig

# ------------------------------------------------------------------------ UI
st.set_page_config(page_title="Arc Protractor Generator", layout="wide")
st.title("Arc protractor generator")
st.write("Keep the arm's effective length fixed, set the pivot-to-spindle distance yourself, "
         "and print an arc protractor that matches your arm.")

with st.sidebar:
    st.header("Arm and alignment")
    L = st.number_input("Effective length L (mm)", min_value=150.0, max_value=400.0,
                        value=DEFAULT_L, step=0.05, format="%.2f")
    method_label = st.radio("How should the geometry be found?",
                            ["Choose an alignment", "Set pivot-to-spindle"])
    method = "align" if method_label == "Choose an alignment" else "p2s"

    preset, n1, n2, d_in, crit, r1c = list(PRESETS)[0], 66.0, 120.9, DEFAULT_P2S, "rms", 66.0
    if method == "align":
        preset = st.selectbox("Alignment", list(PRESETS))
        if PRESETS[preset] is None:
            n1 = st.number_input("Inner null (mm)", value=66.0, step=0.1, format="%.2f")
            n2 = st.number_input("Outer null (mm)", value=120.9, step=0.1, format="%.2f")
        st.caption("P2S follows from the null points and the effective length.")
    else:
        d_in = st.number_input("Pivot-to-spindle P2S (mm)", min_value=100.0, max_value=400.0,
                               value=DEFAULT_P2S, step=0.05, format="%.2f")
        crit_names = {
            "Lowest average error": "rms",
            "Lowest distortion (error weighted by 1/radius)": "dist",
            "Inner null at the innermost groove (Stevenson style)": "stev",
            "An inner null I choose": "cinner",
        }
        crit = crit_names[st.selectbox("Place the null points for", list(crit_names))]
        if crit == "cinner":
            r1c = st.number_input("Inner null (mm)", value=66.0, step=0.1, format="%.2f")
        st.caption("With L and P2S fixed the two null points are tied together.")

    st.header("Sheet")
    paper = st.selectbox("Paper", list(PAPERS))
    mirror = st.checkbox("Arm pivots on the left of the platter", value=False)

g, label = compute(L, method, preset, n1, n2, d_in, crit, r1c)
if g is None:
    st.error(label)
    st.stop()

stt = err_stats(g)
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Pivot-to-spindle", f"{g['d']:.2f} mm")
c2.metric("Overhang", f"{g['L'] - g['d']:.2f} mm")
c3.metric("Offset angle", f"{math.degrees(g['delta']):.2f}°")
c4.metric("Inner null", f"{g['r1']:.2f} mm")
c5.metric("Outer null", f"{g['r2']:.2f} mm")
c6.metric("Peak error", f"{stt['max']:.2f}°", help=f"At {stt['at']:.1f} mm, over 60.3 to 146.05 mm")
st.caption(f"{label}.  Inner null × outer null = L² − P2S² = {g['L'] ** 2 - g['d'] ** 2:.1f} mm².  "
           f"Average error (RMS) {stt['rms']:.2f}°.")

png, pdf, svg, fits = render_sheet(g["L"], g["r1"], g["r2"], g["d"], label, paper, mirror)
st.image(png)
if not fits:
    st.warning("The drawing does not fit on this paper at full size. Try the other paper size.")

base = f"arc-protractor_L{g['L']:.2f}_P2S{g['d']:.2f}"
b1, b2, _ = st.columns([1, 1, 4])
b1.download_button("Save PDF", pdf, file_name=base + ".pdf", mime="application/pdf")
b2.download_button("Save SVG", svg, file_name=base + ".svg", mime="image/svg+xml")
st.caption("Drawn at 1:1. Print at 100% (no fit-to-page) and check the 100 mm bar.")

fig = error_figure(g, label)
st.pyplot(fig)
plt.close(fig)

# ---------------------------------------------------------------- adjusting guide
st.header("Adjusting from a miss at the outer groove")
k_p2s, k_ovh = rule_factors(g["d"], g["L"])
st.markdown(
    "Turn the printed protractor until the stylus is **on the arc at 60 mm**, then read how far the stylus is "
    "from the arc at **146 mm**, along the arm. Call that distance **X**: positive when the stylus is past "
    "the arc (away from the pivot), negative when it is short of it (toward the pivot).\n\n"
    f"- **You can move the arm base** (pivot-to-spindle is free): your actual P2S is about "
    f"the protractor's P2S plus **{1 / k_p2s:.2f} × X**. "
    f"To match the protractor, move the base by {1 / k_p2s:.2f} × X **toward the spindle** when X is positive, "
    f"away from it when X is negative.\n"
    f"- **P2S is fixed** (the arm cannot move): slide the cartridge to change the overhang. "
    f"Increase the overhang by about **{1 / k_ovh:.2f} × X** when X is positive, and decrease it when X is "
    f"negative. Then set the tip on the arc at 60 mm again and re-check 146 mm.\n\n"
    "**Which way does the sign go?** It depends on where you set the tip on the arc. "
    "A too long overhang shows up as the tip *behind* the arc at the far end from where you set it, "
    "when you set it at 60 mm, and as the tip *past* the arc at 60 mm when you set it at 146 mm.\n\n"
    "| Tip set on the arc at | Tip at the other end | Overhang is | Fix |\n"
    "|---|---|---|---|\n"
    "| 60 mm | behind the arc at 146 mm (X negative) | too long | slide the cartridge back |\n"
    "| 60 mm | past the arc at 146 mm (X positive) | too short | slide the cartridge forward |\n"
    "| 146 mm | past the arc at 60 mm | too long | slide the cartridge back |\n"
    "| 146 mm | behind the arc at 60 mm | too short | slide the cartridge forward |\n\n"
    "**Why a too long overhang ends up behind the arc.** It sounds backwards, but it has been checked with a "
    "physical test. To get the tip onto the arc at 60 mm you have to turn the whole protractor, and turning it "
    "shifts the arc sideways by more than the overhang error itself. At 146 mm the arc has moved away from "
    "the tip by more than the tip was too far out, so the tip ends up *behind* the line even though the "
    "overhang is too long. If you do not turn the protractor at all, the too long overhang shows as the tip "
    "*past* the arc everywhere.\n\n"
    f"The factors above are for this arm (L = {g['L']:.2f} mm, P2S = {g['d']:.2f} mm). They hold for misses of a "
    f"few mm. If you match at a different radius, use the calculator below."
)

try:
    fig_ex = overhang_example_figure(g["d"], g["L"])
    st.pyplot(fig_ex)
    plt.close(fig_ex)
    st.caption("Example drawn for the protractor above, with the real effective length 2 mm longer (overhang 2 mm "
               "too long, P2S fixed). Turning the protractor only tilts the error line around the radius where "
               "you set the tip on the arc, so the same arm can show as past the arc at 60 mm (set at 146 mm) or "
               "behind the arc at 146 mm (set at 60 mm). The sign of the miss at the far end is always the "
               "opposite of the sign at the near end.")
except (ValueError, ZeroDivisionError):
    pass

with st.expander("Calculator: find the actual P2S or effective length"):
    cc1, cc2, cc3 = st.columns(3)
    dp_c = cc1.number_input("Protractor P2S (mm)", min_value=100.0, max_value=400.0,
                            value=round(g["d"], 2), step=0.05, format="%.2f")
    Lp_c = cc2.number_input("Protractor effective length (mm)", min_value=150.0, max_value=400.0,
                            value=round(g["L"], 2), step=0.05, format="%.2f")
    X_c = cc3.number_input("Miss X at 146 mm (mm, + past the arc)", min_value=-10.0, max_value=10.0,
                           value=2.0, step=0.1, format="%.2f")
    r1_c = st.number_input("Radius where the tip is matched (mm)", min_value=50.0, max_value=100.0,
                           value=R_MATCH, step=1.0, format="%.1f")
    unknown = st.radio(
        "Which value do you want to find?",
        ["Actual P2S (my effective length is known and fixed)",
         "Actual effective length (my P2S is known and fixed)"],
    )
    try:
        kp, ko = rule_factors(dp_c, Lp_c, r1_c)
        if unknown.startswith("Actual P2S"):
            d_act = actual_p2s(dp_c, Lp_c, X_c, r1_c)
            st.metric("Actual pivot-to-spindle", f"{d_act:.2f} mm",
                      delta=f"{d_act - dp_c:+.2f} mm vs protractor", delta_color="off")
            st.caption(f"Effective length taken as {Lp_c:.2f} mm. Rule of thumb: P2S change = {1 / kp:.2f} × X.")
        else:
            L_act = actual_length(dp_c, Lp_c, X_c, r1_c)
            st.metric("Actual effective length", f"{L_act:.2f} mm",
                      delta=f"{L_act - Lp_c:+.2f} mm vs protractor", delta_color="off")
            st.caption(f"Pivot-to-spindle taken as {dp_c:.2f} mm. To match the protractor, change the overhang by "
                       f"{Lp_c - L_act:+.2f} mm (rule of thumb: {1 / ko:.2f} × X).")
    except (ValueError, ZeroDivisionError):
        st.warning("These values do not give a valid geometry.")
