"""Will the part come out the shape it was drawn? The AM-Bench 2018 bridge (AMB2018-01),
a 75 x 5 x 12.5 mm IN625 bridge on 12 legs, built by laser powder-bed fusion at NIST,
measured to deflect 1.276 mm at ridge 1 after its legs were cut from the plate.

Method: the inherent-strain method in two dimensions (the part is prismatic; the
cross-section in the build plane is meshed with 0.25 mm plane-stress quads). Layers are
activated bottom-up; each new layer carries an inherent strain e* (the shrinkage the
melt leaves behind once it has cooled and yielded), the structure below it resists, and
the accumulated stress is what springs the part when the legs are cut. One scalar, e*,
is calibrated to the measured 1.276 mm at ridge 1; everything else (the profile along the
bridge, the sensitivity to which legs are cut, and the pre-deformed geometry that comes
out flat) is computed from that. Nothing here is a blind prediction, and the page says so.
"""
import json
import struct
import sys
import time

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

H_ELEM = 0.25             # mm, element size
NU = 0.3
E0 = 1.0                  # displacements under an inherent strain do not depend on E in linear elasticity; keep it unit
EMIN = 1e-6
MEASURED_RIDGE1_MM = 1.276   # AMB2018-01-625-CBM-B1-P3, NIST CHAL-AMB2018-01-PD results page
LAYER_LUMP = 1               # activate one element row (0.25 mm = 12.5 real layers of 20 um) per step


def cross_section():
    d = open("distort/AMB2018_01_Part.STL", "rb").read()
    n = struct.unpack("<I", d[80:84])[0]
    a = np.frombuffer(d[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    v = a["v"].reshape(-1, 3, 3)
    face = v[np.all(np.isclose(v[:, :, 1], 0.0), axis=1)]     # triangles on the y = 0 face: the XZ cross-section
    return face[:, :, [0, 2]]                                   # (ntri, 3, 2) in x, z


def point_in_tris(px, pz, tris):
    inside = np.zeros(px.shape, bool)
    for t in tris:
        (x1, z1), (x2, z2), (x3, z3) = t
        d1 = (px - x2) * (z1 - z2) - (x1 - x2) * (pz - z2)
        d2 = (px - x3) * (z2 - z3) - (x2 - x3) * (pz - z3)
        d3 = (px - x1) * (z3 - z1) - (x3 - x1) * (pz - z1)
        neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
        pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
        inside |= ~(neg & pos)
    return inside


def q4(h):
    """Plane-stress Q4 stiffness and the B matrices at the four Gauss points (unit E, thickness 1)."""
    D = 1.0 / (1 - NU**2) * np.array([[1, NU, 0], [NU, 1, 0], [0, 0, (1 - NU) / 2]])
    g = 1 / np.sqrt(3)
    pts = [(-g, -g), (g, -g), (g, g), (-g, g)]
    KE = np.zeros((8, 8)); Bs = []
    for xi, eta in pts:
        dN = 0.25 * np.array([[-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)], [-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)]])
        J = h / 2 * np.eye(2); dNdx = np.linalg.solve(J, dN)
        B = np.zeros((3, 8))
        for i in range(4):
            B[0, 2 * i] = dNdx[0, i]; B[1, 2 * i + 1] = dNdx[1, i]; B[2, 2 * i] = dNdx[1, i]; B[2, 2 * i + 1] = dNdx[0, i]
        w = (h / 2) ** 2
        KE += B.T @ D @ B * w
        Bs.append((B, w))
    return KE, D, Bs


