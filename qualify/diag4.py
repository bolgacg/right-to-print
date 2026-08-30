import glob, os, sys
import numpy as np
from scipy import ndimage
sys.path.insert(0, "qualify")
from analysis import ROOT, SENSORS, load_image, boxes_for, grid
rng = np.random.default_rng(1)
sensor = "PB"; cfg = SENSORS[sensor]; wh, ww = cfg["win"]
imgs = sorted(glob.glob(f"{ROOT}/{sensor}/*.jpg")); rng.shuffle(imgs)
lab = [p for p in imgs if os.path.exists(f"{ROOT}/{sensor}_label/" + os.path.basename(p)[:-4] + ".xml")][:80]
ys, xs, vals = [], [], []
for p in lab:
    img = load_image(p, sensor); y0, y1, x0, x1 = cfg["roi"]
    hp = img - ndimage.uniform_filter1d(img, 21, axis=0); noise = np.median(np.abs(hp[y0:y1, x0:x1])) + 1e-3
    line = ndimage.maximum_filter(np.abs(ndimage.uniform_filter1d(hp / noise, 96, axis=1)), (wh, 1))
    Y, X = grid(img.shape, cfg); F = line[Y, X]
    near = np.zeros(Y.shape, bool)
    for bx0, by0, bx1, by1 in boxes_for(sensor, os.path.basename(p)[:-4]):
        near |= (X >= bx0 - 2*ww) & (X <= bx1 + 2*ww) & (Y >= by0 - 3*wh) & (Y <= by1 + 3*wh)
    m = ~near; ys.append(Y[m]); xs.append(X[m]); vals.append(F[m])
Y = np.concatenate(ys); X = np.concatenate(xs); V = np.concatenate(vals)
top = V > np.quantile(V, 0.999)
print("top 0.1% non-box responses: n", top.sum())
print(" y histogram (bins of 100 px):", np.histogram(Y[top], bins=range(0, 1100, 100))[0].tolist())
print(" x histogram (bins of 100 px):", np.histogram(X[top], bins=range(0, 1300, 100))[0].tolist())
mid = (Y > 200) & (Y < 820) & (X > 200) & (X < 1080)
print("inner region only: p99.9", np.quantile(V[mid], .999).round(2), "p99", np.quantile(V[mid], .99).round(2), "p50", np.median(V[mid]).round(2))
