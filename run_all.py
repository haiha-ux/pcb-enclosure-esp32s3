"""One command: board data -> enclosure -> drawings -> renders -> verify -> break test -> deliver/.
<python with build123d 0.13> run_all.py
Needs: KiCad 10 (kicad-cli + its python), Python 3.11 with ezdxf + PyMuPDF for the PDFs, OrcaSlicer 2.5.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
KICAD = Path(r"C:\Program Files\KiCad\10.0\bin")
PY311 = Path(r"C:\Program Files\Python311\python.exe")
BOARD_REPO = "https://github.com/haiha-ux/pcb-esp32s3-epaper"
BOARD_COMMIT = "e416b79"


def run(*cmd, **kw):
    print(">", " ".join(map(str, cmd)))
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT, **kw)


def main():
    src = ROOT / "input_board"
    if not src.exists():
        run("git", "clone", "-q", BOARD_REPO, src)
    run("git", "-C", src, "checkout", "-q", BOARD_COMMIT)
    pcb = src / "esp32s3_epaper.kicad_pcb"
    (ROOT / "build").mkdir(exist_ok=True)
    run(KICAD / "python.exe", "tools/dump_board.py", pcb, "build/board.json")
    run(KICAD / "python.exe", "tools/fab_outlines.py", pcb, "build/fab_outlines.json")
    run(KICAD / "kicad-cli.exe", "pcb", "export", "step", "--subst-models", "--include-tracks", "-f", "-o", "build/board.step", pcb)
    run(PY, "enclosure/build.py")
    run(PY, "drawing/drawing.py")
    run(PY311, "drawing/to_pdf.py")
    run(PY, "enclosure/render.py")
    run(PY, "verify/verify.py")
    run(PY, "verify/break_test.py")
    run(PY, "package.py")


if __name__ == "__main__":
    main()
