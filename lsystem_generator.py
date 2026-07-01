#!/usr/bin/env python3
"""
L-system / Formal-grammar generator with a live GUI.

Two modes:
  * L-SYSTEM (parallel):   every symbol is rewritten simultaneously each
                           iteration -- the classic Lindenmayer behaviour.
  * PROBABILISTIC (serial): rules are applied to ONE symbol at a time. The
                           symbol to rewrite is chosen from a probability
                           distribution that spans the whole current string.
                           The distribution is normalised over the string's
                           length, so as the string grows the same curve is
                           re-sampled across the new (longer) string.

Turtle alphabet (matches the essay):
    F, G   move forward and draw a line
    f      move forward without drawing
    + turn left by angle      - turn right by angle
    [ push state (save)       ] pop state (restore)
    any other letter (e.g. X, Y) is a control symbol: no drawing, no movement.

Pure standard library (tkinter) -- just run:  python3 lsystem_generator.py
"""

import json
import math
import os
import random
import tkinter as tk
from tkinter import ttk, messagebox

# user saves are written here, next to the script, so they persist between runs
SAVES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "lsystem_saves.json")


def lerp_color(c0, c1, f):
    """Linear interpolation between two '#rrggbb' colours; f in [0, 1]."""
    f = min(1.0, max(0.0, f))
    r0, g0, b0 = int(c0[1:3], 16), int(c0[3:5], 16), int(c0[5:7], 16)
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r = round(r0 + (r1 - r0) * f)
    g = round(g0 + (g1 - g0) * f)
    b = round(b0 + (b1 - b0) * f)
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------- #
#  L-system string generation
# --------------------------------------------------------------------------- #
def expand_parallel(axiom, rules, iterations, max_len=2_000_000):
    """Classic parallel rewriting: every symbol replaced each iteration."""
    s = axiom
    for _ in range(iterations):
        out = []
        for ch in s:
            out.append(rules.get(ch, ch))
        s = "".join(out)
        if len(s) > max_len:
            break
    return s


def expand_probabilistic(axiom, rules, steps, dist_points, max_len=200_000,
                         seed=None):
    """
    Serial rewriting. Each 'step' rewrites exactly ONE symbol.

    The symbol is chosen with a probability proportional to a distribution
    curve sampled across the *current* string. Position i of a length-L string
    maps to t = i/(L-1) in [0, 1]; the curve value at t is its weight. Only
    positions whose symbol has a rule are eligible.
    """
    frames = expand_probabilistic_frames(axiom, rules, steps, dist_points,
                                         max_len=max_len, seed=seed)
    return frames[-1]


