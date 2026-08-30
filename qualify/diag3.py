import glob, os, sys
import numpy as np
from scipy import ndimage
sys.path.insert(0, "qualify")
from analysis import ROOT, SENSORS, TEST_BUILD, load_image, boxes_for, grid
rng = np.random.default_rng(1)
sensor = "PB"; cfg = SENSORS[sensor]; wh, ww = cfg["win"]
imgs = sorted(glob.glob(f"{ROOT}/{sensor}/*.jpg")); rng.shuffle(imgs)
lab = [p for p in imgs if os.path.exists(f"{ROOT}/{sensor}_label/" + os.path.basename(p)[:-4] + ".xml")][:150]
def feats(img):
    y0, y1, x0, x1 = cfg["roi"]
    hp = img - ndimage.uniform_filter1d(img, 21, axis=0)
    noise = np.median(np.abs(hp[y0:y1, x0:x1])) + 1e-3
    hpn = hp / noise
    out = []
    for L in (96, 200, 400):
        out.append(ndimage.maximum_filter(np.abs(ndimage.uniform_filter1d(hpn, L, axis=1)), (wh, 1)))
    # a second-derivative line detector: row minus mean of rows 6 above and below
    ridge = hpn - 0.5 * (np.roll(hpn, 6, 0) + np.roll(hpn, -6, 0))
    out.append(ndimage.maximum_filter(np.abs(ndimage.uniform_filter1d(ridge, 200, axis=1)), (wh, 1)))
    Y, X = grid(img.shape, cfg)
    return np.stack([f[Y, X] for f in out], -1), Y, X
names = ["line96", "line200", "line400", "ridge200"]
bm, neg, blen = [], [], []
for p in lab:
    img = load_image(p, sensor); F, Y, X = feats(img); boxes = boxes_for(sensor, os.path.basename(p)[:-4])
    near = np.zeros(Y.shape, bool)
    for x0, y0, x1, y1 in boxes:
        sel = (X >= x0 - ww/2) & (X <= x1 + ww/2) & (Y >= y0 - wh) & (Y <= y1 + wh)
        near |= (X >= x0 - 2*ww) & (X <= x1 + 2*ww) & (Y >= y0 - 3*wh) & (Y <= y1 + 3*wh)
        if sel.any(): bm.append(F[sel].reshape(-1, 4).max(0)); blen.append(x1 - x0)
    neg.append(F[~near].reshape(-1, 4))
bm = np.array(bm); neg = np.vstack(neg); wpi = len(neg) / len(lab); blen = np.array(blen)
print("boxes", len(bm), "non-box windows in labelled images", len(neg), "per image", round(wpi))
for i, nm in enumerate(names):
    row = []
    for fc in (0.25, 1, 3):
        thr = np.quantile(neg[:, i], 1 - fc / wpi); h = (bm[:, i] > thr)
        row.append(f"fc {fc}: hit {h.mean():.2f} (long>300px {h[blen>300].mean():.2f}, short<100px {h[blen<100].mean():.2f})")
    print(f"  {nm:9s} box p50 {np.median(bm[:, i]):6.2f} neg p50 {np.median(neg[:, i]):5.2f} p99.9 {np.quantile(neg[:, i], .999):6.2f} | " + " | ".join(row))