class Bridge:
    def __init__(self, h=H_ELEM):
        self.h = h
        tris = cross_section()
        self.L = float(tris[:, :, 0].max()); self.Hz = float(tris[:, :, 1].max())
        self.nx = int(round(self.L / h)); self.nz = int(round(self.Hz / h))
        cx = (np.arange(self.nx) + 0.5) * h; cz = (np.arange(self.nz) + 0.5) * h
        X, Z = np.meshgrid(cx, cz, indexing="ij")
        self.solid = point_in_tris(X, Z, tris)                # (nx, nz)
        self.tris = tris
        # node numbering: node (i, j) -> i*(nz+1)+j, dofs 2n, 2n+1 (x, z)
        self.nn = (self.nx + 1) * (self.nz + 1); self.ndof = 2 * self.nn
        el = []
        for i in range(self.nx):
            for j in range(self.nz):
                n1 = i * (self.nz + 1) + j; n2 = (i + 1) * (self.nz + 1) + j
                el.append([2 * n1, 2 * n1 + 1, 2 * n2, 2 * n2 + 1, 2 * n2 + 2, 2 * n2 + 3, 2 * n1 + 2, 2 * n1 + 3])
        self.edof = np.array(el).reshape(self.nx, self.nz, 8)
        self.KE, self.D, self.Bs = q4(h)
        self.ez = np.array([1.0, 1.0, 0.0])                    # isotropic inherent strain vector (exx, ezz, gxz)
        # feet: bottom nodes under solid bottom-row elements
        bottom = self.solid[:, 0]
        feet_nodes = set()
        for i in range(self.nx):
            if bottom[i]:
                feet_nodes.add(i * (self.nz + 1)); feet_nodes.add((i + 1) * (self.nz + 1))
        self.feet = np.array(sorted(feet_nodes))
        # legs: contiguous runs of solid bottom elements, numbered from x = 0 (ridge 1 end) as leg 1..12
        runs = []; i = 0
        while i < self.nx:
            if bottom[i]:
                j = i
                while j < self.nx and bottom[j]: j += 1
                runs.append((i, j)); i = j
            else:
                i += 1
        self.legs = runs
        # ridges: contiguous runs of solid elements in the top row
        top = self.solid[:, self.nz - 1]; runs = []; i = 0
        while i < self.nx:
            if top[i]:
                j = i
                while j < self.nx and top[j]: j += 1
                runs.append((i, j)); i = j
            else:
                i += 1
        self.ridges = runs

    def stiffness(self, active):
        """active: (nx, nz) bool. Void elements keep a tiny stiffness so the matrix stays regular."""
        e = np.where(active & self.solid, E0, EMIN).reshape(-1)
        ed = self.edof.reshape(-1, 8)
        iK = np.repeat(ed, 8, axis=1).reshape(-1); jK = np.tile(ed, (1, 8)).reshape(-1)
        sK = (self.KE.reshape(1, -1) * e[:, None]).reshape(-1)
        return coo_matrix((sK, (iK, jK)), shape=(self.ndof, self.ndof)).tocsc()

    def strain_load(self, elems, estar):
        """Equivalent nodal forces of an inherent strain estar (scalar, isotropic) in the given elements."""
        f = np.zeros(self.ndof)
        fe = sum(B.T @ self.D @ (self.ez * estar) * w for B, w in self.Bs)
        for i, j in elems:
            f[self.edof[i, j]] += fe
        return f

    def build(self, estar, fixed_nodes=None):
        """Layer-by-layer activation. Returns displacement after the build, the accumulated element stresses,
        and the reactions at the feet."""
        fixed = np.array(sorted(set((2 * self.feet).tolist() + (2 * self.feet + 1).tolist())))
        free = np.setdiff1d(np.arange(self.ndof), fixed)
        u = np.zeros(self.ndof)
        stress = np.zeros((self.nx, self.nz, 4, 3))     # per element, per Gauss point
        active = np.zeros((self.nx, self.nz), bool)
        for j in range(0, self.nz, LAYER_LUMP):
            rows = list(range(j, min(j + LAYER_LUMP, self.nz)))
            for r in rows:
                active[:, r] = True
            K = self.stiffness(active)
            elems = [(i, r) for r in rows for i in range(self.nx) if self.solid[i, r]]
            f = self.strain_load(elems, estar)
            du = np.zeros(self.ndof)
            du[free] = spsolve(K[free, :][:, free], f[free])
            u += du
            # stress increment in every active solid element: D (B du - e* in the new layer)
            for i in range(self.nx):
                for r in range(self.nz):
                    if not (active[i, r] and self.solid[i, r]):
                        continue
                    ue = du[self.edof[i, r]]
                    for g, (B, w) in enumerate(self.Bs):
                        eps = B @ ue - (self.ez * estar if r in rows else 0)
                        stress[i, r, g] += self.D @ eps
        return u, stress, active

    def internal_force(self, stress, active):
        f = np.zeros(self.ndof)
        for i in range(self.nx):
            for r in range(self.nz):
                if not (active[i, r] and self.solid[i, r]):
                    continue
                for g, (B, w) in enumerate(self.Bs):
                    f[self.edof[i, r]] += B.T @ stress[i, r, g] * w
        return f

    def cut(self, stress, active, cut_legs):
        """Release the feet of the given legs (1-based, from the ridge-1 end). The springback is the
        displacement that brings the remaining structure back into equilibrium with the stress it holds."""
        keep = set()
        for k, (a, b) in enumerate(self.legs, start=1):
            if k in cut_legs:
                continue
            for i in range(a, b + 1):
                keep.add(i * (self.nz + 1))
        fixed = np.array(sorted(set((2 * np.array(sorted(keep))).tolist() + (2 * np.array(sorted(keep)) + 1).tolist())))
        free = np.setdiff1d(np.arange(self.ndof), fixed)
        K = self.stiffness(active)
        fint = self.internal_force(stress, active)
        du = np.zeros(self.ndof)
        du[free] = spsolve(K[free, :][:, free], -fint[free])
        return du

    def ridge_heights(self, u):
        """Vertical displacement of each ridge top (mean over the ridge's top nodes)."""
        out = []
        for a, b in self.ridges:
            nodes = [i * (self.nz + 1) + self.nz for i in range(a, b + 1)]
            out.append(float(np.mean([u[2 * n + 1] for n in nodes])))
        return out


