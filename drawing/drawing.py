"""2D drawings (DXF) of base and lid: hidden-line projections of the real solids + dimensions.
.venv-b3d python drawing/drawing.py      then  Python311 drawing/to_pdf.py  for the PDFs
Dimension values come from the solids and layout.json, never typed by hand.
"""
import datetime
import json
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment
from build123d import import_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DWG = ROOT / "drawing"
sys.path.insert(0, str(ROOT / "enclosure"))
import params as P  # noqa: E402

# view: (camera position, up) ; u/v = world axes shown right/up on the sheet
VIEWS = {
    "TOP": ((0, 0, 500), (0, 1, 0), (0, 1)),
    "FRONT (from -Y)": ((0, -500, 0), (0, 0, 1), (0, 2)),
    "RIGHT (from +X)": ((500, 0, 0), (0, 0, 1), (1, 2)),
}


def project(shape, cam, up):
    vis, hid = shape.project_to_viewport(cam, viewport_up=up, look_at=(0, 0, 0))
    return vis, hid


def edges_to_dxf(msp, edges, off, layer):
    for e in edges:
        pts = [(p.X + off[0], p.Y + off[1]) for p in e.positions([i / 24 for i in range(25)])] \
            if e.geom_type.name != "LINE" else [(e.start_point().X + off[0], e.start_point().Y + off[1]),
                                                (e.end_point().X + off[0], e.end_point().Y + off[1])]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer})


def setup(doc):
    doc.units = ezdxf.units.MM
    for n, c, lt in (("VISIBLE", 7, "CONTINUOUS"), ("HIDDEN", 8, "DASHED"), ("DIM", 1, "CONTINUOUS"),
                     ("FRAME", 7, "CONTINUOUS"), ("TEXT", 7, "CONTINUOUS"), ("CENTER", 3, "CENTER")):
        if lt not in doc.linetypes:
            doc.linetypes.add(lt, pattern=[9, 6, -3] if lt == "DASHED" else [20, 12, -3, 2, -3])
        doc.layers.add(n, color=c, linetype=lt)
    ds = doc.dimstyles.new("ISO35")
    ds.dxf.dimtxt, ds.dxf.dimasz, ds.dxf.dimexe, ds.dxf.dimexo = 2.5, 2.5, 1.0, 0.8
    ds.dxf.dimgap, ds.dxf.dimdec, ds.dxf.dimtad, ds.dxf.dimclrd, ds.dxf.dimclre = 0.8, 2, 1, 1, 1
    ds.dxf.dimzin = 8
    ds.dxf.dimdsep = ord(".")
    doc.styles.add("ISO", font="isocpeur.ttf")
    ds.dxf.dimtxsty = "ISO"