def expand_probabilistic_frames(axiom, rules, steps, dist_points,
                                max_len=200_000, seed=None, max_frames=120):
    """Like expand_probabilistic but returns a list of (string, depths)
    snapshots: the starting state plus one after (roughly) every rewrite,
    thinned to at most `max_frames` frames so the animation stays smooth."""
    rng = random.Random(seed)
    s = list(axiom)
    depths = [0] * len(s)        # how many rewrites deep each symbol was born
    every = max(1, steps // max_frames)
    frames = [("".join(s), list(depths))]
    for step in range(1, steps + 1):
        # eligible positions = those carrying a rewritable symbol
        eligible = [i for i, ch in enumerate(s) if ch in rules]
        if not eligible:
            break
        L = len(s)
        weights = []
        for i in eligible:
            t = i / (L - 1) if L > 1 else 0.0
            weights.append(max(0.0, sample_distribution(dist_points, t)))
        total = sum(weights)
        if total <= 0:
            # distribution gives no weight to any eligible spot -> pick uniformly
            pos = rng.choice(eligible)
        else:
            pos = rng.choices(eligible, weights=weights, k=1)[0]
        repl = rules[s[pos]]
        d = depths[pos] + 1                       # children are one generation deeper
        s[pos:pos + 1] = list(repl)
        depths[pos:pos + 1] = [d] * len(repl)
        if step % every == 0:
            frames.append(("".join(s), list(depths)))
        if len(s) > max_len:
            break
    if frames[-1][0] != "".join(s):               # always include final state
        frames.append(("".join(s), list(depths)))
    return frames


def sample_distribution(points, t):
    """Piecewise-linear interpolation of control points at parameter t in [0,1].

    `points` is a list of (t, value) sorted by t, with t spanning 0..1.
    """
    if not points:
        return 1.0
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return v0
            f = (t - t0) / (t1 - t0)
            return v0 + f * (v1 - v0)
    return points[-1][1]


# --------------------------------------------------------------------------- #
#  Turtle interpretation -> list of line segments
# --------------------------------------------------------------------------- #
def turtle_segments(s, angle_deg, depths=None, shrink=1.0):
    """Convert an L-system string into a list of ((x0,y0),(x1,y1)) segments.

    If `depths` (a per-symbol generation count) is given, a forward step at
    generation d is drawn with length `shrink ** d`, so symbols created in
    later rewrites draw shorter segments (shrink < 1 = they shrink).
    """
    angle = math.radians(angle_deg)
    x = y = 0.0
    heading = math.pi / 2          # start pointing up (essay uses rotate=90)
    stack = []
    segments = []
    for i, ch in enumerate(s):
        d = depths[i] if depths is not None else 0
        step = shrink ** d if depths is not None else 1.0
        if ch == "f":
            # lowercase f: move forward WITHOUT drawing (leaves a gap)
            x += step * math.cos(heading)
            y += step * math.sin(heading)
        elif ch == "+":
            heading += angle
        elif ch == "-":
            heading -= angle
        elif ch == "[":
            stack.append((x, y, heading))
        elif ch == "]":
            if stack:
                x, y, heading = stack.pop()
        elif ch.isupper():
            # any capital letter: move forward and draw a line
            nx = x + step * math.cos(heading)
            ny = y + step * math.sin(heading)
            segments.append(((x, y), (nx, ny), d))   # carry generation depth
            x, y = nx, ny
        # any other lowercase letter: control symbol, drives rules but no drawing
    return segments


# --------------------------------------------------------------------------- #
#  Preset examples (taken from / inspired by the essay)
# --------------------------------------------------------------------------- #
PRESETS = {
    "Koch curve":          {"axiom": "F++F++F",
                            "rules": [("F", "F-F++F-F")],
                            "angle": 60, "iters": 3},
    "Fractal plant":       {"axiom": "x",
                            "rules": [("x", "F[+x][-x]Fx"), ("F", "FF")],
                            "angle": 25, "iters": 5},
    "Bamboo":              {"axiom": "F",
                            "rules": [("F", "F[-x]x[+x]x"), ("x", "Fx")],
                            "angle": 50, "iters": 4},
    "Bush":                {"axiom": "F",
                            "rules": [("F", "FF-[--F+F+F]+[+F-F-F]")],
                            "angle": 25, "iters": 4},
    "Crop":                {"axiom": "F",
                            "rules": [("F", "F[+F]F[F-F]")],
                            "angle": 20, "iters": 5},
    "Branch":              {"axiom": "x",
                            "rules": [("x", "F-[[x]+x]+F[+Fx]-x"), ("F", "FF")],
                            "angle": 22.5, "iters": 5},
    "Sprite lightning":    {"axiom": "F",
                            "rules": [("F", "F[+F-F][-F+F]F")],
                            "angle": 20, "iters": 4, "rotation": 180},
    "Snowflake":           {"axiom": "[F][--F][++F][++++F]",
                            "rules": [("F", "F[-F][+F]FF")],
                            "angle": 45, "iters": 4},
}


# --------------------------------------------------------------------------- #
#  Distribution editor: a small canvas where points are dragged with the mouse
# --------------------------------------------------------------------------- #
class DistributionEditor(tk.Canvas):
    """A little graph of a probability distribution; drag points to edit it.

    * Left-drag a point to move it.
    * Double-click empty space to add a point.
    * Right-click a point to delete it (endpoints t=0 and t=1 are kept).
    Endpoints stay pinned at t=0 and t=1 but their height is editable.
    """

    PAD = 18
    HIT = 16   # pixel radius for grabbing a point (generous = easy to grab)
    EPS = 1e-3  # interior points stay strictly inside (0, 1)

    def __init__(self, master, on_change=None, **kw):
        super().__init__(master, bg="#1e1e24", highlightthickness=1,
                         highlightbackground="#444", **kw)
        self.on_change = on_change
        # control points in normalised coords: (t in [0,1], v in [0,1]).
        # Invariant: the list is kept sorted by t; index 0 and -1 are the
        # endpoints (pinned at t=0 and t=1), everything between is interior.
        self.points = [(0.0, 0.5), (0.5, 1.0), (1.0, 0.5)]
        self.drag_idx = None
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double)
        self.bind("<Button-2>", self._on_right)   # mac trackpad
        self.bind("<Button-3>", self._on_right)
        self.bind("<Configure>", lambda e: self.redraw())

    # --- coordinate helpers --------------------------------------------- #
    def _to_px(self, t, v):
        w = self.winfo_width()
        h = self.winfo_height()
        x = self.PAD + t * (w - 2 * self.PAD)
        y = (h - self.PAD) - v * (h - 2 * self.PAD)
        return x, y

    def _to_norm(self, x, y):
        w = self.winfo_width()
        h = self.winfo_height()
        t = (x - self.PAD) / max(1, (w - 2 * self.PAD))
        v = ((h - self.PAD) - y) / max(1, (h - 2 * self.PAD))
        return min(1, max(0, t)), min(1, max(0, v))

    # --- distribution accessor ------------------------------------------ #
    def get_points(self):
        return sorted(self.points, key=lambda p: p[0])

    # --- drawing -------------------------------------------------------- #
    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 5 or h < 5:
            return
        # grid
        for frac in (0.25, 0.5, 0.75):
            x, _ = self._to_px(frac, 0)
            self.create_line(x, self.PAD, x, h - self.PAD, fill="#333")
            _, y = self._to_px(0, frac)
            self.create_line(self.PAD, y, w - self.PAD, y, fill="#333")
        # axes
        self.create_rectangle(self.PAD, self.PAD, w - self.PAD, h - self.PAD,
                              outline="#555")
        pts = self.get_points()
        # filled area under the curve
        poly = [self._to_px(0, 0)]
        poly += [self._to_px(t, v) for t, v in pts]
        poly += [self._to_px(1, 0)]
        flat = [c for p in poly for c in p]
        self.create_polygon(*flat, fill="#2d4a6b", outline="")
        # curve
        line = [self._to_px(t, v) for t, v in pts]
        flat = [c for p in line for c in p]
        self.create_line(*flat, fill="#5aa9ff", width=2)
        # points
        for t, v in pts:
            x, y = self._to_px(t, v)
            self.create_oval(x - 5, y - 5, x + 5, y + 5,
                             fill="#ffcf5a", outline="#fff")
        self.create_text(self.PAD + 2, self.PAD - 9, anchor="w",
                         text="weight", fill="#888", font=("TkDefaultFont", 8))
        self.create_text(w - self.PAD, h - self.PAD + 9, anchor="e",
                         text="start --> end of string", fill="#888",
                         font=("TkDefaultFont", 8))

    # --- mouse handling ------------------------------------------------- #
    def _nearest(self, x, y):
        best, bi = self.HIT ** 2, None
        for i, (t, v) in enumerate(self.points):
            px, py = self._to_px(t, v)
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best:
                best, bi = d, i
        return bi

    def _in_plot(self, x, y):
        """Is the pixel inside the plotting rectangle (with a small margin)?"""
        w = self.winfo_width()
        h = self.winfo_height()
        m = self.PAD - 4
        return m <= x <= w - m and m <= y <= h - m

    def _on_press(self, e):
        self.points.sort(key=lambda p: p[0])
        self.drag_idx = self._nearest(e.x, e.y)

    def _on_drag(self, e):
        if self.drag_idx is None:
            return
        t, v = self._to_norm(e.x, e.y)
        n = len(self.points)
        # endpoints are pinned horizontally (identified by position, not value);
        # interior points stay strictly inside so they can never become an edge.
        if self.drag_idx == 0:
            t = 0.0
        elif self.drag_idx == n - 1:
            t = 1.0
        else:
            t = min(1.0 - self.EPS, max(self.EPS, t))
        moved = (t, v)
        self.points[self.drag_idx] = moved
        self.points.sort(key=lambda p: p[0])
        self.drag_idx = self.points.index(moved)   # follow the point after sort
        self.redraw()

    def _on_release(self, e):
        # drag an interior point off the graph to delete it (easy deletion)
        if self.drag_idx is not None:
            n = len(self.points)
            interior = 0 < self.drag_idx < n - 1
            if interior and n > 2 and not self._in_plot(e.x, e.y):
                del self.points[self.drag_idx]
                self.redraw()
        self.drag_idx = None
        if self.on_change:
            self.on_change()

    def _on_double(self, e):
        t, v = self._to_norm(e.x, e.y)
        self.points.append((t, v))
        self.redraw()
        if self.on_change:
            self.on_change()

    def _on_right(self, e):
        i = self._nearest(e.x, e.y)
        if i is not None:
            t, _ = self.points[i]
            if t not in (0.0, 1.0):       # keep endpoints
                del self.points[i]
                self.redraw()
                if self.on_change:
                    self.on_change()


