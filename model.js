/* The decision model behind "The right to print". Pure functions, no DOM,
   loaded by the page and by build_data.py (through node) so the numbers in
   the text and the numbers on the screen come from the same code. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.RTP = factory();
})(typeof self !== "undefined" ? self : this, function () {

  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const THRESH = { t: 65, b: 60 }; // a part must clear both to be 'print'; one of them to be 'investigate'

  /* ---------- deterministic random (mulberry32) ---------- */
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ---------- geometry helpers ---------- */
  function fitsEnvelope(part, env) {
    // any axis permutation may be the build direction; the part fits if some ordering fits
    const p = [...part.envelope_mm].sort((a, b) => b - a), e = [...env].sort((a, b) => b - a);
    return p[0] <= e[0] && p[1] <= e[1] && p[2] <= e[2];
  }
  function volumeCm3(part, rules) {
    const rho = rules.alloys[part.material].density_g_cm3;
    return part.mass_g / rho;
  }

  /* ---------- act one: screening ---------- */
  function technical(part, rules) {
    const w = rules.weights.technical;
    const alloy = rules.alloys[part.material];
    const crit = [];
    let gate = null;
    const fitBase = fitsEnvelope(part, rules.processes.lpbf_base.envelope_mm);
    const fitCont = fitsEnvelope(part, rules.processes.lpbf_container.envelope_mm);
    const fitDed = fitsEnvelope(part, rules.processes.ded.envelope_mm);
    let proc = alloy.process === "sls" ? "SLS (polymer)" : (fitCont ? "LPBF, container or home centre" : fitBase ? "LPBF, home centre only" : fitDed ? "DED only" : null);
    if (alloy.process !== "sls" && !fitBase && !fitDed) gate = "too large for any modelled process";
    crit.push({ k: "build envelope", fact: part.envelope_mm.join(" x ") + " mm", rule: "must fit one process envelope in some orientation", pts: gate ? 0 : (fitCont ? 1 : fitBase ? 0.8 : 0.4), w: "gate", note: proc || "no fit" });
    // alloy
    let alloyPts = alloy.am ? 1 : 0;
    if (!alloy.am) gate = gate || "no printable alloy for " + part.material;
    crit.push({ k: "alloy", fact: part.material + (alloy.am ? " to " + alloy.am : ", no listed equivalent"), rule: "a listed alloy exists for the material class", pts: alloyPts, w: w.alloy, note: alloy.source });
    // complexity: AM rewards it
    crit.push({ k: "geometric complexity", fact: part.complexity.toFixed(2) + " of 1", rule: "more complex shapes gain more from printing (surface to volume, integrated features)", pts: part.complexity, w: w.complexity, note: "0 is a plain shaft, 1 is a heat exchanger core" });
    // tolerance
    const tolPts = { coarse: 1, medium: 0.7, fine: 0.35 }[part.tolerance];
    crit.push({ k: "tolerance class", fact: part.tolerance, rule: "fine tolerances need post-machining of mating faces, which costs hours and fixtures", pts: tolPts, w: w.tolerance, note: "as-built LPBF surfaces are rough; fine faces are machined afterwards" });
    // mass: build time
    const vol = volumeCm3(part, rules);
    const massPts = clamp(1 - Math.log10(Math.max(vol, 1)) / 3, 0, 1);
    crit.push({ k: "volume to print", fact: vol.toFixed(0) + " cm3 (" + part.mass_g + " g)", rule: "build time grows with volume; big solid parts print slowly", pts: massPts, w: w.mass, note: "rate " + (alloy.deposition_cm3_h || "n/a") + " cm3 per hour, assumed" });
    // channels
    crit.push({ k: "internal channels", fact: part.channels ? "yes" : "no", rule: "channels are where printing beats machining, if the powder can get out", pts: part.channels ? 1 : 0.5, w: w.channels, note: part.channels ? "needs a powder-removal path" : "" });
    const num = crit.filter(c => c.w !== "gate").reduce((a, c) => a + c.pts * c.w, 0);
    const den = crit.filter(c => c.w !== "gate").reduce((a, c) => a + c.w, 0);
    let score = gate ? 0 : Math.round(100 * num / den * (fitCont ? 1 : fitBase ? 0.92 : 0.75));
    return { score, gate, crit, proc, fitBase, fitCont, fitDed, alloy };
  }

  function business(part, rules) {
    const w = rules.weights.business;
    const crit = [];
    const critW = { 1: 1, 2: 0.6, 3: 0.25 }[part.criticality];
    const leadPts = clamp(part.conv_lead_days / 180, 0, 1) * critW;
    crit.push({ k: "lead time x criticality", fact: part.conv_lead_days + " days, criticality " + part.criticality, rule: "a long wait for a part that stops the platform is the whole case for printing", pts: leadPts, w: w.lead_time_x_criticality, note: "criticality 1 stops the platform, 2 degrades it, 3 is cosmetic" });
    const obsPts = { "OEM active": 0.2, "end of production": 0.65, "OEM gone": 1 }[part.obsolescence];
    crit.push({ k: "obsolescence", fact: part.obsolescence, rule: "when the supplier is gone, printing is the only route besides redesign", pts: obsPts, w: w.obsolescence, note: "" });
    const d = part.demand_per_year;
    const demPts = d < 1 ? 0.5 : d <= 30 ? 1 : d <= 100 ? 0.6 : 0.2;
    crit.push({ k: "demand fit", fact: d.toFixed(1) + " per year", rule: "printing suits one to a few dozen a year; above that, tooling wins", pts: demPts, w: w.demand_fit, note: "" });
    const costPts = clamp(Math.log10(Math.max(part.conv_cost_eur, 10) / 30) / 2.3, 0, 1);
    crit.push({ k: "conventional unit cost", fact: part.conv_cost_eur + " EUR", rule: "an expensive conventional part leaves room for printing's higher unit cost", pts: costPts, w: w.unit_cost, note: "" });
    const num = crit.reduce((a, c) => a + c.pts * c.w, 0), den = crit.reduce((a, c) => a + c.w, 0);
    return { score: Math.round(100 * num / den), crit, rights: part.data_rights };
  }

  function verdict(t, b) {
    if (t.gate) return { label: "leave", why: t.gate };
    const T = t.score >= THRESH.t, B = b.score >= THRESH.b;
    if (T && B) return { label: "print", why: "printable and worth it" };
    if (T && !B) return { label: "investigate", why: "printable, but the business case is thin: cheap, quick or rarely needed" };
    if (!T && B) return { label: "investigate", why: "the need is real, the geometry or material fights the process" };
    return { label: "leave", why: "neither printable enough nor needed enough" };
  }

  function screen(part, rules) {
    const t = technical(part, rules), b = business(part, rules), v = verdict(t, b);
    return { id: part.id, t, b, v, flip: flip(part, rules, v.label), questions: questions(part, t, b) };
  }

  /* which single change of fact would change the verdict; smallest move first */
  function flip(part, rules, current) {
    const tries = [];
    const leads = [10, 20, 30, 45, 60, 90, 120, 180, 240, 365];
    for (const L of leads) if (L !== part.conv_lead_days) tries.push({ field: "conv_lead_days", value: L, text: "lead time were " + L + " days" });
    for (const c of [1, 2, 3]) if (c !== part.criticality) tries.push({ field: "criticality", value: c, text: "criticality were " + c });
    for (const o of ["OEM active", "end of production", "OEM gone"]) if (o !== part.obsolescence) tries.push({ field: "obsolescence", value: o, text: "the supplier status were '" + o + "'" });
    for (const d of [0.5, 2, 5, 15, 40, 80, 150]) if (Math.abs(d - part.demand_per_year) > 0.5) tries.push({ field: "demand_per_year", value: d, text: "demand were " + d + " a year" });
    for (const tol of ["coarse", "medium", "fine"]) if (tol !== part.tolerance) tries.push({ field: "tolerance", value: tol, text: "the tolerance class were " + tol });
    for (const cx of [0.2, 0.5, 0.8]) if (Math.abs(cx - part.complexity) > 0.1) tries.push({ field: "complexity", value: cx, text: "complexity were " + cx });
    const out = [];
    for (const tr of tries) {
      const p2 = Object.assign({}, part, { [tr.field]: tr.value });
      const v2 = verdict(technical(p2, rules), business(p2, rules));
      if (v2.label !== current) out.push({ text: tr.text, to: v2.label, dist: distance(part, tr) });
    }
    out.sort((a, b) => a.dist - b.dist);
    return out.slice(0, 3);
  }
  function distance(part, tr) {
    const cur = part[tr.field];
    if (typeof cur === "number") return Math.abs(Math.log((tr.value + 0.5) / (cur + 0.5)));
    const ord = { "OEM active": 0, "end of production": 1, "OEM gone": 2, coarse: 0, medium: 1, fine: 2 };
    return Math.abs((ord[tr.value] ?? 0) - (ord[cur] ?? 0)) * 0.6;
  }

  /* what to ask the OEM before a print right is worth anything */
  function questions(part, t, b) {
    const q = [];
    if (part.data_rights === "OEM owns the data") q.push("Will you license the model, the material specification and the load case, or only sell the part? The print right is worth nothing without the first two.");
    if (part.data_rights === "reverse-engineered, open") q.push("Who carries the design responsibility once the part is reverse-engineered? Name the authority that signs the acceptance tier.");
    if (part.tolerance === "fine") q.push("Which faces are functional? The rest can stay as printed; the functional ones need a machining step and a fixture.");
    if (part.channels) q.push("Where can powder leave the internal channels? A closed channel is a trapped-powder rejection.");
    if (part.criticality === 1) q.push("What is the qualification evidence today (fatigue, pressure, load test)? The printed part must be shown equivalent, not assumed.");
    if (!t.fitCont && t.fitBase) q.push("The part fits the home centre's machine but not the container: is the field use case real, or is this a depot part?");
    if (!t.alloy.am) q.push("No printable equivalent of " + part.material + " is listed. Is a substitution acceptable, and who approves it?");
    if (part.obsolescence === "OEM gone") q.push("Is there a drawing at all? Without one this is a scan-and-redesign project first, a printing project second.");
    if (part.demand_per_year > 30) q.push("At " + part.demand_per_year.toFixed(0) + " a year, would a small tooled batch beat printing? Ask for a quote before deciding.");
    return q;
  }

  /* ---------- act two: economics ---------- */
  function printCost(part, rules, s) {
    const a = rules.assumptions, alloy = rules.alloys[part.material];
    if (!alloy.am) return null;
    const vol = volumeCm3(part, rules);
    const rate = alloy.deposition_cm3_h * (s.rateFactor || 1);
    const height = Math.min(...part.envelope_mm); // lay it flat: the shortest edge up
    const layers = height * 1000 / a.layer_um;
    const buildH = vol * (1 + a.support_fraction) / rate + layers * a.recoat_s / 3600;
    const powderKg = part.mass_g / 1000 * (1 + a.support_fraction) * 1.15; // 15% handling loss, assumed
    const machine = buildH * (s.machineEurH ?? a.machine_eur_h);
    const powder = powderKg * (alloy.powder_eur_kg || 0) * (s.powderFactor || 1);
    const post = (a.support_removal_h_per_complexity * part.complexity + a.machining_h[part.tolerance]) * a.labour_eur_h + (alloy.process === "lpbf" ? a.heat_treatment_eur : 0);
    const qa = part.criticality === 1 ? a.ct_scan_eur : part.criticality === 2 ? a.ct_scan_eur * 0.5 : 0;
    const setup = 1.5 * a.labour_eur_h;
    const unit = machine + powder + post + qa + setup;
    const leadDays = (s.container ? a.am_lead_days_container : a.am_lead_days_base) + Math.ceil(buildH / 20) + (part.tolerance === "fine" ? 2 : 0);
    return { unit, buildH, powderKg, machine, powder, post, qa, setup, leadDays };
  }

  /* expected annual value of printing one part type, and the worth of the print right */
  function economics(part, rules, s) {
    const pc = printCost(part, rules, s);
    if (!pc) return { feasible: false };
    const a = rules.assumptions;
    const downtime = s.downtimeEurDay * ({ 1: 1, 2: 0.4, 3: 0 }[part.criticality]);
    const daysSaved = Math.max(0, part.conv_lead_days - pc.leadDays);
    // per demand event: with probability pStockout the part is not on the shelf and the wait costs downtime
    const perEventDowntime = s.pStockout * daysSaved * downtime;
    const perEventCost = part.conv_cost_eur - pc.unit;
    const events = part.demand_per_year * (s.fleet || 100) / 100; // catalogue demand is per 100 platforms
    const annualCost = events * perEventCost, annualDowntime = events * perEventDowntime;
    const annual = annualCost + annualDowntime;
    const qual = a.qualification_eur[String(part.criticality)];
    const years = s.fleetYears;
    const disc = s.discount || 0.04;
    const pv = annual * (1 - Math.pow(1 + disc, -years)) / disc;
    const net = pv - qual;
    let action;
    if (net <= 0) action = "buy the part";
    else if (part.data_rights === "OEM owns the data") action = "buy the right";
    else action = "print";
    return { feasible: true, pc, downtime, daysSaved, perEventDowntime, perEventCost, events, annualCost, annualDowntime, annual, qual, pv, net, action, rightWorth: Math.max(0, net) };
  }

  /* ---------- act three: readiness ---------- */
  /* A fleet of N platforms. Each printable critical part fails as a Poisson
     process with rate demand/fleet per year. A failure puts the platform
     down until the part arrives: from the shelf (probability 1 - pStockout,
     same day), else by the conventional route (lead days), else printed in
     the container (queue for k printers, build time from the cost model,
     powder stock), else by reachback (printed at home, transport days). */
  function readiness(parts, rules, s) {
    const rnd = rng(s.seed || 7);
    const days = s.days || 90, N = s.fleet, k = s.printers;
    const pool = parts.filter(p => p.eco && p.eco.feasible && (p.part.criticality <= 2)).map(p => ({
      part: p.part, buildH: p.eco.pc.buildH, powderKg: p.eco.pc.powderKg,
      rate: p.part.demand_per_year / 100 / 365 // per platform per day, catalogue demand is per 100 platforms
    }));
    const policies = ["conventional", "container", "container+reachback"];
    const out = {};
    for (const pol of policies) {
      const r2 = rng(s.seed || 7);
      let up = N, downUntil = [], queue = [], printerFree = Array(k).fill(0), powder = s.powderKg, powderUsed = 0, printed = 0, reach = 0, waitedForPowder = 0;
      const series = [], events = [];
      for (let d = 0; d < days; d++) {
        // failures today
        for (let i = 0; i < N; i++) {
          if (downUntil[i] > d) continue;
          for (const pp of pool) {
            if (r2() < pp.rate) {
              const onShelf = r2() > s.pStockout;
              if (onShelf) { downUntil[i] = d + 1; }
              else if (pol === "conventional") { downUntil[i] = d + pp.part.conv_lead_days; }
              else { queue.push({ i, pp, since: d }); downUntil[i] = Infinity; }
              break;
            }
          }
        }
        // serve the queue
        if (pol !== "conventional") {
          queue.sort((a, b) => a.since - b.since);
          const rest = [];
          for (const job of queue) {
            const pIdx = printerFree.findIndex(t => t <= d);
            const reachOK = pol === "container+reachback" && (d - job.since) >= 1 && (queue.length > 2 * k || pIdx < 0 || powder < job.pp.powderKg);
            if (reachOK) { downUntil[job.i] = d + rules.assumptions.am_lead_days_base + Math.ceil(job.pp.buildH / 20) + (s.reachbackDays || 3); reach++; continue; }
            if (pIdx >= 0 && powder >= job.pp.powderKg) {
              const doneDay = d + Math.max(1, Math.ceil((job.pp.buildH + 6) / 24)) + 1; // build plus heat treatment and finishing, one day
              printerFree[pIdx] = doneDay; downUntil[job.i] = doneDay; powder -= job.pp.powderKg; powderUsed += job.pp.powderKg; printed++;
            } else { if (powder < job.pp.powderKg) waitedForPowder++; rest.push(job); }
          }
          queue = rest;
        }
        let downCount = 0; for (let i = 0; i < N; i++) if (downUntil[i] > d) downCount++;
        series.push(1 - downCount / N);
      }
      out[pol] = { series, mean: series.reduce((a, b) => a + b, 0) / series.length, printed, reach, powderUsed, powderLeft: powder, queueEnd: queue.length, waitedForPowder };
    }
    return out;
  }

  /* fleet sweep: where does one container stop keeping up */
  function sweep(parts, rules, s, fleets) {
    return fleets.map(N => {
      const r = readiness(parts, rules, Object.assign({}, s, { fleet: N }));
      return { fleet: N, conventional: r.conventional.mean, container: r.container.mean, reachback: r["container+reachback"].mean, queueEnd: r.container.queueEnd };
    });
  }

  /* ---------- acceptance tier ---------- */
  function tier(inp, rules) {
    const g = rules.gates;
    const reasons = [];
    if (inp.density < g.density_emergency_pct) return { tier: "scrap", rule: "density " + inp.density + "% is below the emergency floor of " + g.density_emergency_pct + "%", signs: "nobody; the part is scrapped and the build data kept" };
    if (inp.deviation > 2) return { tier: "scrap", rule: "dimensional deviation " + inp.deviation + "x the tolerance cannot be machined back", signs: "nobody" };
    const witnessOK = inp.witness === "pass";
    const facesOK = inp.tolerance !== "fine" || inp.machined;
    if (inp.density >= g.density_permanent_pct && inp.deviation <= 1 && witnessOK && facesOK) return { tier: "permanent", rule: "density at or above " + g.density_permanent_pct + "% (the DISCMAM gate), within tolerance, witness coupons passed, functional faces finished", signs: "the design authority, once per part family; then routine release" };
    if (inp.density >= g.density_temporary_pct && inp.deviation <= 1.3 && (witnessOK || inp.criticality >= 2) && (facesOK || inp.criticality === 3)) {
      reasons.push(inp.density < g.density_permanent_pct ? "density " + inp.density + "% is under the permanent gate" : null, !witnessOK ? "no passed witness coupon" : null, !facesOK ? "functional faces not machined" : null, inp.deviation > 1 ? "slightly out of tolerance" : null);
      return { tier: "temporary", rule: reasons.filter(Boolean).join("; ") + "; fit for a limited period, then replaced by a permanent part", signs: "the maintenance officer, with a replacement date on the record" };
    }
    if (inp.mission === "emergency" && inp.density >= g.density_emergency_pct) return { tier: "emergency", rule: "below temporary standards but the platform is mission-stopped and no other route exists; single use, inspected after", signs: "the commander on site, logged, reviewed within 30 days" };
    return { tier: "scrap", rule: "below temporary standards and no emergency declared", signs: "nobody; reprint or order" };
  }

  /* act one and act two, combined into one instruction */
  function integrate(verdictLabel, eco) {
    if (!eco.feasible) return "no printable alloy";
    if (verdictLabel === "leave") return "leave";
    if (eco.net <= 0) return "buy the part";
    if (verdictLabel === "investigate") return "investigate first";
    return eco.action; // print, or buy the right
  }

  return { THRESH, integrate, rng, screen, technical, business, verdict, printCost, economics, readiness, sweep, tier, fitsEnvelope, volumeCm3 };
});