def frame(msp, title, part, notes):
    W, H = 420, 297
    msp.add_lwpolyline([(0, 0), (W, 0), (W, H), (0, H)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_lwpolyline([(20, 10), (W - 10, 10), (W - 10, H - 10), (20, H - 10)], close=True, dxfattribs={"layer": "FRAME"})
    x0, y0 = W - 10 - 180, 10
    msp.add_lwpolyline([(x0, y0), (W - 10, y0), (W - 10, y0 + 36), (x0, y0 + 36)], close=True, dxfattribs={"layer": "FRAME"})
    rows = [(title, 5), (f"Part: {part}   Scale 1:1   Units: mm   Sheet A3", 3),
            ("Material: PETG or PLA, FDM 0.4 mm nozzle, 0.2 mm layers   General tol. +-0.2", 2.5),
            (f"Drawn: Ha Phan Thanh Hai   {datetime.date.today().isoformat()}   Projection: third angle", 2.5)]
    y = y0 + 28
    for t, h in rows:
        msp.add_text(t, height=h, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement((x0 + 3, y))
        y -= 8
    # third-angle projection symbol
    sx, sy = x0 + 150, y0 + 22
    msp.add_circle((sx + 18, sy), 4, dxfattribs={"layer": "FRAME"}); msp.add_circle((sx + 18, sy), 2, dxfattribs={"layer": "FRAME"})
    msp.add_lwpolyline([(sx, sy - 2), (sx + 10, sy - 4), (sx + 10, sy + 4), (sx, sy + 2)], close=True, dxfattribs={"layer": "FRAME"})
    msp.add_text("Third-angle", height=2.0, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement((sx, sy - 10))
    y = H - 20
    for i, n in enumerate(notes, 1):
        msp.add_text(f"{i}. {n}", height=2.5, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement((W - 180, y))
        y -= 5


def dim(msp, p1, p2, base, angle=0, text=None):
    d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dimstyle="ISO35",
                           text=text if text else "<>", dxfattribs={"layer": "DIM"})
    d.render()
    return d.dimension.get_measurement()


def label(msp, txt, at):
    msp.add_text(txt, height=3.5, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement(at)


def sheet(part_name, shape, L, place, extra):
    doc = ezdxf.new("R2018", setup=True)
    setup(doc)
    msp = doc.modelspace()
    bb = shape.bounding_box()
    lo, hi = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
    maps = {}
    for name, (cam, up, (ui, vi)) in VIEWS.items():
        vis, hid = project(shape, cam, up)
        allp = [p for e in vis for p in (e.start_point(), e.end_point())]
        umin, vmin = min(p.X for p in allp), min(p.Y for p in allp)
        umax, vmax = max(p.X for p in allp), max(p.Y for p in allp)
        # the projection must be an orthographic copy of the part extents along the two shown axes
        assert abs((umax - umin) - (hi[ui] - lo[ui])) < 0.05 and abs((vmax - vmin) - (hi[vi] - lo[vi])) < 0.05, name
        ox, oy = place[name]
        off = (ox - umin, oy - vmin)
        edges_to_dxf(msp, vis, off, "VISIBLE")
        edges_to_dxf(msp, hid, off, "HIDDEN")
        label(msp, name, (ox, oy + (vmax - vmin) + (26 if name == "TOP" else 16)))
        # world (axis ui, axis vi) -> sheet
        maps[name] = (lambda a, b, ui=ui, vi=vi, ox=ox, oy=oy: (ox + a - lo[ui], oy + b - lo[vi]))
    extra(msp, maps, lo, hi, L)
    doc.saveas(DWG / f"{part_name}.dxf")
    print("wrote", DWG / f"{part_name}.dxf")


def lid_dims(msp, M, lo, hi, L):
    T, F, R = M["TOP"], M["FRONT (from -Y)"], M["RIGHT (from +X)"]
    dim(msp, T(lo[0], lo[1]), T(hi[0], lo[1]), base=T(0, lo[1] - 14))
    dim(msp, T(lo[0], lo[1]), T(lo[0], hi[1]), base=T(lo[0] - 14, 0), angle=90)
    va = L["va"]
    dim(msp, T(va[0], va[3]), T(va[2], va[3]), base=T(0, hi[1] + 8))
    dim(msp, T(va[2], va[1]), T(va[2], va[3]), base=T(hi[0] + 8, 0), angle=90)
    dim(msp, T(lo[0], va[3]), T(va[0], va[3]), base=T(0, hi[1] + 16))
    dim(msp, T(va[2], hi[1]), T(va[2], va[3]), base=T(hi[0] + 16, 0), angle=90)
    for k, txt, tx in (("reset", f"RESET pin %%c{P.RESET_PIN_D} THRU, guide tube", -40), ("led", f"CHG LED light pipe %%c{P.LED_BORE_D} THRU (rod %%c{P.LED_PIPE_D})", -40)):
        o = L["openings"][k]
        tip = T(o["x"], o["y"])
        knee = (T(hi[0], 0)[0] + 25, tip[1] + (10 if k == "led" else -6))
        msp.add_leader([tip, knee, (knee[0] + 75, knee[1])], dxfattribs={"layer": "DIM"})
        msp.add_text(txt, height=2.5, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement((knee[0] + 1, knee[1] + 1))
        dim(msp, T(lo[0], o["y"]), T(o["x"], o["y"]), base=T(0, o["y"] - 4 if k == "reset" else o["y"] + 4))
    for (x, y, r) in L["screws_lid"]:
        msp.add_text(f"%%c{P.CLR_HOLE_M3} THRU ({r})", height=2.5, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement(T(x + 4, y - 1))
    for (x, y) in L["corners"]:
        msp.add_text(f"%%c{P.CLR_HOLE_M3} THRU", height=2.5, dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement(T(x + 4, y - 1))
    u = L["openings"]["usb"]
    zb = L["z"]["split"]
    dim(msp, F(u["x"] - u["w"] / 2, zb), F(u["x"] + u["w"] / 2, zb), base=F(0, lo[2] - 10))
    dim(msp, F(lo[0], hi[2]), F(u["x"], hi[2]), base=F(0, hi[2] + 10))
    dim(msp, F(u["x"] + u["w"] / 2, zb), F(u["x"] + u["w"] / 2, u["z"] + u["h"] / 2), base=F(u["x"] + u["w"] / 2 + 8, 0), angle=90)
    dim(msp, F(lo[0], lo[2]), F(lo[0], hi[2]), base=F(lo[0] - 10, 0), angle=90)
    msp.add_text("USB-C pocket through the wall, open to the parting line", height=2.5,
                 dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement(F(lo[0], lo[2] - 20))
    q = L["openings"]["qwiic"]
    dim(msp, R(q["y"] - q["w"] / 2, q["z"] - q["h"] / 2), R(q["y"] + q["w"] / 2, q["z"] - q["h"] / 2), base=R(0, lo[2] - 10))
    dim(msp, R(q["y"] + q["w"] / 2, q["z"] - q["h"] / 2), R(q["y"] + q["w"] / 2, q["z"] + q["h"] / 2), base=R(q["y"] + q["w"] / 2 + 8, 0), angle=90)
    dim(msp, R(lo[1], hi[2]), R(q["y"], hi[2]), base=R(0, hi[2] + 10))

def base_dims(msp, M, lo, hi, L):
    T, F = M["TOP"], M["FRONT (from -Y)"]
    dim(msp, T(lo[0], lo[1]), T(hi[0], lo[1]), base=T(0, lo[1] - 14))
    dim(msp, T(lo[0], lo[1]), T(lo[0], hi[1]), base=T(lo[0] - 14, 0), angle=90)
    pts = [tuple(h) for h in L["holes"]] + [tuple(c) for c in L["corners"]]
    for i, (x, y) in enumerate(sorted(pts)):
        msp.add_circle(T(x, y), 0.6, dxfattribs={"layer": "CENTER"})
    xs = sorted({round(x, 3) for x, _ in pts})
    ys = sorted({round(y, 3) for _, y in pts})
    for j, x in enumerate(xs):
        dim(msp, T(lo[0], lo[1]), T(x, lo[1]), base=T(0, lo[1] - 22 - 6 * j))
    for j, y in enumerate(ys):
        dim(msp, T(lo[0], lo[1]), T(lo[0], y), base=T(lo[0] - 22 - 6 * j, 0), angle=90)
    msp.add_text(f"6x %%c{P.INSERT_HOLE_D} DEPTH {P.INSERT_HOLE_DEPTH} for M3x5.7 heat-set insert (ruthex RX-M3x5.7)", height=2.5,
                 dxfattribs={"layer": "TEXT", "style": "ISO"}).set_placement(T(lo[0], hi[1] + 6))
    dim(msp, F(lo[0], lo[2]), F(lo[0], hi[2]), base=F(lo[0] - 10, 0), angle=90)
    dim(msp, F(hi[0], lo[2]), F(hi[0], P.Z_SPLIT), base=F(hi[0] + 10, 0), angle=90)


def main():
    L = json.loads((OUT / "layout.json").read_text())
    common = [f"Board: esp32s3_epaper (KiCad), frame = kicad-cli STEP frame.",
              f"All walls >= 1.6 mm (checked, verify/report.json).",
              "Opening positions match KiCad footprint data (CAD check, verify/report.json)."]
    lid = import_step(OUT / "lid.step")
    base = import_step(OUT / "base.step")
    place = {"TOP": (55, 140), "FRONT (from -Y)": (55, 72), "RIGHT (from +X)": (190, 72)}
    sheet("lid", lid, L, place, lid_dims)
    sheet("base", base, L, place, base_dims)
    # title blocks + notes are added in a second pass so frame() stays independent of the views
    for part, title, notes in (("lid", "ESP32-S3 e-paper enclosure - LID", common + [
            "Print upside down (top plate on the bed). Window lip chamfer 0.4 x 45.",
            "Locating lip 1.7 wide, 2.0 deep, 0.2 clearance inside the base wall.",
            "Panel GDEY029T94: tape on the plate underside, NOT over the 4.5 mm FPC-side bonding strip (0.3 relief)."]),
            ("base", "ESP32-S3 e-paper enclosure - BASE", common + [
            "Print as shown (floor on the bed).",
            "Battery pocket ribs for a 50 x 34 x 5 mm cell (assumed 503450, 1000 mAh).",
            "Screws ISO 7045: M3x6 (2 pcs) at H2, H4; M3x14 (2 pcs) through lid at H1, H3; M3x12 (2 pcs) at lid corners.",
            "Print a test coupon of one insert boss first: insert hole diameter depends on the printer."])):
        doc = ezdxf.readfile(DWG / f"{part}.dxf")
        frame(doc.modelspace(), title, part, notes)
        doc.saveas(DWG / f"{part}.dxf")


if __name__ == "__main__":
    main()