# --------------------------------------------------------------------------- #
#  Main application
# --------------------------------------------------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("L-system / Grammar generator")
        self.geometry("1180x760")
        self.minsize(960, 620)

        self.rule_rows = []          # list of (frame, key_entry, val_entry)
        self.seed = 12345            # fixed seed -> reproducible probabilistic runs
        self.line_color = "#ffffff"  # colour of the drawn fractal
        self.bg_color = "#000000"    # canvas background
        self.grad_start = "#6b3f1d"  # gradient colour at the trunk (depth 0)
        self.grad_end = "#7ddf7d"    # gradient colour at the tips (max depth)
        self._animating = False      # animation playback state
        self._anim_job = None

        self._load_saves()
        self._build_ui()
        self._load_preset("Fractal plant")
        self.after(100, self.render)

    # ------------------------------------------------------------------- #
    #  UI construction
    # ------------------------------------------------------------------- #
    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        # ---- left control column (scrollable) ------------------------ #
        left_container = ttk.Frame(root, width=398)
        left_container.pack(side="left", fill="y")
        left_container.pack_propagate(False)
        left_canvas = tk.Canvas(left_container, highlightthickness=0,
                                width=380)
        left_scroll = ttk.Scrollbar(left_container, orient="vertical",
                                    command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side="right", fill="y")
        left_canvas.pack(side="left", fill="both", expand=True)
        self._left_canvas = left_canvas

        left = ttk.Frame(left_canvas)
        left_win = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>",
                  lambda e: left_canvas.configure(
                      scrollregion=left_canvas.bbox("all")))
        left_canvas.bind("<Configure>",
                         lambda e: left_canvas.itemconfig(left_win,
                                                          width=e.width))

        # preset dropdown (built-in, always present)
        prow = ttk.Frame(left)
        prow.pack(fill="x", pady=(0, 4))
        ttk.Label(prow, text="Preset:", width=7).pack(side="left")
        self.preset_var = tk.StringVar(value="Fractal plant")
        self.preset_cb = ttk.Combobox(prow, textvariable=self.preset_var,
                                      state="readonly",
                                      values=list(PRESETS.keys()))
        self.preset_cb.pack(side="left", fill="x", expand=True, padx=4)
        self.preset_cb.bind("<<ComboboxSelected>>",
                            lambda e: (self._load_preset(self.preset_var.get()),
                                       self.render()))

        # saves dropdown (user's, persisted to disk)
        srow0 = ttk.Frame(left)
        srow0.pack(fill="x", pady=(0, 6))
        ttk.Label(srow0, text="Saves:", width=7).pack(side="left")
        self.save_var = tk.StringVar(value="")
        self.save_cb = ttk.Combobox(srow0, textvariable=self.save_var,
                                    state="readonly",
                                    values=list(self.saves.keys()))
        self.save_cb.pack(side="left", fill="x", expand=True, padx=4)
        self.save_cb.bind("<<ComboboxSelected>>",
                          lambda e: self._load_save(self.save_var.get()))
        ttk.Button(srow0, text="Save", width=5,
                   command=self._save_current).pack(side="left")
        ttk.Button(srow0, text="Del", width=4,
                   command=self._delete_save).pack(side="left", padx=(2, 0))

        # mode
        mrow = ttk.LabelFrame(left, text="Mode", padding=6)
        mrow.pack(fill="x", pady=4)
        self.mode_var = tk.StringVar(value="lsystem")
        ttk.Radiobutton(mrow, text="L-system (parallel)", value="lsystem",
                        variable=self.mode_var,
                        command=self._on_mode_change).pack(anchor="w")
        ttk.Radiobutton(mrow, text="Probabilistic (one symbol at a time)",
                        value="prob", variable=self.mode_var,
                        command=self._on_mode_change).pack(anchor="w")

        # axiom
        arow = ttk.Frame(left)
        arow.pack(fill="x", pady=4)
        ttk.Label(arow, text="Axiom:", width=8).pack(side="left")
        self.axiom_var = tk.StringVar(value="X")
        ttk.Entry(arow, textvariable=self.axiom_var).pack(side="left",
                                                          fill="x", expand=True)

        # angle
        grow = ttk.Frame(left)
        grow.pack(fill="x", pady=4)
        ttk.Label(grow, text="Angle:", width=8).pack(side="left")
        self.angle_var = tk.DoubleVar(value=25.0)
        ttk.Spinbox(grow, from_=0, to=180, increment=0.5, width=8,
                    textvariable=self.angle_var).pack(side="left")
        ttk.Label(grow, text="degrees").pack(side="left", padx=4)

        # iterations
        irow = ttk.Frame(left)
        irow.pack(fill="x", pady=4)
        self.iter_label = ttk.Label(irow, text="Iterations:", width=8)
        self.iter_label.pack(side="left")
        self.iter_var = tk.IntVar(value=5)
        self.iter_scale = ttk.Scale(irow, from_=0, to=12, orient="horizontal",
                                    command=self._on_iter_slide)
        self.iter_scale.set(5)
        self.iter_scale.pack(side="left", fill="x", expand=True, padx=4)
        self.iter_val_lbl = ttk.Label(irow, text="5", width=5)
        self.iter_val_lbl.pack(side="left")

        # slider maximum (user-controllable upper bound)
        mxrow = ttk.Frame(left)
        mxrow.pack(fill="x")
        ttk.Label(mxrow, text="Slider max:", width=8).pack(side="left")
        self.maxiter_var = tk.IntVar(value=12)
        ttk.Spinbox(mxrow, from_=1, to=100000, increment=1, width=8,
                    textvariable=self.maxiter_var,
                    command=self._apply_maxiter).pack(side="left", padx=4)
        self.maxiter_var.trace_add("write", lambda *a: self._apply_maxiter())

        # rotation of the whole render
        rotrow = ttk.Frame(left)
        rotrow.pack(fill="x", pady=4)
        ttk.Label(rotrow, text="Rotate:", width=8).pack(side="left")
        self.rot_var = tk.DoubleVar(value=0.0)
        ttk.Scale(rotrow, from_=0, to=360, orient="horizontal",
                  variable=self.rot_var,
                  command=lambda v: self._live()).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(rotrow, text="0", width=3,
                   command=lambda: (self.rot_var.set(0), self.render())).pack(
            side="left")

        # colours
        crow = ttk.Frame(left)
        crow.pack(fill="x", pady=4)
        ttk.Label(crow, text="Colour:", width=8).pack(side="left")
        self.line_swatch = tk.Label(crow, text="  line  ", bg=self.line_color,
                                    relief="raised", cursor="hand2")
        self.line_swatch.pack(side="left", padx=2)
        self.line_swatch.bind("<Button-1>", lambda e: self._pick_color("line"))
        self.bg_swatch = tk.Label(crow, text="  bg  ", bg=self.bg_color,
                                  fg="#ddd", relief="raised", cursor="hand2")
        self.bg_swatch.pack(side="left", padx=2)
        self.bg_swatch.bind("<Button-1>", lambda e: self._pick_color("bg"))

        # rules
        rframe = ttk.LabelFrame(left, text="Rules  (symbol -> replacement)",
                                padding=6)
        rframe.pack(fill="x", pady=6)
        self.rules_container = ttk.Frame(rframe)
        self.rules_container.pack(fill="x")
        brow2 = ttk.Frame(rframe)
        brow2.pack(fill="x", pady=(6, 0))
        ttk.Button(brow2, text="+ Add rule",
                   command=lambda: self._add_rule_row("", "")).pack(side="left")
        self.guide_btn = ttk.Button(brow2, text="▸ Symbol guide",
                                    command=self._toggle_guide)
        self.guide_btn.pack(side="left", padx=6)

        # collapsible information panel describing each turtle symbol
        self._guide_open = False
        self.guide_panel = ttk.Frame(rframe)
        guide_text = (
            "A–Z   any capital letter: move forward and draw a line\n"
            "f         move forward WITHOUT drawing (leaves a gap)\n"
            "+         turn left by the angle\n"
            "−         turn right by the angle\n"
            "[         push: save current position & heading\n"
            "]         pop: restore last saved position & heading\n"
            "a–z   any other lowercase letter: control symbol,\n"
            "         no drawing or movement, only drives the rules"
        )
        ttk.Label(self.guide_panel, text=guide_text, justify="left",
                  foreground="#bbb", font=("TkFixedFont", 9)).pack(
            anchor="w", pady=4)

        # probabilistic-only panel
        self.prob_frame = ttk.LabelFrame(
            left, text="Probability distribution (drag the points)", padding=6)
        ttk.Label(self.prob_frame,
                  text="Double-click: add   Right-click or drag off graph: delete",
                  foreground="#888").pack(anchor="w")
        self.dist_editor = DistributionEditor(self.prob_frame, height=150,
                                              on_change=self.render)
        self.dist_editor.pack(fill="x", pady=4)

        # how quickly segments shrink as the string grows (per generation)
        srow = ttk.Frame(self.prob_frame)
        srow.pack(fill="x", pady=(2, 4))
        ttk.Label(srow, text="Shrink:").pack(side="left")
        self.shrink_var = tk.DoubleVar(value=0.85)
        # left end = strong shrink (0.4), right end = none (1.0)
        ttk.Scale(srow, from_=0.4, to=1.0, orient="horizontal",
                  variable=self.shrink_var,
                  command=lambda v: self._live()).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Label(srow, text="faster  <->  off",
                  foreground="#888").pack(side="left")

        # starting thickness of the trunk (width at depth 0)
        trow = ttk.Frame(self.prob_frame)
        trow.pack(fill="x", pady=(2, 4))
        ttk.Label(trow, text="Start width:").pack(side="left")
        self.start_var = tk.DoubleVar(value=6.0)
        ttk.Scale(trow, from_=1.0, to=20.0, orient="horizontal",
                  variable=self.start_var,
                  command=lambda v: self._live()).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Label(trow, text="thin <-> thick",
                  foreground="#888").pack(side="left")

        # how fast branches get thinner each generation (taper factor)
        trow2 = ttk.Frame(self.prob_frame)
        trow2.pack(fill="x", pady=(2, 4))
        ttk.Label(trow2, text="Thin rate:").pack(side="left")
        self.thin_var = tk.DoubleVar(value=0.8)
        # left = small factor = thins fast; right = ~1 = barely thins
        ttk.Scale(trow2, from_=0.5, to=1.0, orient="horizontal",
                  variable=self.thin_var,
                  command=lambda v: self._live()).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Label(trow2, text="faster <-> slower",
                  foreground="#888").pack(side="left")

        # colour gradient from trunk to tips
        grow2 = ttk.Frame(self.prob_frame)
        grow2.pack(fill="x", pady=(2, 4))
        self.gradient_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(grow2, text="Gradient", variable=self.gradient_var,
                        command=self.render).pack(side="left")
        self.grad_start_swatch = tk.Label(grow2, text=" trunk ",
                                          bg=self.grad_start, fg="#fff",
                                          relief="raised", cursor="hand2")
        self.grad_start_swatch.pack(side="left", padx=2)
        self.grad_start_swatch.bind(
            "<Button-1>", lambda e: self._pick_color("grad_start"))
        ttk.Label(grow2, text="->").pack(side="left")
        self.grad_end_swatch = tk.Label(grow2, text=" tips ",
                                        bg=self.grad_end, fg="#000",
                                        relief="raised", cursor="hand2")
        self.grad_end_swatch.pack(side="left", padx=2)
        self.grad_end_swatch.bind(
            "<Button-1>", lambda e: self._pick_color("grad_end"))

        rrow = ttk.Frame(self.prob_frame)
        rrow.pack(fill="x")
        ttk.Button(rrow, text="New random seed",
                   command=self._reseed).pack(side="left")

        # render + live toggle
        brow = ttk.Frame(left)
        brow.pack(fill="x", pady=8)
        ttk.Button(brow, text="Render", command=self.render).pack(
            side="left", fill="x", expand=True)
        self.anim_btn = ttk.Button(brow, text="Animate",
                                   command=self.toggle_animate)
        self.anim_btn.pack(side="left", fill="x", expand=True, padx=4)
        self.live_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(brow, text="Live", variable=self.live_var).pack(
            side="left", padx=6)

        self.status = ttk.Label(left, text="", foreground="#888")
        self.status.pack(anchor="w", pady=(4, 0))

        # live re-render on edits
        for var in (self.axiom_var, self.angle_var):
            var.trace_add("write", lambda *a: self._live())

        # ---- right canvas -------------------------------------------- #
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.canvas = tk.Canvas(right, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._live())

        self._on_mode_change()

        # mouse-wheel scrolling for the sidebar (cross-platform)
        def _wheel(e):
            if getattr(e, "num", None) == 4 or getattr(e, "delta", 0) > 0:
                self._left_canvas.yview_scroll(-1, "units")
            elif getattr(e, "num", None) == 5 or getattr(e, "delta", 0) < 0:
                self._left_canvas.yview_scroll(1, "units")
        self.bind_all("<MouseWheel>", _wheel)   # macOS / Windows
        self.bind_all("<Button-4>", _wheel)     # Linux scroll up
        self.bind_all("<Button-5>", _wheel)     # Linux scroll down

    # ------------------------------------------------------------------- #
    #  Rule row management
    # ------------------------------------------------------------------- #
    def _add_rule_row(self, key, val):
        frame = ttk.Frame(self.rules_container)
        frame.pack(fill="x", pady=2)
        kv = tk.StringVar(value=key)
        vv = tk.StringVar(value=val)
        ke = ttk.Entry(frame, textvariable=kv, width=3)
        ke.pack(side="left")
        ttk.Label(frame, text="->").pack(side="left", padx=2)
        ve = ttk.Entry(frame, textvariable=vv)
        ve.pack(side="left", fill="x", expand=True)
        btn = ttk.Button(frame, text="x", width=2,
                         command=lambda: self._remove_rule_row(frame))
        btn.pack(side="left", padx=2)
        kv.trace_add("write", lambda *a: self._live())
        vv.trace_add("write", lambda *a: self._live())
        self.rule_rows.append((frame, kv, vv))

    def _remove_rule_row(self, frame):
        self.rule_rows = [r for r in self.rule_rows if r[0] is not frame]
        frame.destroy()
        self._live()

    def _clear_rules(self):
        for frame, _, _ in self.rule_rows:
            frame.destroy()
        self.rule_rows = []

    def _collect_rules(self):
        rules = {}
        for _, kv, vv in self.rule_rows:
            k = kv.get().strip()
            v = vv.get()
            if len(k) == 1:
                rules[k] = v
        return rules

    # ------------------------------------------------------------------- #
    #  Preset / mode / iteration handlers
    # ------------------------------------------------------------------- #
    def _load_preset(self, name):
        p = PRESETS[name]
        # presets are L-system mode, drawn as white lines on a black background
        self.mode_var.set("lsystem")
        self._on_mode_change()
        self.axiom_var.set(p["axiom"])
        self.angle_var.set(p["angle"])
        self._clear_rules()
        for k, v in p["rules"]:
            self._add_rule_row(k, v)
        self._set_iter(p["iters"])
        self.rot_var.set(p.get("rotation", 0.0))   # most presets upright; lightning flips
        self.line_color = "#ffffff"
        self.bg_color = "#000000"
        self.line_swatch.config(bg=self.line_color)
        self.bg_swatch.config(bg=self.bg_color)
        self.canvas.config(bg=self.bg_color)

    # ------------------------------------------------------------------- #
    #  Persistent saves (full state, written to disk)
    # ------------------------------------------------------------------- #
    def _load_saves(self):
        try:
            with open(SAVES_FILE) as f:
                self.saves = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.saves = {}

    def _write_saves(self):
        try:
            with open(SAVES_FILE, "w") as f:
                json.dump(self.saves, f, indent=2)
        except OSError as e:
            messagebox.showerror("Save failed",
                                 f"Could not write saves file:\n{e}")

    def _gather_state(self):
        """Capture every parameter into a JSON-serialisable dict."""
        try:
            angle = float(self.angle_var.get())
        except (tk.TclError, ValueError):
            angle = 25.0
        return {
            "mode": self.mode_var.get(),
            "axiom": self.axiom_var.get(),
            "angle": angle,
            "iters": self.iter_var.get(),
            "max_iter": self.maxiter_var.get(),
            "rotation": self.rot_var.get(),
            "rules": [(kv.get().strip(), vv.get())
                      for _, kv, vv in self.rule_rows if kv.get().strip()],
            "line_color": self.line_color,
            "bg_color": self.bg_color,
            "grad_start": self.grad_start,
            "grad_end": self.grad_end,
            "gradient": self.gradient_var.get(),
            "shrink": self.shrink_var.get(),
            "start_width": self.start_var.get(),
            "thin_rate": self.thin_var.get(),
            "seed": self.seed,
            "dist_points": [list(p) for p in self.dist_editor.get_points()],
        }

    def _apply_state(self, st):
        """Restore every parameter from a saved state dict."""
        self.mode_var.set(st.get("mode", "lsystem"))
        self._on_mode_change()             # resets iter/maxiter -> override below

        self.axiom_var.set(st.get("axiom", "X"))
        self.angle_var.set(st.get("angle", 25.0))
        self.maxiter_var.set(st.get("max_iter", 12))
        self._apply_maxiter()
        self._set_iter(st.get("iters", 5))
        self.rot_var.set(st.get("rotation", 0.0))

        # rules
        self._clear_rules()
        for k, v in st.get("rules", []):
            self._add_rule_row(k, v)

        # colours
        self.line_color = st.get("line_color", self.line_color)
        self.bg_color = st.get("bg_color", self.bg_color)
        self.grad_start = st.get("grad_start", self.grad_start)
        self.grad_end = st.get("grad_end", self.grad_end)
        self.line_swatch.config(bg=self.line_color)
        self.bg_swatch.config(bg=self.bg_color)
        self.canvas.config(bg=self.bg_color)
        self.grad_start_swatch.config(bg=self.grad_start)
        self.grad_end_swatch.config(bg=self.grad_end)

        # probabilistic styling
        self.gradient_var.set(st.get("gradient", True))
        self.shrink_var.set(st.get("shrink", 0.85))
        self.start_var.set(st.get("start_width", 6.0))
        self.thin_var.set(st.get("thin_rate", 0.8))
        self.seed = st.get("seed", self.seed)

        # distribution curve
        pts = st.get("dist_points")
        if pts:
            self.dist_editor.points = [tuple(p) for p in pts]
            self.dist_editor.redraw()

        self.render()

    def _save_current(self):
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Save", "Name for this save:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.saves and not messagebox.askyesno(
                "Overwrite?", f"A save named '{name}' already exists.\n"
                              "Overwrite it?"):
            return
        self.saves[name] = self._gather_state()
        self._write_saves()
        self.save_cb.config(values=list(self.saves.keys()))
        self.save_var.set(name)
        self.status.config(text=f"saved '{name}'")

    def _load_save(self, name):
        if name in self.saves:
            self._apply_state(self.saves[name])
            self.status.config(text=f"loaded save '{name}'")

    def _delete_save(self):
        name = self.save_var.get()
        if not name or name not in self.saves:
            return
        if not messagebox.askyesno("Delete", f"Delete save '{name}'?"):
            return
        del self.saves[name]
        self._write_saves()
        self.save_cb.config(values=list(self.saves.keys()))
        self.save_var.set("")
        self.status.config(text=f"deleted '{name}'")

    def _on_mode_change(self):
        if self.mode_var.get() == "prob":
            self.prob_frame.pack(fill="x", pady=6)
            self.iter_label.config(text="Rewrites:")
            self.maxiter_var.set(600)        # -> _apply_maxiter sets the scale
            if self.iter_var.get() < 30:
                self._set_iter(120)
        else:
            self.prob_frame.pack_forget()
            self.iter_label.config(text="Iterations:")
            self.maxiter_var.set(10)         # default L-system slider max
            self._set_iter(5)                # always reset iterations to 5
        self.render()

    def _set_iter(self, n):
        self.iter_var.set(n)
        self.iter_scale.set(n)
        self.iter_val_lbl.config(text=str(n))

    def _on_iter_slide(self, _val):
        if not hasattr(self, "iter_val_lbl"):
            return                      # still building the UI
        n = int(float(_val))
        self.iter_var.set(n)
        self.iter_val_lbl.config(text=str(n))
        self._live()

    def _reseed(self):
        self.seed = random.randint(0, 1_000_000)
        self.render()

    def _apply_maxiter(self):
        try:
            mx = int(self.maxiter_var.get())
        except (tk.TclError, ValueError):
            return
        mx = max(1, mx)
        self.iter_scale.config(to=mx)
        if self.iter_var.get() > mx:          # clamp current value into range
            self._set_iter(mx)
        self._live()

    def _toggle_guide(self):
        self._guide_open = not self._guide_open
        if self._guide_open:
            self.guide_panel.pack(fill="x", pady=(4, 0))
            self.guide_btn.config(text="▾ Symbol guide")
        else:
            self.guide_panel.pack_forget()
            self.guide_btn.config(text="▸ Symbol guide")

    def _pick_color(self, which):
        from tkinter import colorchooser
        current = {"line": self.line_color, "bg": self.bg_color,
                   "grad_start": self.grad_start,
                   "grad_end": self.grad_end}[which]
        rgb, hexv = colorchooser.askcolor(color=current,
                                          title="Choose colour")
        if not hexv:
            return
        if which == "line":
            self.line_color = hexv
            self.line_swatch.config(bg=hexv)
        elif which == "bg":
            self.bg_color = hexv
            self.bg_swatch.config(bg=hexv)
            self.canvas.config(bg=hexv)
        elif which == "grad_start":
            self.grad_start = hexv
            self.grad_start_swatch.config(bg=hexv)
        elif which == "grad_end":
            self.grad_end = hexv
            self.grad_end_swatch.config(bg=hexv)
        self.render()

    def _live(self):
        if self._animating:
            return
        if getattr(self, "live_var", None) and self.live_var.get():
            # debounce a touch so typing doesn't render every keystroke
            if getattr(self, "_live_job", None):
                self.after_cancel(self._live_job)
            self._live_job = self.after(120, self.render)

    # ------------------------------------------------------------------- #
    #  Render
    # ------------------------------------------------------------------- #
    def render(self):
        axiom = self.axiom_var.get()
        rules = self._collect_rules()
        try:
            angle = float(self.angle_var.get())
        except (tk.TclError, ValueError):
            angle = 25.0
        n = self.iter_var.get()

        if not axiom:
            self.status.config(text="empty axiom")
            return

        if self.mode_var.get() == "prob":
            s, depths = expand_probabilistic(axiom, rules, n,
                                             self.dist_editor.get_points(),
                                             seed=self.seed)
            segments = turtle_segments(s, angle, depths=depths,
                                       shrink=self.shrink_var.get())
        else:
            s = expand_parallel(axiom, rules, n)
            segments = turtle_segments(s, angle)
        self._draw(segments)
        self.status.config(
            text=f"string length: {len(s):,}    segments: {len(segments):,}")

    def _draw(self, segments):
        cv = self.canvas
        cv.delete("all")
        w = cv.winfo_width()
        h = cv.winfo_height()
        if w < 5 or h < 5:
            return
        if not segments:
            cv.create_text(w / 2, h / 2, text="(no drawn lines)",
                           fill="#666")
            return

        # apply the user rotation to every point before fitting, so the
        # auto-scale always frames the rotated drawing correctly
        rot = math.radians(self.rot_var.get())
        if rot:
            ca, sa = math.cos(rot), math.sin(rot)
            segments = [((x0 * ca - y0 * sa, x0 * sa + y0 * ca),
                         (x1 * ca - y1 * sa, x1 * sa + y1 * ca), d)
                        for (x0, y0), (x1, y1), d in segments]

        # bounding box of all points (third tuple item is the depth, not a point)
        xs = [c for (p0, p1, _) in segments for c in (p0[0], p1[0])]
        ys = [c for (p0, p1, _) in segments for c in (p0[1], p1[1])]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        bw = maxx - minx or 1.0
        bh = maxy - miny or 1.0

        margin = 24
        scale = min((w - 2 * margin) / bw, (h - 2 * margin) / bh)
        # centre it
        offx = (w - bw * scale) / 2 - minx * scale
        offy = (h - bh * scale) / 2 - miny * scale

        def tx(x, y):
            # flip y so the drawing grows upward on screen
            return x * scale + offx, h - (y * scale + offy)

        # depth-based styling (probabilistic mode only)
        prob = self.mode_var.get() == "prob"
        maxd = max((d for _, _, d in segments), default=0) or 1
        start_w = self.start_var.get() if prob else 1.0
        thin = self.thin_var.get() if prob else 1.0
        gradient = prob and self.gradient_var.get()

        for (x0, y0), (x1, y1), d in segments:
            ax, ay = tx(x0, y0)
            bx, by = tx(x1, y1)
            frac = d / maxd                       # 0 at trunk, 1 at the tips
            if gradient:
                colour = lerp_color(self.grad_start, self.grad_end, frac)
            else:
                colour = self.line_color
            # start at `start_w` and taper by `thin` for each generation deeper
            width = max(1, int(round(start_w * (thin ** d))))
            cv.create_line(ax, ay, bx, by, fill=colour, width=width)

    # ------------------------------------------------------------------- #
    #  Animation
    # ------------------------------------------------------------------- #
    def _apply_rot(self, segs):
        """Rotate every segment by the current rotation setting."""
        rot = math.radians(self.rot_var.get())
        if not rot:
            return segs
        ca, sa = math.cos(rot), math.sin(rot)
        return [((x0 * ca - y0 * sa, x0 * sa + y0 * ca),
                 (x1 * ca - y1 * sa, x1 * sa + y1 * ca), d)
                for (x0, y0), (x1, y1), d in segs]

    def _build_frames(self):
        """Build one segment-list per growth step (frame 0 = nothing grown)."""
        axiom = self.axiom_var.get()
        rules = self._collect_rules()
        try:
            angle = float(self.angle_var.get())
        except (tk.TclError, ValueError):
            angle = 25.0
        n = self.iter_var.get()
        frames = []
        if self.mode_var.get() == "prob":
            snaps = expand_probabilistic_frames(
                axiom, rules, n, self.dist_editor.get_points(), seed=self.seed)
            for s, depths in snaps:
                frames.append(self._apply_rot(
                    turtle_segments(s, angle, depths=depths,
                                    shrink=self.shrink_var.get())))
        else:
            for order in range(n + 1):
                s = expand_parallel(axiom, rules, order)
                frames.append(self._apply_rot(turtle_segments(s, angle)))
        return frames

    def toggle_animate(self):
        if self._animating:
            self._stop_anim()
            return
        if not self.axiom_var.get():
            return
        frames = self._build_frames()
        if not frames:
            return
        # fixed camera from the union of all frames so growth stays framed
        xs = [v for fr in frames for (p0, p1, _) in fr
              for v in (p0[0], p1[0])]
        ys = [v for fr in frames for (p0, p1, _) in fr
              for v in (p0[1], p1[1])]
        if not xs:
            return
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        bw = (maxx - minx) or 1.0
        bh = (maxy - miny) or 1.0
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        margin = 24
        scale = min((w - 2 * margin) / bw, (h - 2 * margin) / bh)
        offx = (w - bw * scale) / 2 - minx * scale
        offy = (h - bh * scale) / 2 - miny * scale
        maxd = max((d for fr in frames for (_, _, d) in fr), default=0) or 1

        self._frames = frames
        self._anim_tf = (scale, offx, offy, maxd, w, h)
        self._anim_idx = 0
        self._animating = True
        self.anim_btn.config(text="Stop")
        # aim for roughly a 3-second animation, clamped to a sane frame rate
        self._anim_delay = max(25, int(3000 / len(frames)))
        self._anim_step()

    def _anim_step(self):
        if not self._animating:
            return
        frames = self._frames
        if self._anim_idx >= len(frames):
            self._stop_anim()
            return
        self._draw_frame(frames[self._anim_idx], *self._anim_tf)
        self.status.config(
            text=f"animating frame {self._anim_idx + 1}/{len(frames)}")
        self._anim_idx += 1
        self._anim_job = self.after(self._anim_delay, self._anim_step)

    def _stop_anim(self):
        self._animating = False
        if self._anim_job:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self.anim_btn.config(text="Animate")
        self.render()        # restore the normal auto-fitted view

    def _draw_frame(self, segments, scale, offx, offy, maxd, w, h):
        """Draw one animation frame using a fixed camera transform."""
        cv = self.canvas
        cv.delete("all")
        prob = self.mode_var.get() == "prob"
        start_w = self.start_var.get() if prob else 1.0
        thin = self.thin_var.get() if prob else 1.0
        gradient = prob and self.gradient_var.get()

        def tx(x, y):
            return x * scale + offx, h - (y * scale + offy)

        for (x0, y0), (x1, y1), d in segments:
            ax, ay = tx(x0, y0)
            bx, by = tx(x1, y1)
            frac = d / maxd
            colour = (lerp_color(self.grad_start, self.grad_end, frac)
                      if gradient else self.line_color)
            width = max(1, int(round(start_w * (thin ** d))))
            cv.create_line(ax, ay, bx, by, fill=colour, width=width)


if __name__ == "__main__":
    App().mainloop()