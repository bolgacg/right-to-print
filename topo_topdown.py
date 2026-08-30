"""Rerun only the top-down case with more iterations and a gentler filter, to see whether
the optimiser can find a usable hanging design; writes data/topo_topdown.json."""
import json, time
import topo
topo.MAXIT = 400
S = topo.setup()
t0 = time.time()
xP, c, it, hist = topo.optimise(S, "top-down")
json.dump({"compliance": c, "iterations": it, "volume": float(xP.mean()), "unsupported": {o: topo.unsupported_fraction(xP, o) for o in ["bottom-up", "left-to-right", "top-down", "right-to-left"]}, "field": xP.round(2).tolist(), "history": [round(h, 4) for h in hist]}, open("data/topo_topdown.json", "w"))
print(f"top-down 400 iters: compliance {c:.2f} in {time.time()-t0:.0f}s")
