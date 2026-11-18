"""Board data read from the KiCad files (never typed by hand).

Frame used everywhere in this repo = the frame of the STEP that kicad-cli exports:
x right, y = -y_kicad, z up, board bottom at z = 0.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def k2s(x, y):
    """KiCad page coordinates (mm, y down) -> STEP frame (y up)."""
    return x, -y


def load():
    b = json.loads((BUILD / "board.json").read_text())
    fab = json.loads((BUILD / "fab_outlines.json").read_text())
    x0, y0, w, h = b["edge_bbox"]
    # edge_bbox includes half the 0.1 mm Edge.Cuts line width; the outline itself is the line centres
    edges = b["edges"]
    xs = [v for e in edges for v in (e[1], e[3])]
    ys = [v for e in edges for v in (e[2], e[4])]
    assert all(e[0] == "Line" for e in edges) and len(edges) == 4, "outline is not a plain rectangle"
    fp = {f["ref"]: f for f in b["fp"]}
    holes = []
    for f in b["fp"]:
        if not f["fpid"].startswith("MountingHole"):
            continue   # other drilled pads (USB shell legs, module vias) are not mounting holes
        for p in f["pads"]:
            holes.append({"ref": f["ref"], "xy": k2s(p[1], p[2]), "d": p[3]})
    return {
        "xmin": min(xs), "xmax": max(xs), "ymin": -max(ys), "ymax": -min(ys),
        "thickness": b["thickness"],
        "holes": holes, "fp": fp, "fab": fab,
    }


def fab_box(data, ref):
    """F.Fab outline bbox of a footprint, STEP frame: (xmin, ymin, xmax, ymax)."""
    x0, y0, x1, y1 = data["fab"][ref]["fab_bbox_kicad"]
    return x0, -y1, x1, -y0


def centre(data, ref):
    return k2s(*data["fp"][ref]["pos"])
