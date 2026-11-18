import pcbnew, json, sys
b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.ToMM
bb = b.GetBoardEdgesBoundingBox()
out = {"edge_bbox": [mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetWidth()), mm(bb.GetHeight())],
       "thickness": mm(b.GetDesignSettings().GetBoardThickness()), "edges": [], "fp": []}
for d in b.GetDrawings():
    if d.GetLayerName() == "Edge.Cuts":
        out["edges"].append([d.GetShapeStr(), mm(d.GetStart().x), mm(d.GetStart().y), mm(d.GetEnd().x), mm(d.GetEnd().y)])
for f in b.GetFootprints():
    fb = f.GetBoundingBox(False)
    out["fp"].append({"ref": f.GetReference(), "fpid": str(f.GetFPID().GetLibItemName()), "side": "B" if f.IsFlipped() else "F",
        "pos": [mm(f.GetPosition().x), mm(f.GetPosition().y)], "rot": f.GetOrientationDegrees(),
        "bbox": [mm(fb.GetX()), mm(fb.GetY()), mm(fb.GetWidth()), mm(fb.GetHeight())],
        "models": [m.m_Filename for m in f.Models()],
        "pads": [[p.GetNumber(), mm(p.GetPosition().x), mm(p.GetPosition().y), mm(p.GetDrillSize().x)] for p in f.Pads() if p.GetDrillSize().x > 0]})
json.dump(out, open(sys.argv[2], "w"), indent=1)
