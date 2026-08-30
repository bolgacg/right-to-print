"""A synthetic spare-parts catalogue, shaped on the part types the public
record names (DISCMAM's five use cases: an air compressor cover, a fuel filter
housing, a maintenance tool, a front pulley, a joint-shaft flange) and on the
families a vehicle, vessel or aircraft sustainment desk sees. Every part is
generated from a family template with a seeded random draw, so the catalogue
is reproducible and no part is a real item from any fleet.
"""
import json
import random

random.seed(20260830)

# family: (name stems, material, envelope range mm, mass g range, complexity 0-1, tolerance, channels, criticality choices, demand/yr per 100 units, conv cost EUR, conv lead days)
FAMILIES = [
    ("cover", ["air compressor cover", "gearbox inspection cover", "pump end cover", "alternator end cover"], "cast aluminium", (90, 220), (180, 1400), (0.35, 0.6), "medium", False, [2, 3], (2, 12), (140, 900), (30, 120)),
    ("housing", ["fuel filter housing", "oil filter housing", "thermostat housing", "hydraulic valve housing"], "cast aluminium", (70, 180), (150, 1100), (0.5, 0.8), "fine", True, [1, 2], (2, 10), (220, 1400), (45, 180)),
    ("bracket", ["sensor bracket", "antenna mount", "cable-tray bracket", "radiator bracket", "wing-attachment hinge bracket"], "cast aluminium", (60, 200), (60, 700), (0.3, 0.7), "coarse", False, [2, 3], (3, 30), (60, 420), (20, 90)),
    ("flange", ["joint-shaft flange", "exhaust flange", "coupling flange"], "steel", (80, 240), (400, 3200), (0.2, 0.4), "fine", False, [1, 2], (1, 8), (180, 1100), (40, 200)),
    ("pulley", ["front pulley", "idler pulley", "tensioner pulley"], "steel", (70, 200), (300, 2600), (0.25, 0.45), "fine", False, [1, 2], (2, 9), (150, 800), (35, 160)),
    ("tool", ["maintenance tool, barrel alignment", "bearing puller jaw", "torque adapter", "lifting eye adapter"], "steel", (60, 260), (200, 2400), (0.2, 0.5), "coarse", False, [3], (1, 6), (90, 700), (25, 120)),
    ("manifold", ["coolant manifold", "hydraulic manifold block", "fuel rail manifold"], "stainless", (60, 190), (300, 2800), (0.6, 0.95), "medium", True, [1, 2], (1, 6), (400, 2600), (60, 240)),
    ("impeller", ["coolant pump impeller", "bilge pump impeller", "fan impeller"], "stainless", (50, 160), (80, 900), (0.7, 0.95), "medium", False, [1, 2], (1, 7), (260, 1800), (50, 220)),
    ("gear", ["starter gear", "winch gear", "pump drive gear"], "steel", (40, 140), (100, 1200), (0.4, 0.6), "fine", False, [1, 2], (1, 6), (200, 1300), (45, 210)),
    ("shaft", ["water pump shaft", "auxiliary drive shaft", "actuator shaft"], "steel", (120, 420), (300, 3800), (0.1, 0.25), "fine", False, [1, 2], (1, 5), (150, 1100), (40, 180)),
    ("fitting", ["hydraulic fitting", "fuel line fitting", "pitot line fitting"], "stainless", (20, 60), (15, 120), (0.3, 0.5), "fine", True, [2, 3], (10, 80), (25, 140), (10, 60)),
    ("nozzle", ["washer nozzle", "cooling nozzle", "fuel injector nozzle body"], "stainless", (15, 70), (10, 160), (0.6, 0.9), "fine", True, [2, 3], (3, 25), (60, 500), (30, 150)),
    ("heat exchanger", ["oil cooler core", "electronics cold plate", "charge-air cooler element"], "cast aluminium", (100, 320), (600, 5000), (0.85, 1.0), "medium", True, [1, 2], (1, 4), (900, 6000), (90, 300)),
    ("valve body", ["pressure relief valve body", "check valve body", "solenoid valve body"], "stainless", (30, 110), (60, 700), (0.5, 0.8), "fine", True, [1, 2], (2, 12), (180, 1200), (40, 190)),
    ("mount", ["engine mount", "gun-cradle mount", "generator mount", "camera gimbal mount"], "steel", (90, 300), (800, 7000), (0.3, 0.6), "medium", False, [1, 2], (1, 5), (300, 2200), (45, 200)),
    ("bushing", ["pivot bushing", "suspension bushing", "rudder bushing"], "bronze", (30, 120), (60, 900), (0.1, 0.2), "fine", False, [2, 3], (5, 40), (40, 260), (15, 90)),
    ("cover, large", ["turret access cover", "hatch cover", "deck plate cover"], "cast aluminium", (300, 700), (2500, 14000), (0.3, 0.5), "coarse", False, [3], (1, 3), (500, 3000), (40, 150)),
    ("grip", ["control grip", "handle assembly", "lever knob"], "polymer", (40, 140), (30, 260), (0.4, 0.7), "coarse", False, [3], (5, 60), (15, 120), (10, 45)),
    ("duct", ["cooling duct", "cable duct", "air intake duct"], "polymer", (100, 400), (100, 1200), (0.5, 0.8), "coarse", False, [2, 3], (2, 20), (60, 500), (20, 100)),
]
PLATFORMS = ["4x4 truck", "armoured vehicle", "patrol vessel", "fixed-wing aircraft", "ground support equipment", "generator set", "unmanned aircraft"]
OBSOLESCENCE = ["OEM active", "end of production", "OEM gone"]
RIGHTS = ["OEM owns the data", "print right in framework agreement", "reverse-engineered, open"]


def draw(lo, hi):
    return round(random.uniform(lo, hi), 2)


parts = []
i = 0
for fam, stems, material, env, mass, cx, tol, channels, crit_choices, demand, cost, lead in FAMILIES:
    for stem in stems:
        i += 1
        L = random.uniform(*env)
        W = L * random.uniform(0.35, 1.0)
        H = L * random.uniform(0.2, 0.9)
        obs = random.choices(OBSOLESCENCE, weights=[5, 3, 2])[0]
        rights = random.choices(RIGHTS, weights=[6, 2, 2])[0]
        if obs == "OEM gone":
            rights = random.choice(["reverse-engineered, open", "OEM owns the data"])
        criticality = random.choice(crit_choices)
        parts.append({
            "id": f"P{i:03d}",
            "name": stem,
            "family": fam,
            "platform": random.choice(PLATFORMS if fam != "bushing" else PLATFORMS[:3]),
            "material": material,
            "envelope_mm": [round(L), round(W), round(H)],
            "mass_g": round(random.uniform(*mass)),
            "complexity": draw(*cx),
            "tolerance": tol,
            "channels": channels,
            "criticality": criticality,
            "demand_per_year": round(random.uniform(*demand) * random.uniform(0.6, 1.6), 1),
            "conv_cost_eur": round(random.uniform(*cost) / 10) * 10,
            "conv_lead_days": round(random.uniform(*lead) * (1.6 if obs == "OEM gone" else 1.0)),
            "obsolescence": obs,
            "data_rights": rights,
        })

json.dump({"generated": "2026-08-30", "seed": 20260830, "n": len(parts),
           "note": "synthetic catalogue; part families shaped on the public DISCMAM use cases and common sustainment items; no part is a real item from any fleet",
           "parts": parts}, open("data/catalogue.json", "w"), indent=1)
print(f"catalogue: {len(parts)} parts across {len(FAMILIES)} families")
