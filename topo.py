"""One part all the way: a hinge-type bracket, topology-optimised for
minimum compliance at a fixed material budget, with and without the
45-degree self-supporting constraint of laser powder-bed fusion, at three
build orientations.

Method: the classic 2D SIMP formulation (Sigmund's 99-line / top88 lineage):
bilinear quad elements, density filter, optimality-criteria update. The
printability constraint is Langelaar's additive-manufacturing filter
(Struct Multidisc Optim 55, 2017): a layer-by-layer smooth minimum of each
element's density and the smooth maximum of the three elements supporting
it in the layer below, so material that would overhang more than 45 degrees
cannot exist. Sensitivities are back-propagated through the filter exactly.

Everything here is 2D, linear elastic, one load case. It is a demonstration
of the design consequence of printing, not a qualified part.
"""
import json
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

NELX, NELY = 120, 60          # design domain, elements (mm at 1 mm per element)
VOLFRAC = 0.35
PENAL = 3.0
RMIN = 2.4
E0, EMIN, NU = 1.0, 1e-9, 0.3
P_NORM = 40.0                 # smooth max/min sharpness in the AM filter
MAXIT = 140


def element_stiffness():
    k = np.array([1/2-NU/6, 1/8+NU/8, -1/4-NU/12, -1/8+3*NU/8, -1/4+NU/12, -1/8-NU/8, NU/6, 1/8-3*NU/8])
    KE = E0/(1-NU**2)*np.array([
        [k[0], k[1], k[2], k[3], k[4], k[5], k[6], k[7]],
        [k[1], k[0], k[7], k[6], k[5], k[4], k[3], k[2]],
        [k[2], k[7], k[0], k[5], k[6], k[3], k[4], k[1]],
        [k[3], k[6], k[5], k[0], k[7], k[2], k[1], k[4]],
        [k[4], k[5], k[6], k[7], k[0], k[1], k[2], k[3]],
        [k[5], k[4], k[3], k[2], k[1], k[0], k[7], k[6]],
        [k[6], k[3], k[4], k[1], k[2], k[7], k[0], k[5]],
        [k[7], k[2], k[1], k[4], k[3], k[6], k[5], k[0]]])
    return KE


