"""Assemble deliver/ and spec.json from the built and verified files (run after verify).
.venv-b3d python package.py"""
import json
import shutil
import sys
from pathlib import Path

from build123d import Compound, export_step, import_step

ROOT = Path(__file__).resolve().parent
OUT, D = ROOT / "out", ROOT / "deliver"
sys.path.insert(0, str(ROOT / "enclosure"))
import params as P  # noqa: E402


def main():
    D.mkdir(exist_ok=True)
    for f in ("base.step", "lid.step", "base.stl", "lid.stl", "enclosure.3mf"):
        shutil.copy2(OUT / f, D / f)
    base, lid = import_step(OUT / "base.step"), import_step(OUT / "lid.step")
    board = import_step(ROOT / "build" / "board.step")
    base.label, lid.label, board.label = "base", "lid", "board_esp32s3_epaper"
    export_step(Compound(children=[base, lid, board], label="assembly"), D / "assembly.step")
    shutil.copy2(OUT / "enclosure_assembly.step", D / "assembly_full.step")
    for sub in ("drawing", "render"):
        (D / sub).mkdir(exist_ok=True)
        for f in (ROOT / sub).glob("*.p*"):
            if f.suffix in (".pdf", ".png"):
                shutil.copy2(f, D / sub / f.name)
    for f in (ROOT / "drawing").glob("*.dxf"):
        shutil.copy2(f, D / "drawing" / f.name)
    R = json.loads((ROOT / "verify" / "report.json").read_text())
    L = json.loads((OUT / "layout.json").read_text())
    s = []

    def add(**kw):
        s.append(kw)
    for n in ("base", "lid"):
        for ax in ("dx", "dy", "dz"):
            add(name=f"{n} bbox {ax}", kind="bbox_dim", a=f"{n}.step#0", axis=ax[1], target=round(R[f"{n}.step#0.bbox_{ax}"], 3), tol=0.05, op="==")
        add(name=f"{n} min wall", kind="min_wall", a=f"{n}.stl", target=1.6, tol=0.01, op=">=")
    add(name="heat-set insert holes (ruthex RX-M3x5.7)", kind="hole_diameter", a="base.step#0", target=P.INSERT_HOLE_D, tol=0.02, op="==",
        count=len(L["holes"]) + len(L["corners"]), depth_min=P.INSERT_HOLE_DEPTH)
    add(name="M3 clearance holes in lid", kind="hole_diameter", a="lid.step#0", target=P.CLR_HOLE_M3, tol=0.02, op="==",
        count=len(L["screws_lid"]) + len(L["corners"]))
    add(name="RESET pin hole", kind="hole_diameter", a="lid.step#0", target=P.RESET_PIN_D, tol=0.02, op="==", count=1,
        at=[L["openings"]["reset"]["x"], L["openings"]["reset"]["y"]])
    add(name="CHG LED light-pipe bore (2 mm PMMA rod)", kind="hole_diameter", a="lid.step#0", target=P.LED_BORE_D, tol=0.02, op="==", count=1,
        at=[L["openings"]["led"]["x"], L["openings"]["led"]["y"]])
    for b in ("base.step#0", "lid.step#0"):
        add(name=f"board does not penetrate {b}", kind="min_distance", a="board", b=b, target=0.0, tol=0.0, op=">=",
            note="contact is by design: board sits on base standoffs, lid bosses clamp it at H1/H3")
    add(name="board edge to inner side walls", kind="min_distance", a="board PCB substrate", b="side walls only (no bosses)",
        target=P.CLR_BOARD, tol=0.0, op=">=", measured=R["pair.board|walls.min_clearance"])
    va = L["va"]
    add(name="display window = GDEY029T94 viewing area", kind="contains", a="lid.step#0 window void at z plate_bot+0.1..0.5",
        target=[round(v, 3) for v in va], tol=0.1, op="==", axis="xy rectangle [x0, y0, x1, y1]")
    u = L["openings"]["usb"]
    add(name="USB-C pocket centre x = J1 F.Fab centre", kind="distance", a="lid USB pocket centre x", b="J1 F.Fab centre x",
        target=round(u["x"], 3), tol=0.1, op="==", size=[u["w"], "open from parting line to z", round(u["z"] + u["h"] / 2, 3)])
    add(name="USB-C overmold can reach the receptacle mouth", kind="distance", a="first lid material in the 12.85x7.0 overmold footprint",
        b="J1 mouth (F.Fab front edge)", target=P.USB_MOUTH_GAP_MAX, op="<=", measured=R["usb.overmold_stop_to_mouth"],
        note=f"overmold face to mating datum = {P.USB_RECEPTACLE_DEPTH} + gap <= {P.USB_OVERMOLD_DATUM_MAX}")
    q = L["openings"]["qwiic"]
    add(name="Qwiic opening centre (y, z) = J3 STEP body", kind="distance", a="lid Qwiic opening centre", b="J3 3D body centre",
        target=[round(q["y"], 3), round(q["z"], 3)], tol=0.1, op="==", size=[q["w"], q["h"]])
    add(name="USB-C plug shell envelope 8.4 x 2.6 clears lid", kind="min_distance", a="box 8.4x2.6 on J1 axis", b="lid.step#0",
        target=0.0, tol=0.0, op=">", measured=R["usb.plug_shell_to_lid"])
    add(name="reset tube clears the button at rest", kind="distance", a="tube bottom", b="SW1 top (1.5 mm)", target=0.0, op=">",
        measured=R["reset.tube_bottom_to_button_top"])
    for it in s:
        if "a" in it:
            it.setdefault("id", it["a"])
    (ROOT / "spec.json").write_text(json.dumps(s, indent=1))
    shutil.copy2(ROOT / "verify" / "report.json", D.parent / "report.json")
    print("deliver/ and spec.json written:", len(s), "spec items")


if __name__ == "__main__":
    main()
