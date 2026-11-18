"""Checks every claim about the enclosure from the exported files and writes verify/report.json.

.venv-b3d python verify/verify.py      (run after enclosure/build.py)
Exit code 1 if any check fails. Every check asserts a number; nothing is judged from a picture.
"""
import json
import os
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import trimesh
from build123d import Box, Compound, Pos, Align, import_step, import_stl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "enclosure"))
import params as P  # noqa: E402

OUT = Path(os.environ.get("ENCL_OUT", ROOT / "out"))
SLICE = "--no-slice" not in sys.argv
REPORT = Path(os.environ.get("ENCL_REPORT", ROOT / "verify"))
DELIVER = ROOT / "deliver"
PRINT = ROOT / "print"
ORCA = Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe")
KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
FREECADCMD = Path.home() / "AppData/Local/Programs/FreeCAD 1.1/bin/freecadcmd.exe"
TOL_ALIGN = 0.1
A0 = (Align.MIN, Align.MIN, Align.MIN)

report = {}
checks = []


def check(name, ok, **kw):
    checks.append({"name": name, "pass": bool(ok), **kw})
    print(("PASS " if ok else "FAIL ") + name, kw)


def box(x0, y0, z0, x1, y1, z1):
    return Pos(x0, y0, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=A0)


def bb(s):
    b = s.bounding_box()
    return np.array([b.min.X, b.min.Y, b.min.Z]), np.array([b.max.X, b.max.Y, b.max.Z])


def void_bbox(part, region):
    """Bounding box of the empty space of `part` inside `region` (a box): measures openings from the solid itself."""
    v = box(*region) - part
    if v is None or v.volume < 1e-9:
        return None
    return bb(v)


def common_volume(a, b):
    lo1, hi1 = bb(a)
    lo2, hi2 = bb(b)
    if np.any(hi1 < lo2 - 1e-6) or np.any(hi2 < lo1 - 1e-6):
        return 0.0
    c = a & b
    return 0.0 if c is None else sum(s.volume for s in c.solids())


def min_wall(stl_path):
    """Local wall thickness: ray from every triangle centroid inward along -normal to the first hit."""
    m = trimesh.load(stl_path)
    # sample densely: split every triangle until edges are <= 0.5 mm (centroids alone missed the window lip in REV2)
    v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=0.5)
    m = trimesh.Trimesh(v, f, process=False)
    eps = 1e-4
    origins = m.triangles_center - m.face_normals * eps
    dirs = -m.face_normals
    loc, idx_ray, _ = m.ray.intersects_location(origins, dirs, multiple_hits=False)
    d = np.full(len(origins), np.inf)
    d[idx_ray] = np.linalg.norm(loc - origins[idx_ray], axis=1)
    finite = d[np.isfinite(d)]
    i = int(np.argmin(d))
    return float(finite.min()), float(np.percentile(finite, 1)), m.triangles_center[i].tolist(), int(np.isinf(d).sum())


def min_air_gap(stl_path):
    """Narrowest slot inside one part: ray from every face outward to the next face of the same part."""
    m = trimesh.load(stl_path)
    eps = 1e-4
    origins = m.triangles_center + m.face_normals * eps
    loc, idx_ray, idx_tri = m.ray.intersects_location(origins, m.face_normals, multiple_hits=False)
    d = np.linalg.norm(loc - origins[idx_ray], axis=1)
    # a slot has facing walls; a ray that hits a face at a steep angle is a wedge-shaped corner, not a slot
    facing = np.einsum("ij,ij->i", m.face_normals[idx_ray], m.face_normals[idx_tri]) < -0.9
    d, idx_ray = d[facing], idx_ray[facing]
    i = int(np.argmin(d))
    return float(d[i]), m.triangles_center[idx_ray[i]].tolist()


def overhangs(stl_path, flip):
    m = trimesh.load(stl_path)
    if flip:
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
    zmin = m.bounds[0][2]
    nz = m.face_normals[:, 2]
    on_bed = np.all(np.abs(m.triangles[:, :, 2] - zmin) < 1e-3, axis=1)
    over = (nz < -math.cos(math.radians(45))) & ~on_bed
    return float(m.area_faces[over].sum()), m.triangles_center[over]


