import pcbnew, json, sys
b = pcbnew.LoadBoard(sys.argv[1]); mm = pcbnew.ToMM; out = {}
for f in b.GetFootprints():
    if f.GetReference() not in ("J1","J2","J3","J4","SW1","SW2","U4"): continue
    xs, ys = [], []
    for g in f.GraphicalItems():
        if g.GetLayerName() == "F.Fab" and g.GetClass() != "PCB_TEXT" and hasattr(g, "GetStart"):
            for p in (g.GetStart(), g.GetEnd()): xs.append(mm(p.x)); ys.append(mm(p.y))
    pads = [[p.GetNumber(), round(mm(p.GetPosition().x),3), round(mm(p.GetPosition().y),3), round(mm(p.GetSize().x),2), round(mm(p.GetSize().y),2)] for p in f.Pads()]
    out[f.GetReference()] = {"fab_bbox_kicad": [min(xs), min(ys), max(xs), max(ys)] if xs else None, "pos": [mm(f.GetPosition().x), mm(f.GetPosition().y)], "rot": f.GetOrientationDegrees(), "pads": pads}
json.dump(out, open(sys.argv[2], "w"), indent=1)
for k, v in out.items(): print(k, v["pos"], v["rot"], v["fab_bbox_kicad"], len(v["pads"]))
