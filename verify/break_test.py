"""Each case breaks the design on purpose; verify.py must then FAIL the named check.
.venv-b3d python verify/break_test.py"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
CASES = [
    ("WALL 1.4", {"WALL": 1.4}, "wall >= 1.6"),
    ("USB pocket 0.5 mm smaller than the overmold", {"USB_POCKET_CLR": -0.25}, "mating_usb_overmold"),
    ("FPC loop tighter, panel 1 mm into the wall", {"FPC_LOOP_GAP": 0.5, "CLR_PANEL": -1.0}, "no interference panel"),
    ("board clearance 0.2", {"CLR_BOARD": 0.2}, "board to side walls"),
    ("insert hole 5.0 deep", {"INSERT_HOLE_DEPTH": 5.0}, "deep >= 6.7"),
    ("insert hole 3.6", {"INSERT_HOLE_D": 3.6}, "insert@"),
]
results = []
for name, over, expect in CASES:
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, ENCL_OUT=td, ENCL_REPORT=td, ENCL_PARAMS=json.dumps(over))
        subprocess.run([PY, str(ROOT / "enclosure/build.py")], env=env, check=True, capture_output=True)
        r = subprocess.run([PY, str(ROOT / "verify/verify.py"), "--no-slice"], env=env, capture_output=True, text=True)
        failed = json.loads((Path(td) / "report.json").read_text())["checks_failed"]
    caught = r.returncode != 0 and any(expect in f for f in failed)
    results.append({"case": name, "override": over, "caught": caught, "failed_checks": failed})
    print(("CAUGHT " if caught else "MISSED ") + name, failed[:4])
(ROOT / "verify" / "break_test.json").write_text(json.dumps(results, indent=1))
sys.exit(0 if all(r["caught"] for r in results) else 1)
