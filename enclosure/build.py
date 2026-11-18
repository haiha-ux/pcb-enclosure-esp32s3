"""Build base, lid and the assembly from the KiCad board.

.venv-b3d python enclosure/build.py
Writes out/: enclosure_assembly.step, base.step, lid.step, *.stl, enclosure.3mf, layout.json
"""
import json
import os
import math
import sys
from pathlib import Path

from build123d import (Align, Box, Compound, Cylinder, Location, Pos, Rectangle,
                       RectangleRounded, SlotCenterToCenter, Solid, Vector, export_step,
                       export_stl, extrude, import_step, offset, Kind, Mesher, Plane,
                       Wire, Line, CenterArc, sweep, Face, chamfer, Axis, Rot)

sys.path.insert(0, str(Path(__file__).parent))
import board as B
import params as P

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("ENCL_OUT", ROOT / "out"))
for _k, _v in json.loads(os.environ.get("ENCL_PARAMS", "{}")).items():   # used only by verify/break_test.py
    setattr(P, _k, _v)
A0 = (Align.MIN, Align.MIN, Align.MIN)


def box(x0, y0, z0, x1, y1, z1):
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=A0)


def cyl(x, y, z0, z1, d):
    return Pos(x, y, z0) * Cylinder(d / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def prism(face, z0, z1):
    return Pos(0, 0, z0) * extrude(face, z1 - z0)


def layout():
    d = B.load()
    step = import_step(B.BUILD / "board.step")
    kids = {}
    for c in step.children:
        kids.setdefault(c.label, []).append(c)
    copper = kids["esp32s3_epaper_copper"][0].bounding_box()
    zb, zt = copper.min.Z, copper.max.Z            # board bottom / top incl. copper
    L = {"board": {"x0": d["xmin"], "x1": d["xmax"], "y0": d["ymin"], "y1": d["ymax"], "zb": zb, "zt": zt}}
    L["holes"] = [h["xy"] for h in d["holes"]]
    names = [h["ref"] for h in d["holes"]]
    L["hole_refs"] = names

    def fab(ref):
        return B.fab_box(d, ref)

    # parts without a KiCad 3D model -> proxy boxes (XY from F.Fab, height from datasheets)
    sw = {r: B.centre(d, r) for r in ("SW1", "SW2")}
    prox = {
        "J1_USB-C": (*fab("J1")[:2], zt, *fab("J1")[2:], zt + P.H_USBC),
        "J2_JST-PH": (*fab("J2")[:2], zt, *fab("J2")[2:], zt + P.H_JST_PH_SIDE),
        "J4_FPC": (*fab("J4")[:2], zt, *fab("J4")[2:], zt + P.H_FPC_CONN),
    }
    for r, (x, y) in sw.items():
        h = P.TACT_BODY / 2
        prox[f"{r}_tact"] = (x - h, y - h, zt, x + h, y + h, zt + P.H_TACT)
    L["proxies"] = prox
    L["refs"] = {r: B.centre(d, r) for r in ("J1", "J2", "J3", "J4", "SW1", "SW2", "D2", "D3", "U4")}
    L["fab"] = {r: fab(r) for r in ("J1", "J2", "J3", "J4", "U4")}
    j3 = [c for c in step.children if c.label.startswith("JST_SH")][0].bounding_box()
    L["J3_box"] = [j3.min.X, j3.min.Y, j3.min.Z, j3.max.X, j3.max.Y, j3.max.Z]

    # highest STEP component and proxy anywhere: lid plate underside clears it
    comps = [c for c in step.children if not c.label.startswith("esp32s3_epaper")]
    top_step = max(c.bounding_box().max.Z for c in comps)
    top_prox = max(v[5] for v in prox.values())
    j2_top = prox["J2_JST-PH"][5]
    z_plate_bot = j2_top + 0.5
    z_panel_bot = z_plate_bot - P.PANEL_T
    L["z"] = {"floor_bot": P.Z_FLOOR_BOT, "floor_top": P.Z_FLOOR_TOP, "split": P.Z_SPLIT,
              "corner_joint": P.Z_CORNER_JOINT, "plate_bot": z_plate_bot, "top": z_plate_bot + P.PLATE,
              "panel_bot": z_panel_bot, "top_step_part": top_step, "top_proxy": top_prox}

    # e-paper panel position follows from the FPC tail length
    j4 = fab("J4")
    glass_y, loop_y, r, z_exit, z_slot, end_y = P.fpc_loop(z_panel_bot, zt, j4[1], j4[3])
    tail_cx = (j4[0] + j4[2]) / 2
    px0 = tail_cx - (P.FPC_TOP_OFFSET + P.FPC_W / 2)
    panel = (px0, glass_y, z_panel_bot, px0 + P.PANEL_W, glass_y + P.PANEL_L, z_panel_bot + P.PANEL_T)
    va = (panel[3] - P.VA_FROM_SIDE - P.VA_W, panel[4] - P.VA_FROM_FAR_END - P.VA_L,
          panel[3] - P.VA_FROM_SIDE, panel[4] - P.VA_FROM_FAR_END)
    L["panel"] = panel
    L["va"] = va
    L["fpc"] = {"glass_y": glass_y, "loop_y": loop_y, "r": r, "z_exit": z_exit, "z_slot": z_slot,
                "end_y": end_y, "x0": tail_cx - P.FPC_W / 2, "x1": tail_cx + P.FPC_W / 2}

    # interior outline
    bd = L["board"]
    phr_x0 = fab("J2")[0] - P.PHR2["length"]
    xi0 = min(bd["x0"] - P.CLR_BOARD, phr_x0 - 3.0)          # 3 mm for the battery wires to turn down
    xi1 = max(bd["x1"] + P.CLR_BOARD, panel[3] + P.CLR_PANEL)
    yi0 = bd["y0"] - P.CLR_BOARD
    c = P.BOSS_OD / 2 + 0.3                                   # corner column centre inset
    yi1 = panel[4] + P.CLR_PANEL + c + P.BOSS_OD / 2
    loop_min = loop_y - r - P.FPC_T
    bulge = (j4[0] - 0.5, loop_min - 0.5, j4[2] + 0.5, yi0)
    L["interior"] = {"x0": xi0, "x1": xi1, "y0": yi0, "y1": yi1, "bulge": bulge, "corner_c": c}
    L["corners"] = [(xi0 + c, yi1 - c), (xi1 - c, yi1 - c)]
    L["phr_x0"] = phr_x0
    bx, by, bz = P.BATT
    b0 = yi0 + P.BATT_CLR                                    # as far from the antenna as the board allows
    L["battery"] = (36.0 - bx / 2, b0, P.Z_FLOOR_TOP, 36.0 + bx / 2, b0 + by, P.Z_FLOOR_TOP + bz)
    d2 = [c for c in step.children if c.label.startswith("LED_0603")]
    d2 = min(d2, key=lambda c: abs(c.bounding_box().center().X - L["refs"]["D2"][0]) + abs(c.bounding_box().center().Y - L["refs"]["D2"][1]))
    L["led_top"] = d2.bounding_box().max.Z
    return L, step


def outlines(L):
    I = L["interior"]
    inner = Pos((I["x0"] + I["x1"]) / 2, (I["y0"] + I["y1"]) / 2) * Rectangle(I["x1"] - I["x0"], I["y1"] - I["y0"])
    bx0, by0, bx1, by1 = I["bulge"]
    inner = inner + Pos((bx0 + bx1) / 2, (by0 + by1 + 0.01) / 2) * Rectangle(bx1 - bx0, by1 - by0 + 0.01)
    outer = offset(inner, P.WALL, kind=Kind.ARC)
    return inner, outer


def build(L):
    inner, outer = outlines(L)
    z = L["z"]
    bd = L["board"]
    holes = L["holes"]

    # ---------------- base ----------------
    base_walls = prism(outer, z["floor_bot"], z["split"]) - prism(inner, z["floor_top"], z["split"])
    base = base_walls
    for (x, y) in holes:                                     # board standoffs, insert from the top
        base += cyl(x, y, z["floor_top"] - 0.01, bd["zb"], P.BOSS_OD)
    for (x, y) in L["corners"]:                              # lid columns, insert from the top
        base += cyl(x, y, z["floor_top"] - 0.01, z["corner_joint"], P.BOSS_OD)
    I = L["interior"]
    feats = []
    for (x, y) in list(holes) + list(L["corners"]):
        r = P.BOSS_OD / 2
        top = bd["zb"] if (x, y) in [tuple(h_) for h_ in holes] else P.Z_SPLIT
        # a boss closer than 0.8 mm to a wall is filled out to that wall (no unprintable slot)
        wx = I["x0"] if x - r - I["x0"] < 0.8 else I["x1"] if I["x1"] - (x + r) < 0.8 else None
        wy = I["y0"] if y - r - I["y0"] < 0.8 else I["y1"] if I["y1"] - (y + r) < 0.8 else None
        for z0_, z1_, e in ((z["floor_top"] - 0.01, min(top, P.Z_SPLIT), 0.01), (P.Z_SPLIT, top, 0.0)):
            if z1_ <= z0_:
                continue
            ex = None if wx is None else wx + (e if wx > x else -e)
            ey = None if wy is None else wy + (e if wy > y else -e)
            if ex is not None:
                base += box(min(x, ex), y - r, z0_, max(x, ex), y + r, z1_)
            if ey is not None:
                base += box(x - r, min(y, ey), z0_, x + r, max(y, ey), z1_)
            if ex is not None and ey is not None:
                base += box(min(x, ex), min(y, ey), z0_, max(x, ex), max(y, ey), z1_)
    bx0, by0, _, bx1, by1, _ = L["battery"]
    g, t, h, arm = P.BATT_CLR, P.RIB, 3.0, 6.0
    for sx, xc in ((-1, bx0 - g), (1, bx1 + g)):
        for sy, yc in ((-1, by0 - g), (1, by1 + g)):
            for xs, ys in ((sorted((xc - sx * arm, xc + sx * t)), sorted((yc, yc + sy * t))),
                           (sorted((xc, xc + sx * t)), sorted((yc - sy * arm, yc + sy * t)))):
                y0_ = max(ys[0], I["y0"] - 0.01)            # ribs stop at the front wall (it already holds the cell)
                if ys[1] > y0_ + 0.02:
                    base += box(xs[0], y0_, z["floor_top"] - 0.01, xs[1], ys[1], z["floor_top"] + h)
    for (x, y) in holes:
        base -= cyl(x, y, bd["zb"] - P.INSERT_HOLE_DEPTH, bd["zb"] + 1, P.INSERT_HOLE_D)
    for (x, y) in L["corners"]:
        base -= cyl(x, y, z["corner_joint"] - P.INSERT_HOLE_DEPTH, z["corner_joint"] + 1, P.INSERT_HOLE_D)

    # ---------------- lid ----------------
    lid_walls = prism(outer, z["split"], z["top"]) - prism(inner, z["split"] - 1, z["plate_bot"])
    lid = lid_walls
    screws_lid = []
    for (x, y), ref in zip(holes, L["hole_refs"]):
        if x < L["panel"][0] - P.BOSS_OD:                    # holes not under the panel clamp the board from the lid
            lid += cyl(x, y, bd["zt"], z["plate_bot"] + 0.01, P.BOSS_OD)
            r = P.BOSS_OD / 2
            if y - r - I["y0"] < 0.8:                        # web to the wall instead of a 0.3 mm slot
                lid += box(x - r, I["y0"] - 0.01, bd["zt"], x + r, y, z["plate_bot"] + 0.01)
            screws_lid.append((x, y, ref))
    for (x, y) in L["corners"]:
        lid += cyl(x, y, z["corner_joint"], z["plate_bot"] + 0.01, P.BOSS_OD)
        wall_x = I["x0"] - 0.01 if x < (I["x0"] + I["x1"]) / 2 else I["x1"] + 0.01
        xa, xb = sorted((x, wall_x))
        r = P.BOSS_OD / 2
        lid += box(xa, y - r, z["corner_joint"], xb, I["y1"] + 0.01, z["plate_bot"] + 0.01)
        lid += box(x - r, y, z["corner_joint"], x + r, I["y1"] + 0.01, z["plate_bot"] + 0.01)
    # panel locating ribs: left side and FPC end (right side is the wall, far end is the corner columns)
    p = L["panel"]
    f = L["fpc"]
    rz0, rz1 = z["plate_bot"] - 1.0, z["plate_bot"] + 0.01
    c = P.CLR_PANEL
    lid += box(p[0] - c - P.RIB, p[1] - c - P.RIB, rz0, p[0] - c, p[4] + c, rz1)
    lid += box(p[0] - c - P.RIB, p[1] - c - P.RIB, rz0, f["x0"] - 0.5, p[1] - c, rz1)
    lid += box(f["x1"] + 0.5, p[1] - c - P.RIB, rz0, I["x1"] + 0.01, p[1] - c, rz1)
    lid += box(p[0] - c - P.RIB, p[4] + c, rz0, I["x1"] + 0.01, p[4] + c + P.RIB, rz1)
    # relief over the IC bonding strip on the FPC side of the glass
    lid -= box(p[0] - c, p[1] - c, z["plate_bot"] - 1, p[3] + c, p[1] + P.BONDING_STRIP, z["plate_bot"] + P.BONDING_RELIEF)
    # light pipe guide for the CHG LED
    dx, dy = L["refs"]["D2"]
    pipe_bot = L["led_top"] + P.LED_PIPE_GAP
    lid += cyl(dx, dy, pipe_bot, z["plate_bot"] + 0.01, P.LED_BORE_D + 2 * P.RIB)
    # reset pin guide tube
    sx, sy = L["refs"]["SW1"]
    tube_bot = bd["zt"] + P.H_TACT + P.RESET_TUBE_BOTTOM_GAP
    lid += cyl(sx, sy, tube_bot, z["plate_bot"] + 0.01, P.RESET_PIN_D + 2 * P.RIB)
    # cuts
    for (x, y, _) in screws_lid:
        lid -= cyl(x, y, bd["zt"] - 1, z["top"] + 1, P.CLR_HOLE_M3)
    for (x, y) in L["corners"]:
        lid -= cyl(x, y, z["corner_joint"] - 1, z["top"] + 1, P.CLR_HOLE_M3)
    lid -= cyl(sx, sy, tube_bot - 1, z["top"] + 1, P.RESET_PIN_D)
    lid -= cyl(dx, dy, pipe_bot - 1, z["top"] + 1, P.LED_BORE_D)
    va = L["va"]
    win = box(va[0], va[1], z["plate_bot"] - 1, va[2], va[3], z["top"] + 1)
    k = P.WINDOW_CHAMFER
    win += Pos(0, 0, z["top"] - k) * extrude(
        Pos((va[0] + va[2]) / 2, (va[1] + va[3]) / 2) * Rectangle(va[2] - va[0], va[3] - va[1]),
        k + 0.001, taper=-45)
    lid -= win
    # USB-C: pocket through the wall, sized for the overmold, so the plug seats fully (no recess behind the mouth)
    jx = (L["fab"]["J1"][0] + L["fab"]["J1"][2]) / 2
    jz = bd["zt"] + P.H_USBC / 2
    yw = I["y0"]
    rw, rh = P.USB_OVERMOLD[0] + 2 * P.USB_POCKET_CLR, P.USB_OVERMOLD[1] + 2 * P.USB_POCKET_CLR
    lid -= box(jx - rw / 2, yw - P.WALL - 1, z["split"] - 0.01, jx + rw / 2, yw + 0.01, jz + rh / 2)  # open to the split: no thin ledge under it
    ow, oh = rw, rh
    # Qwiic opening in the right wall
    j3 = L["J3_box"]
    qy, qz = (j3[1] + j3[4]) / 2, (j3[2] + j3[5]) / 2
    qw, qh = P.SHR04["width"] + 2 * P.QWIIC_OPEN_CLR, P.SHR04["height"] + 2 * P.QWIIC_OPEN_CLR
    lid -= box(I["x1"] - 1, qy - qw / 2, qz - qh / 2, I["x1"] + P.WALL + 1, qy + qw / 2, qz + qh / 2)
    # locating lip: hangs from the lid inside the base wall all round, cut back wherever base parts sit
    lip_ring = offset(inner, -P.LIP_CLR) - offset(inner, -(P.LIP_CLR + P.LIP_T))
    lip = prism(lip_ring, z["split"] - P.LIP_H, z["split"] + 0.01)
    lip += prism(inner - offset(inner, -(P.LIP_CLR + P.LIP_T)), z["split"], z["split"] + 1.7)
    L["usb_tmp"] = {"x": jx, "z": jz}
    feats.append(box(jx - rw / 2 - 2, I["y0"] - 1, z["split"] - P.LIP_H - 1, jx + rw / 2 + 2, I["y0"] + 2.5, z["split"] + 2))
    feats.append(box(*L["battery"]))
    bx0_, by0_, bx1_, _ = I["bulge"]
    feats.append(box(bx0_ - 2.0, by0_ - 1.0, z["split"] - P.LIP_H - 1, bx1_ + 2.0, I["y0"] + 2.5, z["split"] + 2))
    for f_ in feats + list((base - base_walls).solids()):
        b_ = f_.bounding_box()
        lip -= box(b_.min.X - 0.3, b_.min.Y - 0.3, z["split"] - P.LIP_H - 1, b_.max.X + 0.3, b_.max.Y + 0.3, z["split"] + 2)  # full height: no thin leftovers
    lid += lip
    L["lip_volume"] = lip.volume
    L["openings"] = {"usb": {"x": jx, "z": jz, "w": ow, "h": oh},
                     "qwiic": {"y": qy, "z": qz, "w": qw, "h": qh},
                     "reset": {"x": sx, "y": sy, "d": P.RESET_PIN_D, "tube_bottom": tube_bot},
                     "led": {"x": dx, "y": dy, "d": P.LED_BORE_D, "pipe_bottom": pipe_bot}}
    L["screws_lid"] = screws_lid
    return base, lid, base_walls, lid_walls


def fpc_solid(L):
    f, p = L["fpc"], L["panel"]
    x0, x1 = f["x0"], f["x1"]
    r = f["r"]
    zc = (f["z_exit"] + f["z_slot"]) / 2
    path = (Line((f["glass_y"] + 0.01, f["z_exit"]), (f["loop_y"], f["z_exit"]))
            + CenterArc((f["loop_y"], zc), r, 90, 180)
            + Line((f["loop_y"], f["z_slot"]), (f["end_y"], f["z_slot"])))
    # path drawn in the (y, z) plane -> map to world with Plane.YZ (x normal)
    wire = Plane.YZ.offset((x0 + x1) / 2) * Wire(path.edges())
    prof = Plane.XZ.offset(-(f["glass_y"] + 0.01)) * Pos((x0 + x1) / 2, f["z_exit"]) * Rectangle(x1 - x0, P.FPC_T)
    return sweep(prof, wire)


def mating(L):
    """Plugs a user will insert: must not touch the enclosure."""
    bd, o, I = L["board"], L["openings"], L["interior"]
    u = o["usb"]
    sw, sh = P.USB_SHELL
    mouth = L["fab"]["J1"][1]
    front = mouth - 0.1                                         # overmold stops at the board edge, 0.1 from the mouth
    m = {
        "usb_shell": box(u["x"] - sw / 2, front, u["z"] - sh / 2, u["x"] + sw / 2, mouth, u["z"] + sh / 2),
        "usb_overmold": box(u["x"] - P.USB_OVERMOLD[0] / 2, front - 25, u["z"] - P.USB_OVERMOLD[1] / 2,
                            u["x"] + P.USB_OVERMOLD[0] / 2, front, u["z"] + P.USB_OVERMOLD[1] / 2),
    }
    if "qwiic" not in o or not o["qwiic"].get("w"):
        return m
    j2y = (L["fab"]["J2"][1] + L["fab"]["J2"][3]) / 2
    m["phr2_plug"] = box(L["phr_x0"], j2y - P.PHR2["width"] / 2, bd["zt"], L["fab"]["J2"][0], j2y + P.PHR2["width"] / 2,
                         bd["zt"] + P.PHR2["height"])
    q = o["qwiic"]
    j3 = L["J3_box"]
    m["shr04_plug"] = box(j3[3], q["y"] - P.SHR04["width"] / 2, q["z"] - P.SHR04["height"] / 2,
                          j3[3] + P.SHR04["length"], q["y"] + P.SHR04["width"] / 2, q["z"] + P.SHR04["height"] / 2)
    return m


def main():
    OUT.mkdir(exist_ok=True)
    L, step = layout()
    base, lid, base_walls, lid_walls = build(L)
    base.label, lid.label = "base", "lid"
    meta = {}
    for n, s_ in (("base", base), ("lid", lid)):
        b = s_.bounding_box()
        meta[n] = {"volume": s_.volume, "bbox_min": [b.min.X, b.min.Y, b.min.Z], "bbox_max": [b.max.X, b.max.Y, b.max.Z],
                   "solids": len(s_.solids()), "valid": s_.is_valid}
    (OUT / "build_meta.json").write_text(json.dumps(meta, indent=1))
    export_step(base, OUT / "base.step")
    export_step(lid, OUT / "lid.step")
    export_stl(base, OUT / "base.stl", tolerance=0.01, angular_tolerance=0.1)
    export_stl(lid, OUT / "lid.stl", tolerance=0.01, angular_tolerance=0.1)
    prox = {k: box(*v) for k, v in L["proxies"].items()}
    pn = L["panel"]
    PL, PW, PE, PS = P.PANEL_TOP_LAYER                        # stepped glass: TFT 79.00 long, top layer 74.50
    panel = box(pn[0], pn[1], pn[2], pn[3], pn[4], pn[2] + P.PANEL_TFT_T)
    panel += box(pn[3] - PS - PW, pn[4] - PE - PL, pn[2] + P.PANEL_TFT_T - 0.01, pn[3] - PS, pn[4] - PE, pn[5])
    led = L["openings"]["led"]
    rod = cyl(led["x"], led["y"], led["pipe_bottom"], L["z"]["top"], P.LED_PIPE_D)
    rod.label = "light_pipe_2mm_PMMA"
    fpc = fpc_solid(L)
    bd = L["board"]
    heads = {f"screw_head_{r}": cyl(x, y, bd["zt"], bd["zt"] + P.SCREW_HEAD_K, P.SCREW_HEAD_D)
             for (x, y), r in zip(L["holes"], L["hole_refs"]) if r not in [s[2] for s in L["screws_lid"]]}
    top = L["z"]["top"]
    for (x, y, r) in L["screws_lid"]:
        heads[f"screw_head_{r}"] = cyl(x, y, top, top + P.SCREW_HEAD_K, P.SCREW_HEAD_D)
    for i, (x, y) in enumerate(L["corners"]):
        heads[f"screw_head_corner{i}"] = cyl(x, y, top, top + P.SCREW_HEAD_K, P.SCREW_HEAD_D)
    batt = box(*L["battery"])
    for k, v in prox.items():
        v.label = f"proxy_{k}"
    panel.label, fpc.label, batt.label = "epaper_GDEY029T94", "epaper_fpc", "battery_503450_assumed"
    for k, v in heads.items():
        v.label = k
    step.label = "board_esp32s3_epaper"
    asm = Compound(children=[base, lid, step, panel, fpc, batt, rod, *prox.values(), *heads.values()], label="enclosure_assembly")
    export_step(asm, OUT / "enclosure_assembly.step")
    if not os.environ.get("ENCL_PARAMS"):   # break-test builds skip the 3MF; its mesher rejects some broken geometry
        mesher = Mesher()
        mesher.add_shape([base, lid], linear_deflection=0.01, angular_deflection=0.1)
        mesher.write(str(OUT / "enclosure.3mf"))
    # solids the verifier needs that are not printed parts
    extra = {"panel": panel, "fpc": fpc, "battery": batt, "light_pipe": rod, "base_walls": base_walls, "lid_walls": lid_walls,
             **{f"proxy_{k}": v for k, v in prox.items()}, **heads, **{f"mating_{k}": v for k, v in mating(L).items()}}
    export_step(Compound(children=[v for v in extra.values()]), OUT / "check_solids.step")
    (OUT / "check_solids.json").write_text(json.dumps(list(extra.keys())))
    (OUT / "layout.json").write_text(json.dumps(L, indent=1, default=list))
    print("base vol", round(base.volume, 1), "lid vol", round(lid.volume, 1))
    print("outer bbox", (base + lid).bounding_box())


if __name__ == "__main__":
    main()
