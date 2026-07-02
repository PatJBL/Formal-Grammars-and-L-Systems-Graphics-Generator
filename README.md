# Formal Grammars and L-Systems Graphics Generator

An interactive Python tool for generating graphics from **L-systems** and **formal grammars** — the simple rewrite-rule systems that model how plants and other branching structures grow. Alongside the classic L-system it adds a **probabilistic growth mode** of my own: instead of rewriting every symbol at once, it rewrites *one symbol at a time*, choosing where to grow from a probability distribution you can shape by hand.

The same handful of rules can produce **trees, lightning, rivers, bushes, snowflakes and more** — just by changing a few parameters.

> Built as an extension of a university mathematics essay on L-systems and the power of abstraction in mathematical modelling.

<!-- Add a few output images here once uploaded -->
<!-- ![Tree](images/tree.png) ![Lightning](images/lightning.png) ![River](images/river.png) -->

---

## What it does

Two growth modes:

- **L-system (parallel)** — the classic Lindenmayer behaviour: every symbol is rewritten simultaneously each iteration, like cells dividing in unison.
- **Probabilistic (serial)** — rules are applied to one symbol at a time. The symbol is chosen from a probability distribution spread across the whole current string, so you control *where* growth tends to happen. This is the main original contribution of the project.

A **turtle interpretation** then turns the resulting string of symbols into geometry — line segments drawn on screen.

## Features

- Live, interactive GUI (pure Python standard library — `tkinter`, no dependencies)
- Switch instantly between parallel and probabilistic modes
- **Draggable probability-distribution editor** — drag points to shape where growth occurs (double-click to add, right-click or drag-off to delete)
- Visual / "art" controls (probabilistic mode):
  - **Colour gradient** from trunk to tips
  - **Shrink** — branches shorten with each generation
  - **Thin rate** + **start width** — branches taper as they grow
  - Whole-render **rotation**, custom line/background colours
- **Animation** — watch the structure grow over ~3 seconds
- Built-in **presets**: Koch curve, Fractal plant, Bamboo, Bush, Crop, Branch, Sprite lightning, Snowflake
- **Save / load** full parameter sets to disk (JSON); reproducible output via a fixed random seed

## Run it

Requires **Python 3** (uses only the standard library, including `tkinter`).

```bash
python3 lsystem_generator.py
```
no `pip install` needed.

## Turtle alphabet

| Symbol | Action |
|--------|--------|
| `F`, `G`, any capital letter | move forward and draw a line |
| `f`, any lowercase letter | move forward without drawing |
| `+` | turn left by the angle |
| `-` | turn right by the angle |
| `[` | push (save current position & heading) |
| `]` | pop (restore last saved position & heading) |

### Example (classic L-system)

```
axiom:  X
rules:  X → F[+X][-X]FX
        F → FF
angle:  25°
```

Iterating these two rules and drawing the result produces a self-similar fractal plant.

## The idea behind it

Classic L-systems rewrite every symbol **in parallel** — biologically faithful to cells dividing together. The question that started this project: what if growth were **not** perfectly synchronised? By rewriting one symbol at a time, chosen from a probability distribution across the structure, you get more organic, controllable variation from the same minimal rule sets — while keeping the core strength of L-systems: enormous visual complexity stored in only a few characters.

## Built with

- Python 3 (standard library / `tkinter`)
- Developed with [Claude Code](https://www.anthropic.com/claude-code) as a coding partner

## License

MIT — feel free to use, modify and build on it.

---

*Created by Patrick Barrett-Lennard.*