def setup():
    nelx, nely = NELX, NELY
    ndof = 2*(nelx+1)*(nely+1)
    edofMat = np.zeros((nelx*nely, 8), dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            el = ely + elx*nely
            n1 = (nely+1)*elx + ely
            n2 = (nely+1)*(elx+1) + ely
            edofMat[el, :] = [2*n1+2, 2*n1+3, 2*n2+2, 2*n2+3, 2*n2, 2*n2+1, 2*n1, 2*n1+1]
    iK = np.kron(edofMat, np.ones((8, 1))).flatten()
    jK = np.kron(edofMat, np.ones((1, 8))).flatten()
    # density filter
    nfilter = int(nelx*nely*((2*(np.ceil(RMIN)-1)+1)**2))
    iH = np.zeros(nfilter); jH = np.zeros(nfilter); sH = np.zeros(nfilter)
    cc = 0
    for i in range(nelx):
        for j in range(nely):
            row = i*nely + j
            kk1 = int(np.maximum(i-(np.ceil(RMIN)-1), 0)); kk2 = int(np.minimum(i+np.ceil(RMIN), nelx))
            ll1 = int(np.maximum(j-(np.ceil(RMIN)-1), 0)); ll2 = int(np.minimum(j+np.ceil(RMIN), nely))
            for k in range(kk1, kk2):
                for l in range(ll1, ll2):
                    col = k*nely + l
                    fac = RMIN - np.sqrt((i-k)**2 + (j-l)**2)
                    iH[cc] = row; jH[cc] = col; sH[cc] = np.maximum(0.0, fac); cc += 1
    H = coo_matrix((sH, (iH, jH)), shape=(nelx*nely, nelx*nely)).tocsc()
    Hs = np.asarray(H.sum(1)).flatten()
    # the bracket: clamped along the left wall (x = 0), a pin at the right end carrying a downward load
    # a keep-out hole for the pin at (x = 108, y = 30), radius 7; a keep-in ring around it
    dofs = np.arange(ndof)
    fixed = np.union1d(dofs[0:2*(nely+1):2], dofs[1:2*(nely+1):2])  # left edge, both directions
    free = np.setdiff1d(dofs, fixed)
    f = np.zeros(ndof)
    # the pin bears on the lower half of the hole: spread the load over the ring nodes just below the hole
    for dx in (-2, -1, 0, 1, 2):
        load_node = (nely+1)*(108+dx) + 38
        f[2*load_node+1] = -1.0/5
    # passive elements: hole (void) and ring (solid)
    passive = np.zeros(nelx*nely, dtype=int)
    for elx in range(nelx):
        for ely in range(nely):
            r = np.hypot(elx+0.5-108, ely+0.5-30)
            if r < 7: passive[ely + elx*nely] = 1
            elif r < 10: passive[ely + elx*nely] = 2
    return dict(nelx=nelx, nely=nely, ndof=ndof, edofMat=edofMat, iK=iK, jK=jK, H=H, Hs=Hs, fixed=fixed, free=free, f=f, passive=passive, KE=element_stiffness())


# ---------------- Langelaar's AM filter, layer by layer, with exact backprop ----------------
def smax(a, b, c):
    # smooth maximum of three non-negative values via the P-norm
    s = (a**P_NORM + b**P_NORM + c**P_NORM)
    return s**(1.0/P_NORM)


def am_filter_forward(x, orient):
    """x: (nely, nelx) physical densities. orient: build direction: 'up' (layers grow from the
    bottom edge, y increasing = later layers... here y index 0 is the top in element numbering, so
    we rotate the array so that 'first printed layer' is row 0 of the working array)."""
    X = orient_in(x, orient)
    n_lay, n_col = X.shape
    XI = np.zeros_like(X)
    cache = []
    XI[0] = X[0]
    for i in range(1, n_lay):
        below = XI[i-1]
        left = np.concatenate([[0.0], below[:-1]]); right = np.concatenate([below[1:], [0.0]])
        sm = smax(left + 1e-12, below + 1e-12, right + 1e-12)
        # smooth minimum of x and sm: Langelaar uses min(x, sm) = x + sm - sqrt((x-sm)^2 + eps)... use the softmin via -P-norm
        # Langelaar's smooth minimum, with the + sqrt(eps) term that keeps smin(0, 0) = 0
        xi = 0.5*(X[i] + sm - np.sqrt((X[i]-sm)**2 + 1e-4) + 1e-2)
        XI[i] = xi
        cache.append((left, below, right, sm, X[i]))
    return orient_out(XI, orient), (X, XI, cache)


def am_filter_backward(dXI, ctx, orient):
    """Given d(objective)/d(XI) (in the original orientation), return d/dX (original orientation)."""
    X, XI, cache = ctx
    G = orient_in(dXI, orient).copy()      # gradient wrt XI in working orientation
    dX = np.zeros_like(X)
    n_lay = X.shape[0]
    for i in range(n_lay-1, 0, -1):
        left, below, right, sm, xi_in = cache[i-1]
        g = G[i]
        # xi = 0.5*(x + sm - sqrt((x-sm)^2 + eps))
        d = np.sqrt((xi_in-sm)**2 + 1e-4)
        dxi_dx = 0.5*(1 - (xi_in-sm)/d)
        dxi_dsm = 0.5*(1 + (xi_in-sm)/d)
        dX[i] += g*dxi_dx
        gsm = g*dxi_dsm
        # sm = (l^p + b^p + r^p)^(1/p): dsm/dl = (l/sm)^(p-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            dl = np.where(sm > 0, ((left+1e-12)/sm)**(P_NORM-1), 0.0)
            db = np.where(sm > 0, ((below+1e-12)/sm)**(P_NORM-1), 0.0)
            dr = np.where(sm > 0, ((right+1e-12)/sm)**(P_NORM-1), 0.0)
        # left[j] = below[j-1], right[j] = below[j+1]
        gb = gsm*db
        gb[:-1] += (gsm*dl)[1:]
        gb[1:] += (gsm*dr)[:-1]
        G[i-1] += gb
    dX[0] += G[0]
    return orient_out(dX, orient)


def orient_in(a, orient):
    # working array: row 0 = first printed layer, rows = layers, columns = across the layer
    # element array a is (nely, nelx) with row 0 at the top of the domain
    if orient == "bottom-up": return a[::-1, :]
    if orient == "top-down": return a
    if orient == "left-to-right": return a.T
    if orient == "right-to-left": return a.T[::-1, :]
    raise ValueError(orient)


def orient_out(w, orient):
    if orient == "bottom-up": return w[::-1, :]
    if orient == "top-down": return w
    if orient == "left-to-right": return w.T
    if orient == "right-to-left": return w[::-1, :].T
    raise ValueError(orient)


def unsupported_fraction(x, orient, thresh=0.5):
    """Share of solid elements with no solid element among the three beneath them in build order."""
    X = orient_in(x, orient) >= thresh
    n = 0; bad = 0
    for i in range(1, X.shape[0]):
        below = X[i-1]
        sup = below | np.concatenate([[False], below[:-1]]) | np.concatenate([below[1:], [False]])
        solid = X[i]
        n += solid.sum(); bad += (solid & ~sup).sum()
    return float(bad/max(n, 1))


def optimise(S, orient=None):
    nelx, nely = S["nelx"], S["nely"]
    x = VOLFRAC*np.ones(nely*nelx)
    x[S["passive"] == 1] = 0.0; x[S["passive"] == 2] = 1.0
    xPhys = x.copy()
    history = []
    loop = 0; change = 1.0
    while change > 0.01 and loop < MAXIT:
        loop += 1
        # filtered densities
        xTilde = np.asarray(S["H"] @ x).flatten()/S["Hs"]
        xTilde[S["passive"] == 1] = 0.0; xTilde[S["passive"] == 2] = 1.0
        if orient:
            xT2 = xTilde.reshape(nelx, nely).T  # (nely, nelx)
            xP2, ctx = am_filter_forward(xT2, orient)
            xPhys = xP2.T.flatten()
        else:
            xPhys = xTilde
        # FE
        sK = ((S["KE"].flatten()[np.newaxis]).T*(EMIN + xPhys**PENAL*(E0-EMIN))).flatten(order="F")
        K = coo_matrix((sK, (S["iK"], S["jK"])), shape=(S["ndof"], S["ndof"])).tocsc()
        u = np.zeros(S["ndof"])
        fr = S["free"]
        u[fr] = spsolve(K[fr, :][:, fr], S["f"][fr])
        ce = (np.dot(u[S["edofMat"]].reshape(nelx*nely, 8), S["KE"]) * u[S["edofMat"]].reshape(nelx*nely, 8)).sum(1)
        c = ((EMIN + xPhys**PENAL*(E0-EMIN))*ce).sum()
        dc = (-PENAL*xPhys**(PENAL-1)*(E0-EMIN))*ce
        dv = np.ones(nelx*nely)
        # chain through AM filter, then density filter
        if orient:
            dc = am_filter_backward(dc.reshape(nelx, nely).T, ctx, orient).T.flatten()
            dv = am_filter_backward(dv.reshape(nelx, nely).T, ctx, orient).T.flatten()
        dc = np.asarray(S["H"] @ (dc/S["Hs"])).flatten()
        dv = np.asarray(S["H"] @ (dv/S["Hs"])).flatten()
        # optimality criteria
        l1, l2, move = 0.0, 1e9, 0.2
        while (l2-l1)/(l1+l2) > 1e-3:
            lmid = 0.5*(l2+l1)
            xnew = np.maximum(0.0, np.maximum(x-move, np.minimum(1.0, np.minimum(x+move, x*np.sqrt(np.maximum(-dc/dv, 0)/lmid)))))
            xnew[S["passive"] == 1] = 0.0; xnew[S["passive"] == 2] = 1.0
            # volume of the physical field after the filters
            xt = np.asarray(S["H"] @ xnew).flatten()/S["Hs"]
            xt[S["passive"] == 1] = 0.0; xt[S["passive"] == 2] = 1.0
            if orient:
                xp = am_filter_forward(xt.reshape(nelx, nely).T, orient)[0].T.flatten()
            else:
                xp = xt
            if xp.mean() > VOLFRAC: l1 = lmid
            else: l2 = lmid
        change = np.abs(xnew-x).max()
        x = xnew
        history.append(float(c))
    return xPhys.reshape(nelx, nely).T, float(c), loop, history


def main():
    S = setup()
    t0 = time.time()
    out = {"domain_mm": [NELX, NELY], "volfrac": VOLFRAC, "penal": PENAL, "rmin": RMIN, "load": "unit downward load at the pin, x=108 mm, y=30 mm", "support": "left wall clamped", "designs": []}
    ref = None
    for name, orient in [("unconstrained", None), ("printed bottom-up", "bottom-up"), ("printed on its side", "left-to-right"), ("printed top-down", "top-down")]:
        xP, c, it, hist = optimise(S, orient)
        d = {"name": name, "orientation": orient or "none", "compliance": c, "iterations": it, "volume": float(xP.mean()),
             "unsupported": {o: unsupported_fraction(xP, o) for o in ["bottom-up", "left-to-right", "top-down", "right-to-left"]},
             "field": np.round(xP, 2).tolist(), "history": [round(h, 4) for h in hist]}
        if ref is None: ref = c
        d["compliance_vs_free"] = c/ref
        out["designs"].append(d)
        print(f"{name:22s} compliance {c:8.3f} ({c/ref:5.2f}x free) iters {it:3d} volume {xP.mean():.3f} unsupported {{" + ", ".join(f"{k}:{v:.3f}" for k, v in d['unsupported'].items()) + f"}} {time.time()-t0:.0f}s", flush=True)
    # the mass number: a solid bracket of the same domain minus the hole vs the optimised one
    solid_frac = 1.0 - (S["passive"] == 1).mean()
    out["mass_saved_vs_solid_pct"] = 100*(1 - VOLFRAC/solid_frac)
    out["seconds"] = time.time()-t0
    json.dump(out, open("data/topo.json", "w"))
    print(f"mass saved vs a solid plate: {out['mass_saved_vs_solid_pct']:.0f}%; wrote data/topo.json in {out['seconds']:.0f}s")


if __name__ == "__main__":
    main()
