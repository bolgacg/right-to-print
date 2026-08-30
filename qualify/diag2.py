import glob, os, sys
import numpy as np
sys.path.insert(0, "qualify")
from analysis import ROOT, SENSORS, TEST_BUILD, load_image, window_features, boxes_for, fit_logreg, predict
rng = np.random.default_rng(1)
sensor = "PB"; cfg = SENSORS[sensor]
imgs = sorted(glob.glob(f"{ROOT}/{sensor}/*.jpg")); rng.shuffle(imgs)
lab = [p for p in imgs if os.path.exists(f"{ROOT}/{sensor}_label/" + os.path.basename(p)[:-4] + ".xml")][:120]
unl = [p for p in imgs if not os.path.exists(f"{ROOT}/{sensor}_label/" + os.path.basename(p)[:-4] + ".xml")][:120]
wh, ww = cfg["win"]
boxmax, unlwin, boxlen = [], [], []
for p in lab:
    img = load_image(p, sensor); F, Y, X = window_features(img, cfg, sensor)
    for x0, y0, x1, y1 in boxes_for(sensor, os.path.basename(p)[:-4]):
        sel = (X >= x0 - ww/2) & (X <= x1 + ww/2) & (Y >= y0 - wh) & (Y <= y1 + wh)
        if sel.any(): boxmax.append(F[sel].reshape(-1, 4).max(0)); boxlen.append(x1 - x0)
for p in unl:
    img = load_image(p, sensor); F, Y, X = window_features(img, cfg, sensor); unlwin.append(F.reshape(-1, 4))
bm = np.array(boxmax); uw = np.vstack(unlwin); wpi = len(uw) / len(unl)
print("boxes", len(bm), "unlabelled windows", len(uw), "per image", round(wpi))
for i, nm in enumerate(["line max", "signed max", "contrast", "rowdev max"]):
    for fc in (0.25, 1, 3, 10):
        thr = np.quantile(uw[:, i], 1 - fc / wpi)
        print(f"  {nm:12s} false calls/img {fc:5}: hit rate {(bm[:, i] > thr).mean():.2f}   (box p50 {np.median(bm[:, i]):.2f}, unlabelled p50 {np.median(uw[:, i]):.2f}, p99.9 {np.quantile(uw[:, i], .999):.2f})")
long = np.array(boxlen) > 200
print("long boxes (>200 px) hit rate at 1 false call/img, line max:", (bm[long, 0] > np.quantile(uw[:, 0], 1 - 1 / wpi)).mean().round(2), "short:", (bm[~long, 0] > np.quantile(uw[:, 0], 1 - 1 / wpi)).mean().round(2))
