"""Renders: iso assembly, exploded, top, and a section through USB-C + panel.
.venv-b3d python enclosure/render.py"""
import json, sys
from pathlib import Path
import numpy as np
import trimesh
import vtk
from build123d import import_step, export_stl, Plane, Keep, split

ROOT = Path(__file__).resolve().parents[1]
OUT, R = ROOT / "out", ROOT / "render"
R.mkdir(exist_ok=True)
TMP = OUT / "_mesh"; TMP.mkdir(exist_ok=True)


def meshes():
    asm = import_step(OUT / "enclosure_assembly.step")
    parts = []
    for c in asm.children:
        f = TMP / f"{c.label}.stl"
        export_stl(c, f, tolerance=0.05, angular_tolerance=0.3)
        parts.append((c.label, f))
    return parts


COL = {"base": (0.20, 0.22, 0.26), "lid": (0.55, 0.58, 0.62), "board_esp32s3_epaper": (0.05, 0.35, 0.15),
       "epaper_GDEY029T94": (0.86, 0.85, 0.78), "epaper_fpc": (0.85, 0.55, 0.15), "battery_503450_assumed": (0.3, 0.45, 0.7), "light_pipe_2mm_PMMA": (0.9, 0.3, 0.3)}


def actor(path, col, offset=(0, 0, 0), opacity=1.0, clip=None):
    r = vtk.vtkSTLReader(); r.SetFileName(str(path)); r.Update()
    src = r.GetOutputPort()
    t = vtk.vtkTransform(); t.Translate(*offset)
    tf = vtk.vtkTransformPolyDataFilter(); tf.SetInputConnection(src); tf.SetTransform(t)
    src = tf.GetOutputPort()
    if clip is not None:
        pl = vtk.vtkPlane(); pl.SetOrigin(*clip[0]); pl.SetNormal(*clip[1])
        cl = vtk.vtkClipPolyData(); cl.SetInputConnection(src); cl.SetClipFunction(pl); cl.Update()
        src = cl.GetOutputPort()
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(src)
    a = vtk.vtkActor(); a.SetMapper(m)
    a.GetProperty().SetColor(*col); a.GetProperty().SetOpacity(opacity)
    a.GetProperty().SetSpecular(0.2); a.GetProperty().SetDiffuse(0.75); a.GetProperty().SetAmbient(0.15)
    return a


def shot(actors, name, pos, focal, up=(0, 0, 1), par=False, scale=None):
    ren = vtk.vtkRenderer(); ren.GradientBackgroundOn(); ren.SetBackground(0.62, 0.66, 0.72); ren.SetBackground2(0.30, 0.33, 0.38)
    for a in actors: ren.AddActor(a)
    cam = ren.GetActiveCamera(); cam.SetPosition(*pos); cam.SetFocalPoint(*focal); cam.SetViewUp(*up)
    if par:
        cam.ParallelProjectionOn()
    ren.ResetCamera(); cam.Zoom(1.25)
    if scale: cam.SetParallelScale(scale)
    win = vtk.vtkRenderWindow(); win.SetOffScreenRendering(1); win.AddRenderer(ren); win.SetSize(1600, 1200)
    win.Render()
    w2i = vtk.vtkWindowToImageFilter(); w2i.SetInput(win); w2i.Update()
    wr = vtk.vtkPNGWriter(); wr.SetFileName(str(R / name)); wr.SetInputConnection(w2i.GetOutputPort()); wr.Write()
    print("wrote", R / name)


def section_plot(asm, x, title, yr, zr, path, col):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch
    from build123d import Face, Rectangle, Plane as Pl
    cut = Pl.YZ.offset(x) * Rectangle(400, 400)
    fig, ax = plt.subplots(figsize=(12, 8), dpi=130)
    order = sorted(asm.children, key=lambda c: c.label not in ("base", "lid"))
    for ch in order:
        for so in ch.solids():
            b = so.bounding_box()
            if not (b.min.X < x < b.max.X):
                continue
            sec = so & cut
            if sec is None:
                continue
            for f in sec.faces():
                verts, codes = [], []
                for w in [f.outer_wire(), *f.inner_wires()]:
                    pts = [(p.Y, p.Z) for e in w.order_edges() for p in e.positions([i / 16 for i in range(17)])]
                    a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
                    if (w is f.outer_wire()) != (a > 0):
                        pts = pts[::-1]
                    verts += pts + [pts[0]]
                    codes += [MPath.MOVETO] + [MPath.LINETO] * (len(pts) - 1) + [MPath.CLOSEPOLY]
                ax.add_patch(PathPatch(MPath(verts, codes), facecolor=col(ch.label), edgecolor="black", lw=0.5,
                                       hatch="///" if ch.label in ("base", "lid") else None))
    ax.set_xlim(*yr); ax.set_ylim(*zr); ax.set_aspect("equal")
    ax.set_xlabel("y (mm, KiCad STEP frame)"); ax.set_ylabel("z (mm)"); ax.set_title(title)
    ax.grid(True, lw=0.3, alpha=0.5)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def main():
    parts = meshes()
    L = json.loads((OUT / "layout.json").read_text())
    c = (33, -5, 0)

    def col(n):
        return COL.get(n, (0.6, 0.6, 0.6) if n.startswith(("proxy", "screw")) else (0.5, 0.5, 0.5))
    # 1 iso assembled
    shot([actor(f, col(n)) for n, f in parts if n != "battery_503450_assumed"], "1_iso.png", (150, -170, 140), c)
    # 2 exploded
    off = {"lid": (0, 0, 45), "epaper_GDEY029T94": (0, 0, 30), "epaper_fpc": (0, 0, 30)}
    shot([actor(f, col(n), off.get(n, (0, 0, 15 if n.startswith("screw_head_corner") or n in ("screw_head_H1", "screw_head_H3") else 0)))
          for n, f in parts], "2_exploded.png", (150, -170, 160), (33, -5, 15))
    # 3 top view of the lid with the panel visible through the window
    shot([actor(f, col(n)) for n, f in parts], "3_top.png", (33, -5, 200), c, up=(0, 1, 0), par=True)
    # 4/5 true cross-sections of every solid at x = const, drawn as filled faces (matplotlib)
    asm = import_step(OUT / "enclosure_assembly.step")
    for fname, x, title, yr, zr in (
            ("4_section_usb.png", L["openings"]["usb"]["x"], "Section A-A at USB-C axis (x = %.2f)", (-58, -30), (-10, 13)),
            ("5_section_fpc.png", (L["fpc"]["x0"] + L["fpc"]["x1"]) / 2, "Section B-B through the FPC loop (x = %.2f)", (-58, -30), (-10, 13))):
        section_plot(asm, x, title % x, yr, zr, R / fname, col)
        print("wrote", R / fname)

if __name__ == "__main__":
    main()