def versions():
    import build123d, OCP, ezdxf, trimesh as tm
    v = {"python": platform.python_version(), "build123d": build123d.__version__, "OCP": getattr(OCP, "__version__", "8.0.1.1 (cadquery-ocp-novtk)"),
         "ezdxf": ezdxf.__version__, "trimesh": tm.__version__}
    v["kicad-cli"] = subprocess.run([str(KICAD_CLI), "version"], capture_output=True, text=True).stdout.strip()
    try:
        r = subprocess.run([str(FREECADCMD), "--version"], capture_output=True, text=True, timeout=60)
        v["FreeCAD"] = (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception as e:  # FreeCAD is not used to build; recorded for completeness
        v["FreeCAD"] = f"not run: {e}"
    v["OrcaSlicer"] = "2.5.0 (statistics generator field)"
    return v


def slice_parts():
    from build123d import import_stl  # noqa
    cfg = ROOT / "verify" / "orca"
    PRINT.mkdir(exist_ok=True)
    res = {}
    for name, flip in (("base", False), ("lid", True)):
        m = trimesh.load(OUT / f"{name}.stl")
        if flip:
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0]))
        m.apply_translation(-m.bounds[0] + [10, 10, 0])
        f = PRINT / f"{name}_print.stl"
        m.export(f)
        od = PRINT / f"slice_{name}"
        od.mkdir(exist_ok=True)
        r = subprocess.run([str(ORCA), str(f), "--load-settings", f"{cfg/'machine.json'};{cfg/'process.json'}",
                            "--load-filaments", str(cfg / "filament.json"), "--slice", "0", "--export-statistics",
                            "--outputdir", str(od)], capture_output=True, text=True, timeout=900)
        log = (r.stdout + r.stderr)
        (od / "orca.log").write_text(log, encoding="utf-8")
        stats = json.loads((od / "plate_1.statistics.json").read_text()) if (od / "plate_1.statistics.json").exists() else None
        warn = [ln for ln in log.splitlines() if any(w in ln.lower() for w in ("warning", "error", "floating", "empty layer"))]
        res[name] = {"rc": r.returncode, "time_s": stats["summary"]["time"] if stats else None,
                     "weight_g": stats["summary"]["weight"] if stats else None, "warnings": warn[:20]}
    return res


