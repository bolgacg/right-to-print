# The right to print

A decision console for on-site metal printing of spare parts, built in August 2026 around the
public material of the Danish Technological Institute's industrial 3D-print centre. Live at
https://bolgacg.github.io/right-to-print/

It takes a catalogue of spare parts and answers, part by part, the four questions a sustainment
desk asks before it buys a print right:

1. **Which parts.** A technical score (does the process want this part) and a business score
   (does the fleet want it printed), each criterion with its fact, its rule and its weight
   printed next to the verdict; the single change of fact that would flip the verdict; and the
   questions to put to the supplier before paying for the right.
2. **Is it worth it.** A first-order cost model for one printed part against the conventional
   price, the days saved, the value of a stopped platform, the chance the part is not on the
   shelf, summed over the fleet's life and discounted, minus the cost of qualifying the part
   family. Printing never wins on unit price in this catalogue; the page says so.
3. **What a container buys.** A ninety-day discrete simulation of fleet readiness with
   conventional supply, with a deployable printer next to the fleet, and with reachback to the
   home centre; then a sweep over fleet size, averaged over five random draws, to find where one
   container stops keeping up.
4. **Which acceptance tier.** DISCMAM's four tiers (permanent, temporary, emergency, scrap) as
   an explicit rule set with a named signer, so a non-specialist can read why a part landed
   where it did. The permanent gate (99.9 percent density) is DISCMAM's; the other thresholds
   are this console's illustrative policy.

One part goes all the way: a hinge-type bracket, topology-optimised for stiffness at 35 percent
of the material, unconstrained and then under laser powder-bed fusion's 45-degree
self-supporting rule at three build orientations (Langelaar's additive-manufacturing filter with
exact sensitivities). One orientation fails to converge to a usable design and is reported as a
failure.

## Chapter two: can the camera certify the part?

https://bolgacg.github.io/right-to-print/qualify/ measures the witnesses the release policy relies on,
on open datasets: probability-of-detection curves for a layer camera and optical tomography (Aalto
University's annotated EOS M290 dataset, a transparent detector, a held-out build, MIL-HDBK-1823A
hit/miss model with a false-alarm dial), operating-characteristic curves for an n-coupon acceptance
rule on Penn State's Ti-6Al-4V tensile data, the four tiers applied to 42 real process windows, and
the fatigue-life scatter of printed titanium from FatigueData-AM2022. `qualify/analysis.py` computes
everything; `qualify/build_page.py` writes the page.

## Chapter three: will the part come out the shape it was drawn?

https://bolgacg.github.io/right-to-print/distort/ takes NIST's AM-Bench 2018 bridge (geometry from
the benchmark's STL, the measured 1.276 mm rise at ridge 1 after the legs were cut), builds it
layer by layer with a two-dimensional inherent-strain model, calibrates the one scalar to the
measurement, and then shows the springback profile along the bridge, how it grows as the legs are
cut in sequence, and what a pre-deformed design comes out like when the model is wrong by a given
amount. `distort/simulate.py` computes everything in about a minute.

## How it is built

| file | what it does |
|---|---|
| `catalogue.py` | generates the synthetic catalogue (63 parts, 19 families, fixed seed); the families are shaped on the five public DISCMAM use cases and common sustainment items; no part is a real item from any fleet |
| `rules.py` | process envelopes, alloy mapping, cost assumptions, gates and weights, each tagged fact or assumption with its source |
| `model.js` | the decision model: screening, flip analysis, supplier questions, cost and print-right value, readiness simulation, sweep, acceptance tier. Pure functions; the page and the build script run the same file |
| `topo.py` | the bracket: 2D SIMP with a density filter and Langelaar's AM filter, optimality criteria update |
| `build_data.py` | runs the model through node at the default settings and assembles `docs/data.json` |
| `build_page.py` | inlines the model and the data into `template.html` and writes `docs/index.html` |

    python3 -m venv .venv && .venv/bin/pip install numpy scipy
    .venv/bin/python rules.py && .venv/bin/python catalogue.py
    .venv/bin/python topo.py          # about six minutes
    .venv/bin/python build_data.py && .venv/bin/python build_page.py

Every number in the page's prose is computed by the same code that moves when a slider moves.

## Limits, stated

A synthetic catalogue proves the method, not any fleet's answer. Scores use attributes, not
geometry. The cost model is first-order with assumed rates; DTI's own parameters are not
public and are not used. The bracket is a two-dimensional section under one load case, linear
elastic, unqualified. The readiness simulation treats failures as independent and ignores
cannibalisation, partial stock and transport risk. The acceptance policy is illustrative except
for the one gate taken from DISCMAM. Nothing here is a certification claim.

## Sources

Danish Technological Institute, Center for Industrial 3D Print (facilities and alloy list);
Nikon SLM Solutions, SLM 280 build volume; the DISCMAM project (European Defence Fund) and the
Additive Manufacturing Media article of 23 July 2026 on digital qualification of field-printed
parts; ing.dk columns by Jeppe Byskov (April 2026) and the DALO engineer interview (April 2026);
M. Langelaar, "An additive manufacturing filter for topology optimization of print-ready
designs", Structural and Multidisciplinary Optimization 55 (2017); Sigmund's 99-line code and
the top88 formulation for the density method.
