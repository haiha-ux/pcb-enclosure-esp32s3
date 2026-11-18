"""DXF -> PDF at true 1:1 on A3.  "C:/Program Files/Python311/python.exe" drawing/to_pdf.py"""
from pathlib import Path
import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext, layout, pymupdf, config

D = Path(__file__).resolve().parent
for n in ("lid", "base"):
    doc = ezdxf.readfile(D / f"{n}.dxf")
    be = pymupdf.PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.BLACK, lineweight_scaling=0.5)
    Frontend(RenderContext(doc), be, config=cfg).draw_layout(doc.modelspace())
    page = layout.Page(420, 297, layout.Units.mm)
    (D / f"{n}.pdf").write_bytes(be.get_pdf_bytes(page, settings=layout.Settings(scale=1, fit_page=False)))
    be2 = pymupdf.PyMuPdfBackend()
    Frontend(RenderContext(doc), be2, config=cfg).draw_layout(doc.modelspace())
    (D / f"{n}.png").write_bytes(be2.get_pixmap_bytes(page, fmt="png", settings=layout.Settings(scale=1, fit_page=False), dpi=110))
    print("wrote", D / f"{n}.pdf")