def main():
    meta = json.loads((OUT / "build_meta.json").read_text())
    L = json.loads((OUT / "layout.json").read_text())
    parts = {}
    # 1 validity + STEP round trip + STL watertight
    for n in ("base", "lid"):
        s = import_step(OUT / f"{n}.step")
        sols = s.solids()
        lo, hi = bb(s)
        vol = s.volume
        parts[n] = s
        m0 = meta[n]
        dv = abs(vol - m0["volume"]) / m0["volume"]
        db = max(np.max(np.abs(lo - m0["bbox_min"])), np.max(np.abs(hi - m0["bbox_max"]))) / max(hi - lo)
        k = f"{n}.step#0"
        report.update({f"{k}.volume": vol, f"{k}.bbox_dx": hi[0] - lo[0], f"{k}.bbox_dy": hi[1] - lo[1],
                       f"{k}.bbox_dz": hi[2] - lo[2], f"{k}.is_valid": s.is_valid, f"{k}.solid_count": len(sols),
                       f"{k}.reimport_rel_volume_err": dv, f"{k}.reimport_rel_bbox_err": db})
        check(f"{n}: one valid solid, volume > 0", len(sols) == 1 and s.is_valid and vol > 0, solids=len(sols), volume=vol)
        check(f"{n}: STEP re-import matches build (rel <= 1e-6)", dv <= 1e-6 and db <= 1e-6, rel_volume=dv, rel_bbox=db)
        m = trimesh.load(OUT / f"{n}.stl")
        report[f"{n}.stl.watertight"] = bool(m.is_watertight)
        report[f"{n}.stl.volume"] = float(m.volume)
        check(f"{n}: STL watertight, volume within 0.5 % of STEP", m.is_watertight and m.is_volume and abs(m.volume - vol) / vol < 5e-3,
              stl_volume=float(m.volume))

    # 2 interference and clearances
    board = import_step(ROOT / "build" / "board.step")
    names = json.loads((OUT / "check_solids.json").read_text())
    extra = dict(zip(names, import_step(OUT / "check_solids.step").solids()))
    if len(extra) != len(names):
        raise SystemExit("check_solids.step solid count changed")
    board_pcb = [c for c in board.children if c.label == "esp32s3_epaper_PCB"][0]
    base, lid = parts["base"], parts["lid"]
    others = {"board": board, "panel": extra["panel"], "fpc": extra["fpc"], "battery": extra["battery"], "light_pipe": extra["light_pipe"]}
    others.update({k: v for k, v in extra.items() if k.startswith(("proxy_", "screw_head_", "mating_"))})
    worst = 0.0
    for pn, p in (("base.step#0", base), ("lid.step#0", lid)):
        for on, o in others.items():
            solids = o.solids() if on == "board" else [o]
            v = sum(common_volume(p, s) for s in solids)
            d = p.distance_to(o)
            report[f"pair.{on}|{pn}.min_clearance"] = d
            report[f"pair.{on}|{pn}.common_volume"] = v
            worst = max(worst, v)
            check(f"no interference {on} | {pn}", v < 1e-3, common_volume=v, min_clearance=d)
    v = common_volume(base, lid)
    report["pair.base.step#0|lid.step#0.common_volume"] = v
    report["pair.base.step#0|lid.step#0.min_clearance"] = base.distance_to(lid)
    check("no interference base | lid", v < 1e-3, common_volume=v)
    # non-enclosure pairs that must not collide either
    inner = [("panel", "board"), ("panel", "proxy_J2_JST-PH"), ("panel", "proxy_J4_FPC"), ("panel", "proxy_SW2_tact"),
             ("fpc", "board"), ("battery", "board"), ("light_pipe", "board"), ("light_pipe", "proxy_J2_JST-PH")] + [(h, "panel") for h in extra if h.startswith("screw_head_H")]
    for a, b_ in inner:
        A = extra[a]
        Bs = board.solids() if b_ == "board" else [extra[b_]]
        v = sum(common_volume(A, s) for s in Bs)
        d = A.distance_to(board if b_ == "board" else extra[b_])
        report[f"pair.{a}|{b_}.common_volume"] = v
        report[f"pair.{a}|{b_}.min_clearance"] = d
        check(f"no interference {a} | {b_}", v < 1e-3, common_volume=v, min_clearance=d)
    blo, bhi = bb(board)
    report.update({"board.step#0.bbox_dx": bhi[0] - blo[0], "board.step#0.bbox_dy": bhi[1] - blo[1], "board.step#0.bbox_dz": bhi[2] - blo[2],
                   "board.step#0.volume": board.volume, "board.step#0.solid_count": len(board.solids()),
                   "pair.base.step#0|board.step#0.min_clearance": base.distance_to(board),
                   "pair.lid.step#0|board.step#0.min_clearance": lid.distance_to(board)})
    walls = extra["base_walls"].fuse(extra["lid_walls"])
    dw = board_pcb.distance_to(walls)
    report["pair.board|walls.min_clearance"] = dw
    check(f"board to side walls >= CLR_BOARD {P.CLR_BOARD}", dw >= P.CLR_BOARD - 1e-6, min_clearance=dw)

    # 3 openings measured from the lid, compared with KiCad positions
    I, z, bd = L["interior"], L["z"], L["board"]
    jx = (L["fab"]["J1"][0] + L["fab"]["J1"][2]) / 2
    jz = bd["zt"] + P.H_USBC / 2
    vb = void_bbox(lid, (jx - 12, I["y0"] - 1.2, z["split"] + 0.1, jx + 12, I["y0"] - 0.1, z["top"] - 0.1))
    c = (vb[0] + vb[1]) / 2
    top_need = jz + P.USB_OVERMOLD[1] / 2
    report.update({"usb.pocket_cx": c[0], "usb.pocket_w": vb[1][0] - vb[0][0], "usb.pocket_top_z": vb[1][2],
                   "usb.connector_cx": jx, "usb.connector_cz": jz})
    check("USB-C pocket centred on J1 (+-0.1) and above the overmold top", abs(c[0] - jx) <= TOL_ALIGN and vb[1][2] > top_need,
          dx=c[0] - jx, pocket_top=vb[1][2], overmold_top=top_need)
    # how close can the overmold get to the receptacle mouth? first obstruction in its footprint
    mouth = L["fab"]["J1"][1]
    ow, oh = P.USB_OVERMOLD
    probe = box(jx - ow / 2, mouth - 40, jz - oh / 2, jx + ow / 2, mouth - 1e-3, jz + oh / 2)
    hit = probe & lid
    stop_lid = max((s_.bounding_box().max.Y for s_ in hit.solids()), default=None) if hit is not None else None
    stop = max(v for v in (stop_lid, bd["y0"]) if v is not None)     # the board edge stops it anyway
    gap = mouth - stop
    report.update({"usb.overmold_stop_to_mouth": gap, "usb.overmold_stop_by": "lid" if stop == stop_lid else "board edge",
                   "usb.overmold_face_to_mating_datum": P.USB_RECEPTACLE_DEPTH + gap})
    check(f"USB-C overmold reaches within {P.USB_MOUTH_GAP_MAX} of the mouth (datum <= {P.USB_OVERMOLD_DATUM_MAX})",
          gap <= P.USB_MOUTH_GAP_MAX and P.USB_RECEPTACLE_DEPTH + gap <= P.USB_OVERMOLD_DATUM_MAX, gap=gap,
          datum=P.USB_RECEPTACLE_DEPTH + gap, stopped_by=report["usb.overmold_stop_by"])
    dsh = lid.distance_to(extra["mating_usb_shell"])
    dom = lid.distance_to(extra["mating_usb_overmold"])
    report["usb.plug_shell_to_lid"], report["usb.plug_overmold_to_lid"] = dsh, dom
    check("seated USB-C plug (shell 8.4x2.6, overmold 12.85x7.0) clears the lid", dsh > 0 and dom > 0, shell=dsh, overmold=dom)
    j3 = L["J3_box"]
    qy, qz = (j3[1] + j3[4]) / 2, (j3[2] + j3[5]) / 2
    vb = void_bbox(lid, (I["x1"] + 0.1, qy - 10, z["split"] + 0.1, I["x1"] + P.WALL - 0.1, qy + 10, z["plate_bot"] - 0.1))
    c = (vb[0] + vb[1]) / 2
    report.update({"qwiic.opening_cy": c[1], "qwiic.opening_cz": c[2], "qwiic.connector_cy": qy, "qwiic.connector_cz": qz})
    check("Qwiic opening centred on J3 (+-0.1)", abs(c[1] - qy) <= TOL_ALIGN and abs(c[2] - qz) <= TOL_ALIGN, dy=c[1] - qy, dz=c[2] - qz)
    dq = lid.distance_to(extra["mating_shr04_plug"])
    report["qwiic.plug_to_lid"] = dq
    check("SHR-04V plug clears the lid", dq > 0, clearance=dq)
    for key, ref, dnom in (("reset", "SW1", P.RESET_PIN_D), ("led", "D2", P.LED_BORE_D)):
        x, y = L["refs"][ref]
        vb = void_bbox(lid, (x - 4, y - 4, z["plate_bot"] + 0.1, x + 4, y + 4, z["top"] - 0.1))
        c = (vb[0] + vb[1]) / 2
        dia = vb[1][0] - vb[0][0]
        report.update({f"{key}.hole_cx": c[0], f"{key}.hole_cy": c[1], f"{key}.hole_d": dia})
        check(f"{key} hole over {ref} (+-0.1), d = {dnom}", abs(c[0] - x) <= TOL_ALIGN and abs(c[1] - y) <= TOL_ALIGN and abs(dia - dnom) < 0.05,
              dx=c[0] - x, dy=c[1] - y, d=dia)
    btn_top = bd["zt"] + P.H_TACT
    report["reset.tube_bottom_to_button_top"] = L["openings"]["reset"]["tube_bottom"] - btn_top
    report["reset.pin_depth_from_lid_top_to_button_top"] = z["top"] - btn_top
    led = L["openings"]["led"]
    report["led.pipe_bottom_to_led_top"] = led["pipe_bottom"] - L["led_top"]
    report["led.light_pipe_length"] = z["top"] - led["pipe_bottom"]
    check("light-pipe rod (cut flush with the lid top) stops above the LED", report["led.pipe_bottom_to_led_top"] > 0, gap=report["led.pipe_bottom_to_led_top"])
    br = box(I["x1"] - 12, I["y0"] - 0.1, z["split"] - P.LIP_H, I["x1"], I["y0"] + 12, z["split"])
    lipv = sum(s_.volume for s_ in (br & lid).solids()) if (br & lid) is not None else 0.0
    report["lid.lip_volume_bottom_right_corner"] = lipv
    check("lid has a locating lip at the bottom-right corner", lipv > 1.0, volume=lipv)
    check("reset tube does not touch the button at rest", report["reset.tube_bottom_to_button_top"] > 0,
          gap=report["reset.tube_bottom_to_button_top"])
    va = L["va"]
    vb = void_bbox(lid, (va[0] - 1.5, va[1] - 1.5, z["plate_bot"] + 0.1, va[2] + 1.5, va[3] + 1.5, z["plate_bot"] + 0.5))
    err = max(abs(vb[0][0] - va[0]), abs(vb[0][1] - va[1]), abs(vb[1][0] - va[2]), abs(vb[1][1] - va[3]))
    report.update({"window.x0": vb[0][0], "window.y0": vb[0][1], "window.x1": vb[1][0], "window.y1": vb[1][1], "window.max_edge_err": err})
    check("display window = panel viewing area (+-0.1)", err <= TOL_ALIGN, max_edge_err=err)

    # 4 wall thickness, overhangs, slicing
    for n, flip in (("base", False), ("lid", True)):
        mw, p1, where, miss = min_wall(OUT / f"{n}.stl")
        report[f"{n}.stl.min_wall"], report[f"{n}.stl.wall_p1"], report[f"{n}.stl.min_wall_at"] = mw, p1, where
        report[f"{n}.step#0.min_wall"] = mw
        check(f"{n}: wall >= 1.6 everywhere (ray method)", mw >= 1.6 - 0.01 and miss == 0, min_wall=mw, at=where, rays_missed=miss)
        g, at = min_air_gap(OUT / f"{n}.stl")
        report[f"{n}.stl.min_slot"], report[f"{n}.stl.min_slot_at"] = g, at
        check(f"{n}: no slot narrower than 0.8 mm (two extrusion lines)", g >= 0.8, min_slot=g, at=at)
        area, centres = overhangs(OUT / f"{n}.stl", flip)
        report[f"{n}.print.overhang_gt45_area_mm2"] = area
        report[f"{n}.print.orientation"] = "lid upside down (top plate on the bed)" if flip else "as modelled (floor on the bed)"
    sl = slice_parts() if SLICE else {}
    for n, r in sl.items():
        report[f"{n}.slice.time_s"], report[f"{n}.slice.weight_g"], report[f"{n}.slice.warnings"] = r["time_s"], r["weight_g"], r["warnings"]
        check(f"{n}: OrcaSlicer slices with no error/warning", r["rc"] == 0 and r["time_s"] and not r["warnings"], **r)

    # 5 heat-set insert holes measured from the base
    holes = [tuple(h) for h in L["holes"]] + [tuple(c) for c in L["corners"]]
    tops = [bd["zb"]] * len(L["holes"]) + [z["corner_joint"]] * len(L["corners"])
    for (x, y), top in zip(holes, tops):
        vb = void_bbox(base, (x - 2.5, y - 2.5, z["floor_bot"] + 0.001, x + 2.5, y + 2.5, top - 0.05))
        d = vb[1][0] - vb[0][0]
        depth = top - vb[0][2]
        below = vb[0][2] - z["floor_bot"]
        k = f"insert@{x:.2f},{y:.2f}"
        report.update({f"{k}.d": d, f"{k}.depth": depth, f"{k}.material_below": below,
                       f"{k}.boss_wall": (P.BOSS_OD - d) / 2})
        check(f"{k}: hole {P.INSERT_HOLE_D} deep >= {P.INSERT_HOLE_DEPTH}, wall >= {P.INSERT_MIN_WALL}",
              abs(d - P.INSERT_HOLE_D) < 0.02 and depth >= P.INSERT_HOLE_DEPTH - 1e-3 and below >= 1.6 - 1e-3
              and (P.BOSS_OD - d) / 2 >= P.INSERT_MIN_WALL, d=d, depth=depth, below=below)
    report["insert.source"] = P.SOURCES["ruthex RX-M3x5.7"]

    # 6 informational: distances to the antenna area (Espressif HDG asks 15 mm of metal clearance)
    u4 = L["fab"]["U4"]
    ant = box(u4[0], u4[3] - 6.0, bd["zt"], u4[2], u4[3], bd["zt"] + 3.2)
    for k in ("battery", "panel", "screw_head_H1", "screw_head_H2"):
        report[f"antenna_area.distance_to_{k}"] = ant.distance_to(extra[k])

    report["tools"] = versions()
    report["checks_failed"] = [c["name"] for c in checks if not c["pass"]]
    report["checks_total"] = len(checks)
    (REPORT / "report.json").write_text(json.dumps(report, indent=1, default=float))
    (REPORT / "checks.json").write_text(json.dumps(checks, indent=1, default=float))
    print(f"\n{len(checks) - len(report['checks_failed'])}/{len(checks)} checks pass")
    sys.exit(1 if report["checks_failed"] else 0)


if __name__ == "__main__":
    main()
