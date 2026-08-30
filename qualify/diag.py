"""Detector diagnostics on a subset: which features separate labelled boxes from defect-free images,
and the hit rate at several false-call budgets."""
import glob, os, sys
import numpy as np
sys.path.insert(0, "qualify")
from analysis import ROOT, SENSORS, TEST_BUILD, load_gray, window_features, boxes_for, fit_logreg, predict
rng = np.random.default_rng(1)
for sensor, cfg in SENSORS.items():
    imgs = sorted(glob.glob(f"{ROOT}/{sensor}/*.jpg"))
    test = [p for p in imgs if os.path.basename(p).split("_")[0] == TEST_BUILD]
    train = [p for p in imgs if os.path.basename(p).split("_")[0] != TEST_BUILD]
    rng.shuffle(test); rng.shuffle(train)
    d = cfg["down"]
    def feats(paths, n):
        pos, neg, boxmax, goodmax = [], [], [], []
        for p in paths[:n]:
            name = os.path.basename(p)[:-4]; img = load_gray(p, d); F, Y, X = window_features(img, cfg); boxes = boxes_for(sensor, name)
            inside = np.zeros(Y.shape, bool); near = np.zeros(Y.shape, bool)
            for x0, y0, x1, y1 in boxes:
                inside |= (X*d >= x0) & (X*d <= x1) & (Y*d >= y0) & (Y*d <= y1)
                m = cfg["win"]*d; near |= (X*d >= x0-m) & (X*d <= x1+m) & (Y*d >= y0-m) & (Y*d <= y1+m)
            pos.append(F[inside]); neg.append(F[~near][rng.choice((~near).sum(), min(300, (~near).sum()), replace=False)])
            if boxes:
                for x0, y0, x1, y1 in boxes:
                    sel = (X*d >= x0-cfg["win"]*d/2) & (X*d <= x1+cfg["win"]*d/2) & (Y*d >= y0-cfg["win"]*d/2) & (Y*d <= y1+cfg["win"]*d/2)
                    if sel.any(): boxmax.append(F[sel].reshape(-1, 4).max(0))
            else:
                goodmax.append(F.reshape(-1, 4).max(0))
        return np.vstack(pos), np.vstack(neg), np.array(boxmax), np.array(goodmax)
    ptr, ntr, _, _ = feats(train, 250)
    pte, nte, bm, gm = feats(test, 300)
    print(sensor, "train pos/neg", len(ptr), len(ntr), "test boxes", len(bm), "good imgs", len(gm))
    # per-feature AUC: box max vs good-image max
    for i, nm in enumerate(["mean_hp", "max_hp", "std", "rel"]):
        a, b = bm[:, i], gm[:, i]
        auc = (a[:, None] > b[None, :]).mean()
        print(f"   {nm:8s} box-max median {np.median(a):8.2f}  good-image-max median {np.median(b):8.2f}  AUC(box>goodmax) {auc:.2f}")
    model = fit_logreg(np.vstack([ptr, ntr]), np.concatenate([np.ones(len(ptr)), np.zeros(len(ntr))]))
    sb = predict(model, bm); sg = predict(model, gm)
    print("   model: box-max score median", np.median(sb).round(3), "good-image-max median", np.median(sg).round(3), "AUC", (sb[:, None] > sg[None, :]).mean().round(2))
    for fc in (0.05, 0.25, 1, 2, 5):
        # false calls per image approximated by the fraction of good images whose max exceeds thr times windows... use the image-max quantile
        thr = np.quantile(sg, 1 - min(0.99, fc / 1.0)) if fc < 1 else np.quantile(sg, 0.0)
        print(f"   share of good images with any call {fc}: hit rate {(sb > thr).mean():.3f} at thr {thr:.3f}")
