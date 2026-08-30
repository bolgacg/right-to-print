"""Assemble docs/data.json: catalogue, rules, the screening of every part, the
economics at the default settings, the readiness sweep, the optimised bracket.
Everything the page states in prose is computed here, through the same
model.js the page runs, so the text and the controls cannot disagree."""
import json
import os
import subprocess

os.makedirs("docs", exist_ok=True)
NODE = os.path.expanduser("~/.nvm/versions/node")
node = "node"
try:
    vers = sorted(os.listdir(NODE))
    node = os.path.join(NODE, vers[-1], "bin", "node")
except OSError:
    pass

DEFAULTS = {"downtimeEurDay": 1200, "pStockout": 0.35, "fleetYears": 8, "container": True, "fleet": 60,
            "printers": 1, "powderKg": 60, "days": 90, "seed": 7, "reachbackDays": 3}

script = r"""
const R = require('./model.js'); const rules = require('./data/rules.json'); const cat = require('./data/catalogue.json');
const s0 = %s;
const screened = cat.parts.map(p => R.screen(p, rules));
const eco = cat.parts.map(p => ({ part: p, eco: R.economics(p, rules, s0) }));
const counts = {}; screened.forEach(s => counts[s.v.label] = (counts[s.v.label] || 0) + 1);
const actions = {}; eco.forEach(e => { const v = screened.find(x => x.id === e.part.id).v.label; const k = R.integrate(v, e.eco); actions[k] = (actions[k] || 0) + 1; });
const cheaperPerUnit = eco.filter(e => e.eco.feasible && e.eco.perEventCost > 0).length;
const cheapest = Object.assign({}, s0, { machineEurH: 40, powderFactor: 0.5 });
const cheaperAtCheapest = cat.parts.filter(p => { const e = R.economics(p, rules, cheapest); return e.feasible && e.perEventCost > 0; }).length;
const ratios = eco.filter(e => e.eco.feasible).map(e => e.eco.pc.unit / e.part.conv_cost_eur).sort((a, b) => a - b);
const ratioSpan = [ratios[Math.floor(ratios.length * 0.1)], ratios[Math.floor(ratios.length * 0.5)], ratios[Math.floor(ratios.length * 0.9)]];
const best = eco.filter(e => e.eco.feasible).sort((a, b) => b.eco.rightWorth - a.eco.rightWorth)[0];
const rd = R.readiness(eco, rules, s0);
const fleets = [10, 20, 40, 60, 100, 150, 200, 300, 400, 600];
const seeds = [1, 2, 3, 4, 5];
const sweeps = seeds.map(seed => R.sweep(eco, rules, Object.assign({}, s0, { seed }), fleets));
const sweep = fleets.map((N, i) => ({ fleet: N, conventional: seeds.reduce((a, _, j) => a + sweeps[j][i].conventional, 0) / seeds.length,
  container: seeds.reduce((a, _, j) => a + sweeps[j][i].container, 0) / seeds.length, reachback: seeds.reduce((a, _, j) => a + sweeps[j][i].reachback, 0) / seeds.length,
  queueEnd: Math.round(seeds.reduce((a, _, j) => a + sweeps[j][i].queueEnd, 0) / seeds.length) }));
const breakAt = sweep.find(r => r.container - r.conventional < 0.02);
const tierExamples = [
  { name: 'a clean build', inp: { density: 99.93, deviation: 0.8, witness: 'pass', tolerance: 'fine', machined: true, criticality: 1, mission: 'routine' } },
  { name: 'porous but usable', inp: { density: 99.6, deviation: 0.9, witness: 'pass', tolerance: 'coarse', machined: false, criticality: 2, mission: 'routine' } },
  { name: 'mission-stopped, no other route', inp: { density: 99.2, deviation: 1.1, witness: 'none', tolerance: 'coarse', machined: false, criticality: 1, mission: 'emergency' } },
  { name: 'the same part on a routine day', inp: { density: 99.2, deviation: 1.1, witness: 'none', tolerance: 'coarse', machined: false, criticality: 1, mission: 'routine' } },
].map(t => Object.assign(t, { out: R.tier(t.inp, rules) }));
console.log(JSON.stringify({ thresholds: R.THRESH, screened, eco: eco.map(e => ({ id: e.part.id, eco: e.eco })), counts, actions, cheaperPerUnit, cheaperAtCheapest, ratioSpan,
  best: { id: best.part.id, name: best.part.name, worth: best.eco.rightWorth, action: best.eco.action },
  readiness: Object.fromEntries(Object.entries(rd).map(([k, v]) => [k, { mean: v.mean, printed: v.printed, reach: v.reach, powderUsed: v.powderUsed, queueEnd: v.queueEnd, series: v.series }])),
  sweep, sweepSeeds: seeds.length, breakAt: breakAt ? breakAt.fleet : null, tierExamples, defaults: s0 }));
""" % json.dumps(DEFAULTS)
out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
model = json.loads(out.stdout)
data = {
    "built": "2026-08-30",
    "catalogue": json.load(open("data/catalogue.json")),
    "rules": json.load(open("data/rules.json")),
    "model": model,
    "topo": json.load(open("data/topo.json")) if os.path.exists("data/topo.json") else None,
    "topo_retry": ({"orientation": "top-down", **{k: v for k, v in json.load(open("data/topo_topdown.json")).items() if k in ("compliance", "iterations")}}
                   if os.path.exists("data/topo_topdown.json") else None),
}
json.dump(data, open("docs/data.json", "w"))
m = model
print(f"verdicts {m['counts']}  actions {m['actions']}  cheaper per unit {m['cheaperPerUnit']}/{len(m['eco'])}, at the cheapest setting {m['cheaperAtCheapest']}; unit ratio p10/p50/p90 {[round(x,1) for x in m['ratioSpan']]}")
print(f"best right: {m['best']['name']} worth {m['best']['worth']:.0f} EUR ({m['best']['action']})")
print("readiness " + ", ".join(f"{k} {v['mean']:.3f}" for k, v in m["readiness"].items()) + f"; container stops helping at fleet {m['breakAt']}")
print("tiers: " + ", ".join(f"{t['name']} -> {t['out']['tier']}" for t in m["tierExamples"]))
print("wrote docs/data.json", os.path.getsize("docs/data.json") // 1024, "KB; topo", "yes" if data["topo"] else "not yet")