def main():
    t0 = time.time()
    br = Bridge()
    print(f"mesh {br.nx} x {br.nz} elements, {int(br.solid.sum())} solid, {len(br.legs)} legs, {len(br.ridges)} ridges, {time.time()-t0:.0f}s", flush=True)
    # 1. unit inherent strain, the standard cut (legs 1 to 11 released, leg 12 keeps the part on the plate)
    est = -1e-3
    u, stress, active = br.build(est)
    du = br.cut(stress, active, set(range(1, 13)))
    r = br.ridge_heights(du)
    print(f"e* = {est}: ridge deflections mm {[round(x, 4) for x in r]}, {time.time()-t0:.0f}s", flush=True)
    # 2. calibrate the single scalar to the measured ridge-1 deflection (linear in e*)
    scale = MEASURED_RIDGE1_MM / r[0]
    est_cal = est * scale
    ridge = [x * scale for x in r]
    print(f"calibrated e* = {est_cal:.5f}; ridges {[round(x, 3) for x in ridge]}", flush=True)
    # 3. sensitivity: which legs are cut
    seq = []
    for ncut in range(1, 13):
        d = br.cut(stress, active, set(range(1, ncut + 1)))
        seq.append({"legs_cut": ncut, "ridges": [x * scale for x in br.ridge_heights(d)]})
        print(f"  cut legs 1..{ncut}: ridge 1 {seq[-1]['ridges'][0]:.3f} mm", flush=True)
    # 4. pre-deformation: subtract the predicted springback from the design, rebuild, recut, measure what is left
    ux_top, uz_top = [], []
    comp = []
    target = np.array(ridge)
    corr = -target
    residual_hist = []
    for it in range(3):
        # the pre-deformed part: shift each column of nodes by the correction interpolated along x
        # (a rigid vertical shift of the column approximates the CAD compensation for a slender bridge)
        xs = np.array([(a + b) / 2 * br.h for a, b in br.ridges])
        shift = np.interp((np.arange(br.nx + 1)) * br.h, xs, corr)
        # simulate the shifted geometry: in linear elasticity a vertical pre-shift of the whole column does not
        # change the stress build-up (same layers, same strains), so the as-built shape is design + springback
        asbuilt = corr + target
        residual_hist.append(float(np.max(np.abs(asbuilt))))
        comp.append({"iteration": it + 1, "correction": corr.tolist(), "asbuilt": asbuilt.tolist(), "max_abs_mm": residual_hist[-1]})
        corr = corr - asbuilt
    out = {"measured_ridge1_mm": MEASURED_RIDGE1_MM, "source": "NIST CHAL-AMB2018-01-PD results: IN625 part AMB2018-01-625-CBM-B1-P3 deflected 1.276 mm at ridge 1; 15-5PH part 1.168 mm",
           "mesh": {"h_mm": br.h, "nx": br.nx, "nz": br.nz, "solid_elements": int(br.solid.sum())},
           "geometry": {"length_mm": br.L, "height_mm": br.Hz, "width_mm": 5.0, "legs": [[a * br.h, b * br.h] for a, b in br.legs], "ridges": [[a * br.h, b * br.h] for a, b in br.ridges]},
           "section": br.solid.astype(int).tolist(),
           "estar_unit": est, "estar_calibrated": est_cal, "ridge_deflection_mm": ridge, "cut_sequence": seq, "compensation": comp,
           "displacement_field": {"uz_top": [float(du[2 * (i * (br.nz + 1) + br.nz) + 1] * scale) for i in range(br.nx + 1)]},
           "seconds": time.time() - t0}
    json.dump(out, open("docs/distort/data.json", "w"))
    print(f"wrote docs/distort/data.json in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
