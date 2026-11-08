/* PalmYield engine: data, insights, built-in answers and the AI connection. No UI code here. */
(function () {
  const LEVERS = {
    harvest_round: { issue: "Long harvest round", short: "Harvest round" },
    road_access: { issue: "Poor road access", short: "Road access" },
    drain_upkeep: { issue: "Drains poorly kept", short: "Drain upkeep" },
    flooding: { issue: "Flooding", short: "Flooding" },
    leaf_k: { issue: "Low leaf K", short: "Leaf potassium" },
    leaf_mg: { issue: "Low leaf Mg", short: "Leaf magnesium" },
    ganoderma: { issue: "Ganoderma", short: "Ganoderma" },
    bagworm: { issue: "Bagworm", short: "Bagworm" },
    missing_palms: { issue: "Missing palms", short: "Missing palms" },
    weeds: { issue: "Weed competition", short: "Weeds" },
  };

  const fmt = {
    n: (x, d = 0) => (x == null || isNaN(x) ? "–" : Number(x).toLocaleString("en-MY", { minimumFractionDigits: d, maximumFractionDigits: d })),
    rm: (x) => {
      if (x == null || isNaN(x)) return "–";
      const a = Math.abs(x);
      if (a >= 1e6) return "RM " + (x / 1e6).toFixed(a >= 1e7 ? 1 : 2) + "m";
      if (a >= 1e4) return "RM " + Math.round(x / 1e3).toLocaleString("en-MY") + "k";
      return "RM " + Math.round(x).toLocaleString("en-MY");
    },
    signed: (x, d = 2) => (x == null ? "–" : (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d)),
  };

  const wavg = (rows, key) => {
    let s = 0, a = 0;
    for (const r of rows) if (r[key] != null) { s += r[key] * r.area; a += r.area; }
    return a ? s / a : NaN;
  };
  const sum = (rows, f) => rows.reduce((s, r) => s + f(r), 0);

  function leverAction(D, lever) {
    const l = D.levers.find((x) => x.lever === lever);
    return l ? l.action : "";
  }

  /* Everything a page needs for the blocks in scope. */
  function scope(D, estate, price) {
    const blocks = estate ? D.blocks.filter((b) => b.estate === estate) : D.blocks;
    const totalT = sum(blocks, (b) => (b.all_levers || 0) * b.area);
    const leverT = Object.keys(LEVERS).map((k) => ({
      lever: k, ...LEVERS[k], action: leverAction(D, k),
      blocks: blocks.filter((b) => b.levers[k]).length,
      t: sum(blocks, (b) => (b.levers[k] || 0) * b.area),
    })).filter((x) => x.t > 0.5).sort((a, b) => b.t - a.t);
    const estates = [...new Set(blocks.map((b) => b.estate))].map((e) => {
      const rows = blocks.filter((b) => b.estate === e);
      return {
        estate: e, region: rows[0].region, blocks: rows.length, area: sum(rows, (b) => b.area),
        yield: wavg(rows, "yield"), vs_peers: wavg(rows, "vs_peers_all"), fc_vs_peers: wavg(rows, "fc_vs_peers"),
        high: rows.filter((b) => b.risk === "High").length, gain_t: sum(rows, (b) => (b.all_levers || 0) * b.area),
      };
    }).sort((a, b) => a.vs_peers - b.vs_peers);
    const ranked = [...blocks].sort((a, b) => a.rank - b.rank);
    const warnings = blocks.filter((b) => b.risk === "High")
      .map((b) => ({ ...b, drop: b.fc - b.yield })).sort((a, b) => a.fc_vs_peers - b.fc_vs_peers);
    return {
      blocks, ranked, estates, leverT, warnings, price,
      totalT, totalRM: totalT * price,
      yield: wavg(blocks, "yield"), peer: wavg(blocks, "peer"), vs_peers: wavg(blocks, "vs_peers"),
      fc: wavg(blocks, "fc"), high: blocks.filter((b) => b.risk === "High").length,
      area: sum(blocks, (b) => b.area),
    };
  }

  /* The management briefing: problem, why, action, expected outcome. */
  function briefing(D, S) {
    const behind = S.blocks.filter((b) => b.vs_peers < -2);
    const worst = S.estates[0];
    const [l1, l2] = S.leverT;
    const top = S.ranked.slice(0, Math.max(10, Math.round(S.blocks.length * 0.1)));
    const topT = sum(top, (b) => b.gain_t || 0);
    const allT = sum(S.blocks, (b) => b.gain_t || 0);
    const next = nextCycleLabel(D);
    return [
      { kind: "problem", title: "The problem", head: `${behind.length} blocks are more than 2 t/ha/yr behind their age peers`,
        body: `Yield is lost block by block, not estate by estate. ${worst ? `${worst.estate} lags most (${fmt.signed(worst.vs_peers)} t/ha/yr vs age peers).` : ""} ${S.high} blocks are forecast high risk for ${next}.` },
      { kind: "why", title: "Why it happens", head: l1 ? `${l1.issue} is the biggest controllable cause` : "No controllable cause found",
        body: l1 ? `It holds back ${l1.blocks} blocks, worth ${fmt.n(l1.t)} t FFB a year.${l2 ? ` Next: ${l2.issue.toLowerCase()} (${fmt.n(l2.t)} t).` : ""} Palm age explains most of the rest and cannot be changed.` : "" },
      { kind: "action", title: "What to do first", head: `Start with the top ${top.length} blocks on the action plan`,
        body: `They hold ${allT ? Math.round((topT / allT) * 100) : 0}% of the value. First: ${top[0] ? `${top[0].action.toLowerCase()} in ${top[0].id}` : "–"}.` },
      { kind: "outcome", title: "Expected outcome", head: `${fmt.rm(topT * S.price)} a year from the top ${top.length} blocks`,
        body: `${fmt.n(topT)} t extra FFB a year at RM ${fmt.n(S.price)}/t. Fixing every controllable issue is worth ${fmt.rm(S.totalRM)} a year, before costs.` },
    ];
  }

  function nextCycleLabel(D) {
    const last = D.meta.cycle_dates[D.meta.cycle_dates.length - 1];
    const d = new Date(last); d.setDate(d.getDate() + 13);
    return "the next harvest cycle (to about " + d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) + ")";
  }

  /* What-if: gain from fixing the chosen levers, capped by the model's all-levers gain. */
  function simulate(blocks, chosen, price) {
    let t = 0;
    const by = {};
    for (const b of blocks) {
      let g = 0;
      for (const k of chosen) { const v = b.levers[k] || 0; g += v; by[k] = (by[k] || 0) + v * b.area; }
      g = Math.min(g, b.all_levers || g);
      t += g * b.area;
    }
    const area = sum(blocks, (b) => b.area);
    return { t, rm: t * price, per_ha: area ? t / area : 0, by };
  }

  /* ---------- Ask the data: built-in answers (Option A, and the fallback in B) ---------- */
  const SUGGESTED = [
    "Which estate needs the most attention?",
    "Which blocks will under-perform next cycle?",
    "What should we fix first, and what is it worth?",
    "Tell me about EST005-D08-B01",
    "Is fertilizer working?",
    "How accurate is the forecast?",
  ];

  const has = (q, ...words) => words.some((w) => new RegExp("\\b" + w, "i").test(q));

  function answer(D, S, q) {
    if (has(q, "brief", "summar", "overview", "this cycle", "needs me", "what needs", "headline", "good morning")) {
      const c = briefing(D, S);
      return { text: c.map((x) => `**${x.title}:** ${x.head}. ${x.body}`).join("\n\n"), chart: "levers" };
    }
    const id = (q.match(/EST\d{3}-D\d{2}-B\d{2}/i) || [])[0];
    if (id) {
      const b = D.blocks.find((x) => x.id === id.toUpperCase());
      if (!b) return { text: `I could not find block ${id.toUpperCase()}. Block IDs look like EST005-D08-B01.` };
      return { text: blockStory(b, S.price), chart: "block", block: b.id };
    }
    const est = D.estates.find((e) => q.toLowerCase().includes(e.estate_name.toLowerCase().replace(" estate", "")));
    if (est) {
      const e = S.estates.find((x) => x.estate === est.estate_name) || scope(D, est.estate_name, S.price).estates[0];
      const top = D.blocks.filter((b) => b.estate === est.estate_name).sort((a, b) => a.rank - b.rank).slice(0, 3);
      return { text: `**${e.estate}** (${e.region}): ${e.blocks} blocks, average yield ${fmt.n(e.yield, 1)} t/ha/yr, ${fmt.signed(e.vs_peers)} t/ha/yr vs age peers. ${e.high} blocks are high risk next cycle; fixing controllable issues is worth about ${fmt.n(e.gain_t)} t (${fmt.rm(e.gain_t * S.price)}) a year.\n\nFirst blocks to fix:\n` + top.map((b) => `- **${b.id}**: ${b.action} (about ${fmt.n(b.gain_t)} t a year)`).join("\n"), chart: "top_blocks" };
    }
    if (has(q, "attention", "worst", "estate", "lag")) {
      const [a, b] = S.estates;
      const most = [...S.estates].sort((x, y) => y.high - x.high)[0];
      return { text: `**${a.estate}** needs the most attention: it lags its age peers most, at ${fmt.signed(a.vs_peers)} t/ha/yr${b ? `, followed by ${b.estate} (${fmt.signed(b.vs_peers)})` : ""}. **${most.estate}** has the most high-risk blocks (${most.high}). Open the Early warnings and Action plan pages for the blocks.`, chart: "estates" };
    }
    if (has(q, "risk", "under-perform", "underperform", "next cycle", "forecast", "warning", "drop")) {
      if (has(q, "accura", "trust", "error", "good")) return accuracy(D);
      const w = S.warnings.slice(0, 5);
      return { text: `**${S.high} blocks** are forecast high risk next cycle (well below their age peers). The five furthest behind:\n` + w.map((b) => `- **${b.id}** (${b.estate}): forecast ${fmt.n(b.fc, 1)} t/ha/yr, ${fmt.signed(b.fc_vs_peers)} vs peers. Fix: ${b.action.toLowerCase()}`).join("\n") + `\n\nAct now, before the harvest: each has a costed first action.`, chart: "risk" };
    }
    if (has(q, "accura", "trust", "model", "mae", "error")) return accuracy(D);
    if (has(q, "fertili", "nutrient", "potassium", "magnesium", "leaf")) {
      const lows = D.feeding.filter((f) => f.situation.startsWith("Low leaf despite"));
      return { text: `Fertilizer mostly reaches the palms: ${D.nutrients.map((n) => `${n.share_below_pct}% of samples are below the ${n.nutrient} critical level`).slice(0, 3).join("; ")}. Where leaf levels stay low **despite** fertilizer, yield trails peers (${lows.map((f) => `${f.nutrient}: ${fmt.signed(f.yield_vs_age_peers)} t/ha/yr`).join(", ")}): check application timing and drainage there before buying more.`, chart: "drivers" };
    }
    if (has(q, "ganoderma", "bagworm", "pest", "disease", "treat")) {
      const t = D.treatments.filter((x) => x.change_pct_points < 0).sort((a, b) => a.change_pct_points - b.change_pct_points).slice(0, 3);
      const g = S.leverT.find((l) => l.lever === "ganoderma");
      return { text: `${g ? `Ganoderma control is worth about ${fmt.n(g.t)} t FFB a year across ${g.blocks} blocks. ` : ""}The treatments that cut incidence most:\n` + t.map((x) => `- ${x.treatment_program} on ${x.pest}: ${fmt.signed(x.change_pct_points)} points next cycle (${x.block_cycles} block-cycles)`).join("\n"), chart: "levers" };
    }
    if (has(q, "harvest", "round", "interval")) {
      const l = S.leverT.find((x) => x.lever === "harvest_round");
      return { text: `Long harvest rounds cost yield: good practice is 7–10 days. ${l ? `Cutting rounds to 10 days is worth about ${fmt.n(l.t)} t FFB (${fmt.rm(l.t * S.price)}) a year across ${l.blocks} blocks.` : ""} Note that raw yield per cycle flatters slow rounds; this app annualises yield to compare fairly.`, chart: "levers" };
    }
    if (has(q, "age", "old", "young", "replant")) {
      const peak = [...D.age_curve].sort((a, b) => b.y - a.y)[0];
      return { text: `Palm age is the biggest driver of yield. It peaks at **${peak.palm_age_band}** (median ${fmt.n(peak.y, 1)} t/ha/yr). That is why every block is compared with its **age peers**, so old blocks are not blamed for their age.`, chart: "age_curve" };
    }
    if (has(q, "fix", "first", "worth", "value", "rm", "money", "action", "recommend", "priorit", "lever", "what should")) {
      const [a, b, c] = S.leverT;
      return { text: `Fixing every controllable issue is worth **${fmt.rm(S.totalRM)} a year** (${fmt.n(S.totalT)} t FFB), before costs. Biggest levers:\n` + [a, b, c].filter(Boolean).map((l) => `- **${l.issue}**: ${fmt.n(l.t)} t a year, ${l.blocks} blocks. Action: ${l.action}`).join("\n") + `\n\nStart with the top-ranked blocks on the Action plan; the top 10% hold about a fifth of the value.`, chart: "levers" };
    }
    if (has(q, "driver", "why", "cause", "explain")) {
      return { text: "The main drivers of yield, from a model checked on blocks it never saw:\n" + D.drivers.slice(0, 5).map((d) => `- ${d.label}: ${d.share_pct}% of explained variation`).join("\n") + "\n\nPalm age cannot be changed; the controllable ones become the levers on the Action plan.", chart: "drivers" };
    }
    if (has(q, "hello", "hi", "help", "what can")) {
      return { text: "I answer questions about the yield results: estates, blocks (e.g. EST005-D08-B01), risk next cycle, what to fix first and its value, fertilizer, pests, harvest rounds and forecast accuracy." };
    }
    return { text: `Here is the summary for the blocks in view: average yield ${fmt.n(S.yield, 1)} t/ha/yr (${fmt.signed(S.vs_peers)} vs age peers), ${S.high} high-risk blocks next cycle, and ${fmt.rm(S.totalRM)} a year at stake.\n\nTry asking about an estate, a block ID, risk, what to fix first, fertilizer or pests.`, chart: "estates" };
  }

  function accuracy(D) {
    const m = D.forecast_metrics;
    return { text: `The forecast (${m.chosen_model}) is tested on blocks it never saw: average error **${m.model.mae} t/ha/yr** (R² ${m.model.r2}), ${m.mae_improvement_vs_last_cycle_pct}% better than assuming "same as last cycle". Each forecast has an 80% range (±${m.range_80_half_width} t/ha/yr), and ${m.range_80_coverage_pct}% of actual results fell inside it.`, chart: "accuracy" };
  }

  function blockStory(b, price) {
    const lev = Object.entries(b.levers).sort((x, y) => y[1] - x[1]);
    return `**${b.id}** (${b.estate}, ${b.division}; ${b.age_band}, ${fmt.n(b.area, 1)} ha)\n\n` +
      `- **Now:** ${fmt.n(b.yield, 1)} t/ha/yr, ${fmt.signed(b.vs_peers)} vs age peers (${fmt.n(b.peer, 1)}).\n` +
      `- **Next cycle:** forecast ${fmt.n(b.fc, 1)} t/ha/yr (80% range ${fmt.n(b.fc_low, 1)}–${fmt.n(b.fc_high, 1)}), risk **${b.risk}**.\n` +
      `- **Why:** ${b.issues || "no controllable issue stands out"}.\n` +
      `- **Do first:** ${b.action}. Worth about ${fmt.n(b.gain_t)} t FFB (${fmt.rm(b.gain_t * price)}) a year; rank ${b.rank} of 640.` +
      (lev.length > 1 ? `\n- **Other levers:** ${lev.slice(1, 4).map(([k, v]) => `${LEVERS[k].short} ${fmt.n(v, 2)} t/ha/yr`).join(", ")}.` : "");
  }

  /* ---------- AI (Option B): grounded on a results brief; key stays in this browser ---------- */
  const MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"];
  const SYSTEM = "You are PalmYield's assistant for oil palm plantation managers. Answer ONLY from the RESULTS below; never invent numbers. " +
    "Be brief and practical: lead with the answer, then the reason, then the action and its expected value in RM. Use short bullet points and markdown bold. " +
    "If the RESULTS do not cover the question, say so. The data is a synthetic sample. " +
    "If a chart would help, end with one line 'CHART: <name>' using one of: estates, risk, levers, top_blocks, drivers, age_curve, accuracy, block.";

  function context(D, S, q) {
    const lines = [
      `Scope: ${S.blocks.length} blocks, ${S.estates.length} estates. FFB price RM ${S.price}/t. Data: synthetic sample, ${D.meta.cycles} harvest cycles.`,
      `Average yield ${fmt.n(S.yield, 2)} t/ha/yr; vs age peers ${fmt.signed(S.vs_peers)}; high-risk blocks next cycle ${S.high}; value of fixing all controllable issues ${fmt.n(S.totalT)} t = ${fmt.rm(S.totalRM)} a year before costs.`,
      "Estates (vs age peers, high-risk blocks, gain t/yr): " + S.estates.map((e) => `${e.estate} ${fmt.signed(e.vs_peers)}, ${e.high}, ${fmt.n(e.gain_t)}`).join("; "),
      "Levers (issue: t/yr, blocks, action): " + S.leverT.map((l) => `${l.issue}: ${fmt.n(l.t)}, ${l.blocks}, ${l.action}`).join("; "),
      "Top 10 blocks (rank, id, estate, issues, first action, gain t/yr, risk): " + S.ranked.slice(0, 10).map((b) => `${b.rank} ${b.id} ${b.estate} [${b.issues}] ${b.action} ${b.gain_t} ${b.risk}`).join(" | "),
      "Most at risk next cycle (id, forecast, vs peers): " + S.warnings.slice(0, 8).map((b) => `${b.id} ${b.fc} ${fmt.signed(b.fc_vs_peers)}`).join("; "),
      "Drivers (share %): " + D.drivers.slice(0, 8).map((d) => `${d.label} ${d.share_pct}`).join("; "),
      "Patterns tested: " + D.patterns.map((p) => `${p.pattern}: ${p.verdict} (${p.evidence})`).join("; "),
      "Nutrients: " + D.nutrients.map((n) => `${n.nutrient} critical ${n.critical_level_pct}%, ${n.share_below_pct}% below`).join("; "),
      "Fertilizer vs leaf: " + D.feeding.map((f) => `${f.nutrient} ${f.situation}: ${f.share_pct}% of block-cycles, yield vs peers ${f.yield_vs_age_peers}`).join("; "),
      "Treatments (pest, program, change in incidence points): " + D.treatments.map((t) => `${t.pest} ${t.treatment_program} ${t.change_pct_points}`).join("; "),
      `Forecast accuracy: MAE ${D.forecast_metrics.model.mae} t/ha/yr, R2 ${D.forecast_metrics.model.r2}, 80% range coverage ${D.forecast_metrics.range_80_coverage_pct}%.`,
    ];
    const id = (q.match(/EST\d{3}-D\d{2}-B\d{2}/i) || [])[0];
    const b = id && D.blocks.find((x) => x.id === id.toUpperCase());
    if (b) lines.push("Block asked about: " + blockStory(b, S.price).replace(/\*\*/g, "") + " Signals: " + JSON.stringify(b.signals) + " History t/ha/yr by cycle: " + b.history.join(", "));
    return lines.join("\n");
  }

  async function askGemini(key, D, S, q, history) {
    const contents = [...history.slice(-6).map((m) => ({ role: m.role === "user" ? "user" : "model", parts: [{ text: m.text }] })),
      { role: "user", parts: [{ text: q }] }];
    const body = { systemInstruction: { parts: [{ text: SYSTEM + "\n\nRESULTS:\n" + context(D, S, q) }] }, contents,
      generationConfig: { temperature: 0.2, maxOutputTokens: 900 } };
    let last = "";
    for (const m of MODELS) {
      try {
        const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), 30000);
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent`, {
          method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": key }, body: JSON.stringify(body), signal: ctrl.signal });
        clearTimeout(timer);
        const j = await r.json();
        if (!r.ok) { last = (j.error && j.error.message) || r.statusText; if (r.status === 400 || r.status === 403) break; continue; }
        const text = (j.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("").trim();
        if (text) return { text, model: m };
        last = "empty answer";
      } catch (e) { last = e.name === "AbortError" ? "timed out" : e.message; }
    }
    throw new Error(last || "no answer");
  }

  /* Streaming version: calls onText(wholeTextSoFar) as the answer arrives, like a chat app. */
  async function askGeminiStream(key, D, S, q, history, onText) {
    const contents = [...history.slice(-6).map((m) => ({ role: m.role === "user" ? "user" : "model", parts: [{ text: m.text }] })),
      { role: "user", parts: [{ text: q }] }];
    const body = JSON.stringify({ systemInstruction: { parts: [{ text: SYSTEM + "\n\nRESULTS:\n" + context(D, S, q) }] }, contents,
      generationConfig: { temperature: 0.2, maxOutputTokens: 900 } });
    let last = "";
    for (const m of MODELS) {
      let text = "";
      try {
        const ctrl = new AbortController(); let timer = setTimeout(() => ctrl.abort(), 30000);
        const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:streamGenerateContent?alt=sse`, {
          method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": key }, body, signal: ctrl.signal });
        if (!r.ok) { clearTimeout(timer); const j = await r.json().catch(() => ({})); last = (j.error && j.error.message) || r.statusText; if (r.status === 400 || r.status === 403) break; continue; }
        const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
        for (;;) {
          const { value, done } = await reader.read(); if (done) break;
          clearTimeout(timer); timer = setTimeout(() => ctrl.abort(), 30000);
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
            if (!line.startsWith("data:")) continue;
            try { const j = JSON.parse(line.slice(5)); text += (j.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join(""); onText(text); } catch { /* partial line */ }
          }
        }
        clearTimeout(timer);
        if (text.trim()) return { text: text.trim(), model: m };
        last = "empty answer";
      } catch (e) {
        if (text.trim()) return { text: text.trim(), model: m };
        last = e.name === "AbortError" ? "timed out" : e.message;
      }
    }
    throw new Error(last || "no answer");
  }

  /* Follow-up questions to offer after an answer, by topic. */
  function followUps(q, chart, D, S) {
    const top = S.ranked[0] ? S.ranked[0].id : "EST005-D08-B01";
    const w = S.warnings[0] ? S.warnings[0].id : top;
    const worst = S.estates[0] ? S.estates[0].estate.replace(" Estate", "") : "Sepakau 2";
    const by = {
      estates: [`What should ${worst} fix first?`, "Which blocks will under-perform next cycle?"],
      risk: [`Tell me about ${w}`, "What should we fix first, and what is it worth?"],
      levers: [`Tell me about ${top}`, "Which estate needs the most attention?"],
      block: ["What should we fix first, and what is it worth?", "How accurate is the forecast?"],
      drivers: ["Is fertilizer working?", "Which estate needs the most attention?"],
      accuracy: ["Which blocks will under-perform next cycle?", "Brief me on this cycle"],
      age_curve: ["What should we fix first, and what is it worth?", "Which blocks will under-perform next cycle?"],
      top_blocks: [`Tell me about ${top}`, "Which blocks will under-perform next cycle?"],
    };
    return (by[chart] || ["Brief me on this cycle", "What should we fix first, and what is it worth?"]).filter((x) => x.toLowerCase() !== q.toLowerCase());
  }

  function splitChart(text) {
    const m = text.match(/\n?\s*CHART:\s*([a-z_]+)\s*$/i);
    return m ? { text: text.slice(0, m.index).trim(), chart: m[1].toLowerCase() } : { text, chart: null };
  }

  window.PY = { LEVERS, fmt, scope, briefing, simulate, answer, SUGGESTED, askGemini, askGeminiStream, followUps, splitChart, blockStory, nextCycleLabel, wavg };
})();
