/* PalmYield web app: screens. Data logic lives in engine.js (window.PY). */
(function () {
  const { useState, useEffect, useRef, useMemo, useCallback } = React;
  const html = htm.bind(React.createElement);
  const { fmt, LEVERS } = PY;
  const STREAMLIT = "https://palm-yield-poc-gjzqnhwncr2o5pr78ichfq.streamlit.app/";

  /* ---------- Storage: per-browser, wrapped so private windows still work ---------- */
  const store = {
    get(k, d) { try { const v = localStorage.getItem("py." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("py." + k, JSON.stringify(v)); } catch { /* storage blocked */ } },
  };
  function usePersist(key, init) {
    const [v, setV] = useState(() => store.get(key, init));
    const set = useCallback((x) => setV((old) => { const n = typeof x === "function" ? x(old) : x; store.set(key, n); return n; }), [key]);
    return [v, set];
  }

  const ROLES = {
    manager: { name: "Aina Rahman", role: "Estate manager", initials: "AR" },
    agronomist: { name: "Daniel Wong", role: "Agronomist", initials: "DW" },
    admin: { name: "Siti Hassan", role: "Administrator", initials: "SH" },
  };

  /* ---------- Router ---------- */
  function useRoute() {
    const read = () => (location.hash.replace(/^#\/?/, "") || "home").split("/");
    const [r, setR] = useState(read);
    useEffect(() => { const f = () => { setR(read()); window.scrollTo(0, 0); }; addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
    return r;
  }
  const go = (path) => { location.hash = "#/" + path; };

  /* ---------- Small pieces ---------- */
  function Md({ text }) {
    const out = []; let list = [];
    const inline = (s, k) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => p.startsWith("**") ? html`<b key=${k + "-" + i}>${p.slice(2, -2)}</b>` : p);
    const flush = (k) => { if (list.length) { out.push(html`<ul key=${"u" + k}>${list.map((l, i) => html`<li key=${i}>${inline(l, k + "l" + i)}</li>`)}</ul>`); list = []; } };
    (text || "").split("\n").forEach((line, i) => {
      const t = line.trim();
      if (/^[-*•]\s+/.test(t)) { list.push(t.replace(/^[-*•]\s+/, "")); return; }
      flush(i);
      if (!t) return;
      const h = t.replace(/^#{1,4}\s+/, "");
      out.push(html`<p key=${i} style=${{ margin: "4px 0" }}>${h !== t ? html`<b>${inline(h, i)}</b>` : inline(t, i)}</p>`);
    });
    flush("end");
    return html`<div>${out}</div>`;
  }

  function Chart({ option, height = 300 }) {
    const el = useRef(null), inst = useRef(null);
    useEffect(() => {
      inst.current = echarts.init(el.current, null, { renderer: "svg" });
      const ro = new ResizeObserver(() => inst.current && inst.current.resize());
      ro.observe(el.current);
      return () => { ro.disconnect(); inst.current.dispose(); inst.current = null; };
    }, []);
    useEffect(() => { inst.current && inst.current.setOption(option, true); }, [option]);
    return html`<div ref=${el} style=${{ width: "100%", height: height + "px" }}></div>`;
  }

  const AX = { axisLine: { lineStyle: { color: "#D9D5CA" } }, axisLabel: { color: "#4A5650", fontSize: 11 }, splitLine: { lineStyle: { color: "#EEEBE3" } } };
  const base = (o) => ({ textStyle: { fontFamily: "Inter" }, grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true }, tooltip: { trigger: "axis", axisPointer: { type: "shadow" } }, ...o });
  const hbar = (labels, values, colors, unit, fmtV = (v) => fmt.n(v, 2)) => base({
    grid: { left: 8, right: Math.min(150, 14 + 6.2 * Math.max(...values.map((v) => String(fmtV(v)).length), 4)), top: 16, bottom: 8, containLabel: true },
    xAxis: { type: "value", ...AX, name: unit, nameLocation: "end", nameTextStyle: { color: "#7A847E", fontSize: 11 } },
    yAxis: { type: "category", data: labels, ...AX, axisTick: { show: false } },
    series: [{ type: "bar", data: values.map((v, i) => ({ value: v, itemStyle: { color: Array.isArray(colors) ? colors[i] : colors, borderRadius: 3 } })), barMaxWidth: 18,
      label: { show: true, position: "right", fontSize: 11, color: "#4A5650", formatter: (p) => fmtV(p.value) } }],
  });

  const CHARTS = {
    estates: (D, S) => { const e = [...S.estates].reverse(); return { title: "Estates: yield vs age peers (t/ha/yr)", option: hbar(e.map((x) => x.estate.replace(" Estate", "")), e.map((x) => +x.vs_peers.toFixed(2)), e.map((x) => (x.vs_peers < 0 ? "#C0392B" : "#2E7D4F")), "t/ha/yr") }; },
    risk: (D, S) => { const w = S.warnings.slice(0, 12).reverse(); return { title: "Blocks most at risk next cycle: forecast vs age peers (t/ha/yr)", option: hbar(w.map((b) => b.id), w.map((b) => b.fc_vs_peers), "#C0392B", "t/ha/yr") }; },
    levers: (D, S) => { const l = S.leverT.slice(0, 8).reverse(); return { title: "Value of fixing each issue (t FFB a year)", option: hbar(l.map((x) => x.issue), l.map((x) => Math.round(x.t)), "#2E7D4F", "t/yr", (v) => fmt.n(v) + " t · " + fmt.rm(v * S.price)) }; },
    top_blocks: (D, S) => { const t = S.ranked.slice(0, 10).reverse(); return { title: "Top 10 blocks by value of first action (t FFB a year)", option: hbar(t.map((b) => `#${b.rank} ${b.id}`), t.map((b) => b.gain_t), "#C7781F", "t/yr", (v) => fmt.n(v, 0) + " t") }; },
    drivers: (D) => { const d = D.drivers.slice(0, 10).reverse(); return { title: "What drives yield (% of explained variation)", option: hbar(d.map((x) => x.label), d.map((x) => x.share_pct), "#2F6FB0", "%", (v) => v + "%") }; },
    age_curve: (D) => ({ title: "Median yield by palm age (t/ha/yr)", option: base({ tooltip: { trigger: "axis" }, xAxis: { type: "category", data: D.age_curve.map((a) => a.palm_age_band.replace(/ \(/, "\n(")), ...AX, axisLabel: { ...AX.axisLabel, fontSize: 10, interval: 0 } }, yAxis: { type: "value", ...AX }, series: [{ type: "line", smooth: true, data: D.age_curve.map((a) => +a.y.toFixed(1)), color: "#2E7D4F", areaStyle: { color: "rgba(46,125,79,.12)" }, symbolSize: 7, label: { show: true, fontSize: 10, position: "top" } }] }) }),
    accuracy: (D) => ({ title: "Forecast vs actual on unseen blocks (t/ha/yr)", option: base({ tooltip: { trigger: "item", formatter: (p) => `Actual ${fmt.n(p.value[0], 1)} · forecast ${fmt.n(p.value[1], 1)}` }, xAxis: { type: "value", name: "Actual", min: 8, max: 36, ...AX }, yAxis: { type: "value", name: "Forecast", min: 8, max: 36, ...AX }, series: [{ type: "scatter", symbolSize: 5, data: D.cv_sample.map((c) => [c.actual_next, c.predicted]), itemStyle: { color: "rgba(47,111,176,.45)" } }, { type: "line", data: [[8, 8], [36, 36]], symbol: "none", lineStyle: { color: "#C7781F", type: "dashed" } }] }) }),
    block: (D, S, b) => {
      if (!b) return null;
      const cats = [...D.meta.cycle_dates.map((d, i) => `C${i + 1}`), "Next"];
      return { title: `${b.id}: yield by harvest cycle and next-cycle forecast (t/ha/yr)`, option: base({
        tooltip: { trigger: "axis" }, legend: { bottom: 0, data: ["Actual", "Age peers", "Forecast", "80% range"], textStyle: { fontSize: 11 } }, grid: { left: 8, right: 24, top: 16, bottom: 30, containLabel: true },
        xAxis: { type: "category", data: cats, ...AX },
        yAxis: { type: "value", ...AX, min: (v) => Math.floor(Math.min(v.min, b.fc_low) - 1), max: (v) => Math.ceil(Math.max(v.max, b.fc_high, b.peer) + 1) },
        series: [
          { name: "_base", type: "bar", stack: "range", data: [...b.history.map(() => null), b.fc_low], itemStyle: { color: "transparent" }, barWidth: 14, tooltip: { show: false }, silent: true },
          { name: "80% range", type: "bar", stack: "range", data: [...b.history.map(() => null), +(b.fc_high - b.fc_low).toFixed(2)], itemStyle: { color: "rgba(199,120,31,.28)", borderRadius: 4 }, barWidth: 14, tooltip: { valueFormatter: () => `${fmt.n(b.fc_low, 1)}–${fmt.n(b.fc_high, 1)}` } },
          { name: "Actual", type: "line", data: [...b.history, null], color: "#12241C", symbolSize: 7 },
          { name: "Age peers", type: "line", data: cats.map(() => b.peer), color: "#7A847E", lineStyle: { type: "dashed" }, symbol: "none" },
          { name: "Forecast", type: "scatter", data: [...b.history.map(() => null), b.fc], color: b.risk === "High" ? "#C0392B" : "#C7781F", symbolSize: 14, z: 5 },
        ] }) };
    },
  };

  function ChartCard({ D, S, name, block, height = 300, bare }) {
    const spec = useMemo(() => (CHARTS[name] ? CHARTS[name](D, S, block) : null), [name, S, block]);
    if (!spec) return null;
    const body = html`<div><div class="small muted" style=${{ marginBottom: 6, fontWeight: 600 }}>${spec.title}</div><${Chart} option=${spec.option} height=${height} /></div>`;
    return bare ? body : html`<div class="card">${body}</div>`;
  }

  window.PYUI = { Md, ChartCard, CHARTS };

  const Kpi = ({ label, value, note, cls }) => html`<div class="card kpi"><div class="label">${label}</div><div class=${"value " + (cls || "")}>${value}</div>${note && html`<div class="note">${note}</div>`}</div>`;
  const Head = ({ eyebrow, title, sub, children }) => html`<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>${sub && html`<p class="sub">${sub}</p>`}</div><div class="row">${children}</div></div>`;
  const Risk = ({ r }) => html`<span class=${"risk " + r}>${r}</span>`;
  const STATUS = { todo: "To do", inprog: "In progress", done: "Done" };
  const OWNERS = ["Estate manager", "Harvest team", "Field assistant", "Agronomist", "Maintenance team"];

  function download(name, rows) {
    const head = Object.keys(rows[0] || {});
    const csv = [head.join(","), ...rows.map((r) => head.map((h) => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  /* ---------- Pages ---------- */
  function Home({ D, S, ctx }) {
    const brief = useMemo(() => PY.briefing(D, S), [S]);
    const wo = Object.values(ctx.orders);
    const woOpen = wo.filter((w) => w.status !== "done"); const woDone = wo.filter((w) => w.status === "done");
    const [narr, setNarr] = useState(null); const [busy, setBusy] = useState(false);
    const aiOn = ctx.option === "B" && ctx.key;
    async function aiBrief() {
      setBusy(true);
      try {
        const r = await PY.askGemini(ctx.key, D, S, "Write a management briefing for this week in 4 short sentences: the problem, why it is happening, the first actions, and the expected outcome in RM. Name the estates and blocks. No chart.", []);
        setNarr(PY.splitChart(r.text).text); ctx.log("Briefing", true);
      } catch (e) { setNarr("The AI service did not answer (" + e.message + "). The briefing above is computed from the results and stays valid."); ctx.log("Briefing", false); }
      setBusy(false);
    }
    return html`<div>
      <${Head} eyebrow="Dashboard" title="What needs you this cycle" sub=${`${S.blocks.length} blocks in ${S.estates.length} estates · last harvest cycle ended ${new Date(D.meta.cycle_dates.at(-1)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}`} />
      <div class="brief">
        <div class="brief-top"><div><div class="ai-tag">✦ AUTOMATED ANALYSIS · UPDATED EVERY HARVEST CYCLE</div><h2>Management briefing</h2></div>
          <div class="row">${ctx.option === "B" && html`<button class="btn sm" onClick=${aiOn ? aiBrief : () => go("settings")} disabled=${busy}>${busy ? "Writing…" : aiOn ? "✦ Write it with AI" : "✦ Switch on AI in Settings"}</button>`}
          <button class="btn sm primary" onClick=${() => go("actions")}>Open action plan →</button></div></div>
        <div class="brief-grid">${brief.map((c) => html`<div key=${c.kind} class=${"brief-card " + c.kind}><div class="k">${c.title}</div><div class="h">${c.head}</div><div class="b">${c.body}</div></div>`)}</div>
        ${narr && html`<div class="ai-narr"><b>✦ AI briefing</b><${Md} text=${narr} /></div>`}
      </div>
      <div class="grid g4" style=${{ marginTop: 16 }}>
        <${Kpi} label="Yield, latest cycle (annualised)" value=${fmt.n(S.yield, 1) + " t/ha"} note=${html`<span class=${S.vs_peers < 0 ? "down" : "up"}>${fmt.signed(S.vs_peers)}</span> t/ha/yr vs age peers`} />
        <${Kpi} label="Value at stake" value=${fmt.rm(S.totalRM)} note=${fmt.n(S.totalT) + " t FFB a year, before costs"} />
        <${Kpi} label="Early warnings" value=${S.high} cls="down" note="blocks at high risk next cycle" />
        <${Kpi} label="Action plan progress" value=${`${woDone.length} / ${wo.length}`} note=${wo.length ? `${fmt.rm(woOpen.reduce((s, w) => s + w.gain_t, 0) * S.price)} a year in open work orders` : "No work orders yet: create them on the action plan"} />
      </div>
      <div class="grid g-wide" style=${{ marginTop: 16 }}>
        <div class="card"><div class="card-head"><div><h2>Early warnings: act before the harvest</h2><p>Blocks forecast furthest below their age peers next cycle</p></div><a class="btn sm" href="#/warnings">See all ${S.high}</a></div>
          <div class="list">${S.warnings.slice(0, 5).map((b) => html`<div class="li" key=${b.id}><${Risk} r=${b.risk} /><div class="main-t"><b><a href=${"#/block/" + b.id}>${b.id}</a> · ${b.estate}</b><span>Forecast ${fmt.n(b.fc, 1)} t/ha/yr (${fmt.signed(b.fc_vs_peers)} vs peers). Cause: ${b.issues || "age and site"}.</span></div>
            <${WoButton} b=${b} ctx=${ctx} /></div>`)}</div></div>
        <${ChartCard} D=${D} S=${S} name="levers" height=${280} />
      </div>
      <div class="grid g2" style=${{ marginTop: 16 }}>
        <div class="card"><div class="card-head"><div><h2>Top actions by value</h2><p>The first action for the highest-value blocks</p></div><a class="btn sm" href="#/actions">Action plan</a></div>
          <div class="list">${S.ranked.slice(0, 5).map((b) => html`<div class="li" key=${b.id}><div class="main-t"><b>#${b.rank} <a href=${"#/block/" + b.id}>${b.id}</a></b><span>${b.action}</span></div><div class="amt">${fmt.rm(b.gain_t * S.price)}<div class="small muted">a year</div></div></div>`)}</div></div>
        <${ChartCard} D=${D} S=${S} name="estates" height=${300} />
      </div>
          </div>`;
  }

  function WoButton({ b, ctx, label }) {
    const has = ctx.orders[b.id];
    return has ? html`<a class="btn sm" href="#/actions/board"><span class=${"status " + has.status}>${STATUS[has.status]}</span></a>`
      : html`<button class="btn sm primary" onClick=${() => ctx.createOrders([b])}>${label || "+ Work order"}</button>`;
  }

  function Warnings({ D, S, ctx }) {
    const [risk, setRisk] = useState("High");
    const rows = useMemo(() => S.blocks.filter((b) => risk === "All" || b.risk === risk).sort((a, b) => a.fc_vs_peers - b.fc_vs_peers), [S, risk]);
    const [sel, setSel] = useState(null);
    const b = sel ? D.blocks.find((x) => x.id === sel) : rows[0];
    return html`<div>
      <${Head} eyebrow="Predict" title="Early warnings" sub=${`The forecast for ${PY.nextCycleLabel(D)}, per block, with an 80% range. Act on these blocks before the yield is lost.`}>
        <div class="seg">${["High", "Medium", "Low", "All"].map((r) => html`<button key=${r} class=${risk === r ? "on" : ""} onClick=${() => setRisk(r)}>${r}</button>`)}</div>
        <button class="btn" onClick=${() => ctx.createOrders(rows.filter((x) => x.risk === "High").slice(0, 10))}>+ Work orders for top 10</button>
      </${Head}>
      <div class="grid g4" style=${{ marginBottom: 16 }}>
        <${Kpi} label="High risk next cycle" value=${S.high} cls="down" note="well below age peers" />
        <${Kpi} label="Forecast yield" value=${fmt.n(S.fc, 1) + " t/ha"} note=${`${fmt.signed(S.fc - S.yield)} vs now`} />
        <${Kpi} label="Forecast error" value=${"±" + fmt.n(D.forecast_metrics.model.mae, 2)} note="t/ha/yr on unseen blocks" />
        <${Kpi} label="Range coverage" value=${D.forecast_metrics.range_80_coverage_pct + "%"} note="of results inside the 80% range" />
      </div>
      <div class="grid g-wide">
        <div class="card"><div class="card-head"><h2>${rows.length} blocks</h2><button class="btn sm" onClick=${() => download("early_warnings.csv", rows.map((x) => ({ block: x.id, estate: x.estate, risk: x.risk, now: x.yield, forecast: x.fc, low: x.fc_low, high: x.fc_high, vs_peers: x.fc_vs_peers, cause: x.issues, action: x.action })))}>⇩ Export</button></div>
          <div class="table-wrap scroll"><table class="t"><thead><tr><th>Block</th><th>Estate</th><th>Risk</th><th class="num">Now</th><th class="num">Forecast</th><th class="num">vs peers</th><th>Cause</th></tr></thead>
          <tbody>${rows.slice(0, 200).map((x) => html`<tr key=${x.id} class="click" onClick=${() => setSel(x.id)} style=${b && b.id === x.id ? { background: "#F1F7F3" } : null}><td><b>${x.id}</b></td><td>${x.estate.replace(" Estate", "")}</td><td><${Risk} r=${x.risk} /></td><td class="num">${fmt.n(x.yield, 1)}</td><td class="num">${fmt.n(x.fc, 1)}</td><td class="num">${fmt.signed(x.fc_vs_peers)}</td><td class="small">${x.issues || "–"}</td></tr>`)}</tbody></table></div></div>
        ${b && html`<div class="card"><div class="card-head"><div><h2>${b.id}</h2><p>${b.estate} · ${b.age_band}</p></div><${Risk} r=${b.risk} /></div>
          <${ChartCard} D=${D} S=${S} name="block" block=${b} height=${250} bare=${true} />
          <p style=${{ margin: "10px 0" }}><b>Do first:</b> ${b.action}. Worth ${fmt.rm(b.gain_t * S.price)} a year.</p>
          <div class="row"><${WoButton} b=${b} ctx=${ctx} /><a class="btn sm" href=${"#/block/" + b.id}>Block profile</a><button class="btn sm" onClick=${() => ctx.ask(`Why is ${b.id} at risk, and what should we do first?`)}>✦ Ask about it</button></div></div>`}
      </div></div>`;
  }

  function Actions({ D, S, ctx, sub }) {
    const tab = sub === "board" ? "board" : "plan";
    const [n, setN] = useState(50);
    const [lever, setLever] = useState("");
    const rows = useMemo(() => S.ranked.filter((b) => !lever || b.levers[lever]), [S, lever]);
    const orders = Object.values(ctx.orders).filter((o) => !ctx.estate || o.estate === ctx.estate);
    const sumRM = (arr) => fmt.rm(arr.reduce((s, o) => s + o.gain_t, 0) * S.price);
    return html`<div>
      <${Head} eyebrow="Recommend" title="Action plan" sub="Every block ranked by the value of its first action. Turn recommendations into work orders, assign an owner, and track them to done.">
        <div class="seg"><button class=${tab === "plan" ? "on" : ""} onClick=${() => go("actions")}>Recommendations</button><button class=${tab === "board" ? "on" : ""} onClick=${() => go("actions/board")}>Work orders (${orders.length})</button></div>
      </${Head}>
      ${tab === "plan" ? html`<div>
        <div class="grid g4" style=${{ marginBottom: 16 }}>
          <${Kpi} label="Value of all actions" value=${fmt.rm(S.ranked.reduce((s, b) => s + b.gain_t, 0) * S.price)} note="a year, before costs" />
          <${Kpi} label="Top 10% of blocks" value=${fmt.rm(S.ranked.slice(0, Math.round(S.ranked.length / 10)).reduce((s, b) => s + b.gain_t, 0) * S.price)} note=${Math.round(S.ranked.length / 10) + " blocks to start with"} />
          <${Kpi} label="Biggest lever" value=${S.leverT[0] ? S.leverT[0].short : "–"} note=${S.leverT[0] ? fmt.rm(S.leverT[0].t * S.price) + " a year" : ""} />
          <${Kpi} label="Open work orders" value=${orders.filter((o) => o.status !== "done").length} note=${sumRM(orders.filter((o) => o.status !== "done")) + " a year in progress"} />
        </div>
        <div class="card"><div class="card-head"><div class="row"><select value=${lever} onChange=${(e) => setLever(e.target.value)} style=${{ font: "inherit", border: "1px solid var(--line)", borderRadius: 9, padding: "6px 10px" }}><option value="">All issues</option>${S.leverT.map((l) => html`<option key=${l.lever} value=${l.lever}>${l.issue} (${l.blocks})</option>`)}</select><span class="muted small">${rows.length} blocks</span></div>
          <div class="row"><button class="btn sm primary" onClick=${() => ctx.createOrders(rows.slice(0, 10))}>+ Work orders for top 10</button><button class="btn sm" onClick=${() => download("action_plan.csv", rows.map((b) => ({ rank: b.rank, block: b.id, estate: b.estate, issues: b.issues, first_action: b.action, gain_t_yr: b.gain_t, gain_rm_yr: Math.round(b.gain_t * S.price), risk: b.risk })))}>⇩ Export</button></div></div>
          <div class="table-wrap"><table class="t"><thead><tr><th>#</th><th>Block</th><th>Issues found</th><th>First action</th><th class="num">Worth a year</th><th>Risk</th><th></th></tr></thead>
          <tbody>${rows.slice(0, n).map((b) => html`<tr key=${b.id}><td>${b.rank}</td><td><a href=${"#/block/" + b.id}><b>${b.id}</b></a><div class="small muted">${b.estate.replace(" Estate", "")}</div></td><td class="small">${b.issues || "–"}</td><td class="small">${b.action}</td><td class="num"><b>${fmt.rm(b.gain_t * S.price)}</b><div class="small muted">${fmt.n(b.gain_t)} t</div></td><td><${Risk} r=${b.risk} /></td><td><${WoButton} b=${b} ctx=${ctx} /></td></tr>`)}</tbody></table></div>
          ${n < rows.length && html`<div style=${{ textAlign: "center", marginTop: 12 }}><button class="btn" onClick=${() => setN(n + 50)}>Show more</button></div>`}
        </div></div>`
      : html`<div>
        ${!orders.length && html`<div class="notice info" style=${{ marginBottom: 14 }}>No work orders yet. Create them from the recommendations, the early warnings or a block profile.</div>`}
        <div class="board">${["todo", "inprog", "done"].map((st) => { const col = orders.filter((o) => o.status === st); return html`<div class="col" key=${st}><h3><span>${STATUS[st]}</span><span class="muted small">${col.length} · ${sumRM(col)}/yr</span></h3>
          ${col.map((o) => html`<div class="wo" key=${o.id}><div class="t"><a href=${"#/block/" + o.id}>${o.id}</a> · ${fmt.rm(o.gain_t * S.price)}/yr</div><div class="d">${o.action}</div>
            <div class="row"><select value=${o.owner} onChange=${(e) => ctx.updateOrder(o.id, { owner: e.target.value })}>${OWNERS.map((w) => html`<option key=${w}>${w}</option>`)}</select>
            <select value=${o.status} onChange=${(e) => ctx.updateOrder(o.id, { status: e.target.value })}>${Object.entries(STATUS).map(([k, v]) => html`<option key=${k} value=${k}>${v}</option>`)}</select>
            <span class="small muted">Due ${o.due}</span><button class="btn sm" title="Remove" onClick=${() => ctx.removeOrder(o.id)}>✕</button></div></div>`)}</div>`; })}</div>
        ${orders.length > 0 && html`<div class="row" style=${{ marginTop: 14 }}><button class="btn sm" onClick=${() => download("work_orders.csv", orders.map((o) => ({ block: o.id, estate: o.estate, action: o.action, owner: o.owner, status: STATUS[o.status], due: o.due, gain_rm_yr: Math.round(o.gain_t * S.price) })))}>⇩ Export work orders</button><span class="small muted">Saved in this browser for the demo; in production, saved to the database and visible to the whole team.</span></div>`}
      </div>`}
    </div>`;
  }

  function MapView({ blocks, mode, onPick, picked }) {
    const el = useRef(null), map = useRef(null), layer = useRef(null);
    useEffect(() => {
      map.current = L.map(el.current, { scrollWheelZoom: false });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors" }).addTo(map.current);
      layer.current = L.layerGroup().addTo(map.current);
      return () => map.current.remove();
    }, []);
    useEffect(() => {
      layer.current.clearLayers();
      const color = (b) => mode === "risk" ? ({ High: "#C0392B", Medium: "#C7781F", Low: "#2E7D4F" })[b.risk]
        : mode === "value" ? (b.gain_t > 60 ? "#7A2E0E" : b.gain_t > 30 ? "#C7781F" : b.gain_t > 10 ? "#E8B66A" : "#D9D5CA")
        : (b.vs_peers < -2 ? "#C0392B" : b.vs_peers < 0 ? "#E8A07A" : b.vs_peers < 2 ? "#8CCBA3" : "#2E7D4F");
      blocks.forEach((b) => {
        L.circleMarker([b.lat, b.lon], { radius: b.id === picked ? 9 : 5.5, color: b.id === picked ? "#12241C" : "#fff", weight: b.id === picked ? 3 : 1, fillColor: color(b), fillOpacity: .9 })
          .bindTooltip(`<b>${b.id}</b><br>${b.estate}<br>${fmt.n(b.yield, 1)} t/ha/yr · risk ${b.risk}`).on("click", () => onPick(b.id)).addTo(layer.current);
      });
      if (blocks.length) map.current.fitBounds(L.latLngBounds(blocks.map((b) => [b.lat, b.lon])).pad(0.08), { maxZoom: 13 });
    }, [blocks, mode, picked]);
    return html`<div class="map" ref=${el}></div>`;
  }

  function Explorer({ D, S, ctx }) {
    const [mode, setMode] = useState("risk");
    const [picked, setPicked] = useState(null);
    const [q, setQ] = useState("");
    const b = picked && D.blocks.find((x) => x.id === picked);
    const legends = { risk: [["#C0392B", "High risk"], ["#C7781F", "Medium"], ["#2E7D4F", "Low"]], gap: [["#C0392B", "< −2 vs peers"], ["#E8A07A", "−2 to 0"], ["#8CCBA3", "0 to +2"], ["#2E7D4F", "> +2"]], value: [["#7A2E0E", "> 60 t/yr"], ["#C7781F", "30–60"], ["#E8B66A", "10–30"], ["#D9D5CA", "< 10"]] };
    return html`<div>
      <${Head} eyebrow="Observe" title="Block map" sub="Every block on the map. Colour by risk, yield gap or value, then click a block for its story.">
        <div class="seg">${[["risk", "Risk"], ["gap", "Yield gap"], ["value", "Value"]].map(([k, l]) => html`<button key=${k} class=${mode === k ? "on" : ""} onClick=${() => setMode(k)}>${l}</button>`)}</div>
        <form onSubmit=${(e) => { e.preventDefault(); const id = q.trim().toUpperCase(); if (D.blocks.find((x) => x.id === id)) go("block/" + id); else ctx.toast("No block " + id); }} class="row">
          <input list="blockids" placeholder="Find a block, e.g. EST005-D08-B01" value=${q} onInput=${(e) => setQ(e.target.value)} style=${{ font: "inherit", border: "1px solid var(--line)", borderRadius: 9, padding: "7px 10px", width: 250 }} />
          <datalist id="blockids">${S.blocks.slice(0, 640).map((x) => html`<option key=${x.id} value=${x.id} />`)}</datalist><button class="btn">Open</button></form>
      </${Head}>
      <div class="grid g-wide">
        <div class="card"><${MapView} blocks=${S.blocks} mode=${mode} onPick=${setPicked} picked=${picked} />
          <div class="legend">${legends[mode].map(([c, l]) => html`<span key=${l}><i style=${{ background: c }}></i>${l}</span>`)}<span class="muted">· Block locations from the sample data</span></div></div>
        ${b ? html`<div class="card"><div class="card-head"><div><h2>${b.id}</h2><p>${b.estate} · ${b.division} · ${b.age_band}</p></div><${Risk} r=${b.risk} /></div>
            <div class="grid g2" style=${{ gap: 10, marginBottom: 12 }}><div><div class="small muted">Yield now</div><b style=${{ fontSize: 20 }}>${fmt.n(b.yield, 1)}</b> <span class="small">t/ha/yr</span></div><div><div class="small muted">vs age peers</div><b style=${{ fontSize: 20 }} class=${b.vs_peers < 0 ? "down" : "up"}>${fmt.signed(b.vs_peers)}</b></div>
            <div><div class="small muted">Forecast next</div><b style=${{ fontSize: 20 }}>${fmt.n(b.fc, 1)}</b></div><div><div class="small muted">Fixing it is worth</div><b style=${{ fontSize: 20 }}>${fmt.rm(b.gain_t * S.price)}</b></div></div>
            <p class="small"><b>Why:</b> ${b.issues || "no controllable issue stands out"}</p><p class="small" style=${{ margin: "6px 0 12px" }}><b>Do first:</b> ${b.action}</p>
            <div class="row"><a class="btn sm primary" href=${"#/block/" + b.id}>Open block profile</a><${WoButton} b=${b} ctx=${ctx} /></div></div>`
          : html`<div class="card"><h2>Estates</h2><p class="small muted" style=${{ marginBottom: 8 }}>Area-weighted, worst first. Click a dot on the map for a block.</p>
            <div class="table-wrap"><table class="t"><thead><tr><th>Estate</th><th class="num">Yield</th><th class="num">vs peers</th><th class="num">High risk</th></tr></thead><tbody>
            ${S.estates.map((e) => html`<tr key=${e.estate} class="click" onClick=${() => ctx.setEstate(e.estate)}><td><b>${e.estate.replace(" Estate", "")}</b><div class="small muted">${e.region}</div></td><td class="num">${fmt.n(e.yield, 1)}</td><td class=${"num " + (e.vs_peers < 0 ? "down" : "up")}>${fmt.signed(e.vs_peers)}</td><td class="num">${e.high}</td></tr>`)}</tbody></table></div></div>`}
      </div></div>`;
  }

  function Block({ D, S, ctx, id }) {
    const b = D.blocks.find((x) => x.id === (id || "").toUpperCase());
    if (!b) return html`<div class="card"><h2>Block not found</h2><p class="muted">Open one from the map or the action plan.</p><a class="btn" href="#/map" style=${{ marginTop: 10 }}>Block map</a></div>`;
    const lev = Object.entries(b.levers).sort((x, y) => y[1] - x[1]);
    const nut = (sym) => D.nutrients.find((n) => n.nutrient.includes(`(${sym})`));
    const sig = b.signals;
    const checks = [
      ["Harvest round", `${fmt.n(sig.harvest_interval_days)} days`, sig.harvest_interval_days <= 10, "7–10 days"],
      ["Flooding", `${fmt.n(sig.flooding_days)} days`, sig.flooding_days <= 2, "0–2 days"],
      ["Road access score", `${fmt.n(sig.road_accessibility_score_1_5, 1)} of 5`, sig.road_accessibility_score_1_5 >= 3.5, "3.5 or more"],
      ["Leaf potassium (K)", `${sig.leaf_k_pct}%`, !nut("K") || sig.leaf_k_pct >= nut("K").critical_level_pct, nut("K") ? `≥ ${nut("K").critical_level_pct}%` : ""],
      ["Leaf magnesium (Mg)", `${sig.leaf_mg_pct}%`, !nut("Mg") || sig.leaf_mg_pct >= nut("Mg").critical_level_pct, nut("Mg") ? `≥ ${nut("Mg").critical_level_pct}%` : ""],
      ["Ganoderma", `${sig.ganoderma_incidence_pct}%`, sig.ganoderma_incidence_pct < 1, "under 1%"],
      ["Bagworm", `${sig.bagworm_incidence_pct}%`, sig.bagworm_incidence_pct < 3, "under 3%"],
      ["Missing palms", `${sig.missing_palm_pct}%`, sig.missing_palm_pct < 3, "under 3%"],
      ["Weed cover", `${sig.weed_cover_pct}%`, sig.weed_cover_pct <= 15, "15% or less"],
    ];
    return html`<div>
      <${Head} eyebrow=${`Block profile · rank ${b.rank} of ${D.blocks.length}`} title=${b.id} sub=${`${b.name} · ${b.estate}, ${b.division} · ${b.age_band} (${b.age} years) · ${fmt.n(b.area, 1)} ha · ${b.soil} · ${b.genetic}`}>
        <${WoButton} b=${b} ctx=${ctx} label="+ Create work order" /><button class="btn" onClick=${() => go("simulator/" + b.id)}>Simulate fixes</button><button class="btn dark" onClick=${() => ctx.ask(`Why is ${b.id} on the action list, and what should we do first?`)}>✦ Ask about this block</button>
      </${Head}>
      <div class="grid g4" style=${{ marginBottom: 16 }}>
        <${Kpi} label="Yield now" value=${fmt.n(b.yield, 1) + " t/ha"} note=${html`<span class=${b.vs_peers < 0 ? "down" : "up"}>${fmt.signed(b.vs_peers)}</span> vs age peers (${fmt.n(b.peer, 1)})`} />
        <${Kpi} label="Forecast next cycle" value=${fmt.n(b.fc, 1) + " t/ha"} note=${html`80% range ${fmt.n(b.fc_low, 1)}–${fmt.n(b.fc_high, 1)} · <${Risk} r=${b.risk} />`} />
        <${Kpi} label="Value of fixing this block" value=${fmt.rm(b.gain_t * S.price)} note=${`${fmt.n(b.gain_t)} t FFB a year (${fmt.n(b.gain_ha, 2)} t/ha)`} />
        <${Kpi} label="Priority" value=${`#${b.rank}`} note=${`of ${D.blocks.length} blocks, by value and risk`} />
      </div>
      <div class="grid g-wide">
        <${ChartCard} D=${D} S=${S} name="block" block=${b} height=${300} />
        <div class="card"><h2>What to do, and why</h2>
          <div class="notice info" style=${{ margin: "10px 0" }}><b>Do first:</b> ${b.action}</div>
          <p class="small" style=${{ marginBottom: 10 }}><b>Issues found:</b> ${b.issues || "none controllable"}. Programs: ${b.fert}; ${b.treat}.</p>
          ${lev.length ? html`<div class="list">${lev.map(([k, v]) => html`<div class="li" key=${k}><div class="main-t"><b>${LEVERS[k].issue}</b><span>${(D.levers.find((l) => l.lever === k) || {}).action}</span></div><div class="amt">${fmt.n(v, 2)} t/ha<div class="small muted">${fmt.rm(v * b.area * S.price)}/yr</div></div></div>`)}</div>` : html`<p class="muted">No controllable lever; this block's yield follows its age.</p>`}
        </div>
      </div>
      <div class="card" style=${{ marginTop: 16 }}><h2>Field signals, latest cycle</h2><p class="small muted" style=${{ marginBottom: 8 }}>Against good-practice references. Red marks what is holding this block back.</p>
        <div class="table-wrap"><table class="t"><thead><tr><th>Signal</th><th class="num">This block</th><th>Reference</th><th>Status</th></tr></thead><tbody>
        ${checks.map(([n, v, ok, ref]) => html`<tr key=${n}><td>${n}</td><td class="num"><b>${v}</b></td><td class="small muted">${ref}</td><td>${ok ? html`<span class="risk Low">OK</span>` : html`<span class="risk High">Check</span>`}</td></tr>`)}</tbody></table></div></div>
    </div>`;
  }

  function Simulator({ D, S, ctx, id }) {
    const [scopeKind, setScopeKind] = useState(id ? "block" : "view");
    const [blockId, setBlockId] = useState(id || S.ranked[0].id);
    const blocks = scopeKind === "block" ? D.blocks.filter((b) => b.id === blockId) : S.blocks;
    const avail = Object.keys(LEVERS).map((k) => ({ k, ...LEVERS[k], t: blocks.reduce((s, b) => s + (b.levers[k] || 0) * b.area, 0) })).filter((l) => l.t > 0.05).sort((a, b) => b.t - a.t);
    const [chosen, setChosen] = useState(() => new Set(avail.slice(0, 3).map((l) => l.k)));
    const [price, setPrice] = useState(S.price);
    const [cost, setCost] = useState(0);
    const res = PY.simulate(blocks, [...chosen].filter((k) => avail.find((a) => a.k === k)), price);
    const toggle = (k) => setChosen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
    const net = res.rm - cost;
    return html`<div>
      <${Head} eyebrow="Recommend" title="What-if simulator" sub="Choose which issues to fix and see the expected extra yield and its value, from the yield model. Add your cost to see the return." />
      <div class="grid g-wide">
        <div class="card">
          <div class="row" style=${{ marginBottom: 14 }}><div class="seg"><button class=${scopeKind === "view" ? "on" : ""} onClick=${() => setScopeKind("view")}>${ctx.estate ? ctx.estate : "All blocks in view"}</button><button class=${scopeKind === "block" ? "on" : ""} onClick=${() => setScopeKind("block")}>One block</button></div>
            ${scopeKind === "block" && html`<select value=${blockId} onChange=${(e) => setBlockId(e.target.value)} style=${{ font: "inherit", border: "1px solid var(--line)", borderRadius: 9, padding: "6px 10px" }}>${S.ranked.slice(0, 640).map((b) => html`<option key=${b.id} value=${b.id}>#${b.rank} ${b.id}</option>`)}</select>`}</div>
          <h3 style=${{ marginBottom: 8 }}>Issues to fix (${blocks.length} block${blocks.length > 1 ? "s" : ""})</h3>
          ${avail.length ? avail.map((l) => html`<label class="check" key=${l.k}><input type="checkbox" checked=${chosen.has(l.k)} onChange=${() => toggle(l.k)} /><div><b>${l.issue}</b><div class="small muted">${(D.levers.find((x) => x.lever === l.k) || {}).action}</div></div><span class="amt">${fmt.n(l.t)} t/yr</span></label>`) : html`<p class="muted">No controllable issue for this selection.</p>`}
          <div class="grid g2" style=${{ marginTop: 10 }}><div class="field"><label>FFB price (RM per tonne)</label><input type="number" value=${price} min="300" max="2000" step="10" onInput=${(e) => setPrice(+e.target.value || S.price)} /><span class="hint">MPOB 2025 average: RM 930</span></div>
          <div class="field"><label>Cost of the work (RM a year)</label><input type="number" value=${cost} min="0" step="1000" onInput=${(e) => setCost(+e.target.value || 0)} /><span class="hint">Optional: your estimate</span></div></div>
        </div>
        <div class="card"><h2>Expected outcome</h2>
          <div class="grid g2" style=${{ gap: 12, margin: "12px 0" }}>
            <div><div class="small muted">Extra FFB a year</div><div style=${{ fontFamily: "Space Grotesk", fontSize: 30, fontWeight: 600 }}>${fmt.n(res.t)} t</div></div>
            <div><div class="small muted">Value a year</div><div style=${{ fontFamily: "Space Grotesk", fontSize: 30, fontWeight: 600 }} class="up">${fmt.rm(res.rm)}</div></div>
            <div><div class="small muted">Per hectare</div><b>${fmt.n(res.per_ha, 2)} t/ha/yr</b></div>
            <div><div class="small muted">${cost ? "Net of cost" : "Return on cost"}</div><b class=${net < 0 ? "down" : ""}>${cost ? fmt.rm(net) + " · " + (res.rm / cost).toFixed(1) + "×" : "add a cost"}</b></div>
          </div>
          <${Chart} height=${220} option=${hbar(avail.filter((l) => chosen.has(l.k)).map((l) => l.short).reverse(), avail.filter((l) => chosen.has(l.k)).map((l) => Math.round(res.by[l.k] || 0)).reverse(), "#2E7D4F", "t/yr", (v) => fmt.n(v) + " t")} />
          <p class="small muted" style=${{ marginTop: 8 }}>Model estimate on synthetic data, before costs; overlapping fixes are capped so they are not counted twice. Prove on trial blocks first.</p>
          <div class="row" style=${{ marginTop: 10 }}><button class="btn primary" onClick=${() => ctx.createOrders([...blocks].sort((a, b) => a.rank - b.rank).filter((b) => [...chosen].some((k) => b.levers[k])).slice(0, 10))}>+ Work orders for the top 10 blocks</button></div>
        </div>
      </div></div>`;
  }

  function Insights({ D, S }) {
    return html`<div>
      <${Head} eyebrow="Understand" title="Why yield differs" sub="What the models found, tested against agronomy references. Every number here comes from the pipeline." />
      <div class="grid g2"><${ChartCard} D=${D} S=${S} name="drivers" height=${320} /><${ChartCard} D=${D} S=${S} name="age_curve" height=${320} /></div>
      <div class="card" style=${{ marginTop: 16 }}><h2>Eight patterns tested</h2><p class="small muted" style=${{ marginBottom: 8 }}>Each one checked in the data before it is used in a recommendation.</p>
        <div class="table-wrap"><table class="t"><thead><tr><th>#</th><th>Pattern</th><th>Test</th><th>Evidence</th><th>Verdict</th></tr></thead><tbody>
        ${D.patterns.map((p) => html`<tr key=${p.no}><td>${p.no}</td><td><b>${p.pattern}</b></td><td class="small">${p.test}</td><td class="small">${p.evidence}</td><td><span class=${"risk " + (p.verdict === "Confirmed" ? "Low" : "Medium")}>${p.verdict}</span></td></tr>`)}</tbody></table></div></div>
      <div class="grid g2" style=${{ marginTop: 16 }}>
        <div class="card"><h2>Leaf nutrients</h2><div class="table-wrap"><table class="t"><thead><tr><th>Nutrient</th><th class="num">Critical level</th><th class="num">Samples below</th><th class="num">Yield vs peers below</th></tr></thead><tbody>
          ${D.nutrients.map((n) => html`<tr key=${n.nutrient}><td>${n.nutrient}</td><td class="num">${n.critical_level_pct}%</td><td class="num">${n.share_below_pct}%</td><td class="num">${fmt.signed(n.yield_vs_peers_below)}</td></tr>`)}</tbody></table></div></div>
        <div class="card"><h2>Pest treatments that work</h2><div class="table-wrap"><table class="t"><thead><tr><th>Pest</th><th>Program</th><th class="num">Change next cycle</th></tr></thead><tbody>
          ${[...D.treatments].sort((a, b) => a.change_pct_points - b.change_pct_points).slice(0, 8).map((t, i) => html`<tr key=${i}><td>${t.pest}</td><td>${t.treatment_program}</td><td class=${"num " + (t.change_pct_points < 0 ? "up" : "down")}>${fmt.signed(t.change_pct_points)} pts</td></tr>`)}</tbody></table></div></div>
      </div>
      <div class="card" style=${{ marginTop: 16 }}><h2>Block groups</h2><p class="small muted" style=${{ marginBottom: 8 }}>Blocks with similar conditions, grouped by machine learning, best first.</p>
        <div class="table-wrap"><table class="t"><thead><tr><th>Group</th><th class="num">Blocks</th><th class="num">Yield</th><th class="num">vs peers</th><th>Typical traits</th></tr></thead><tbody>
        ${D.groups.map((g) => html`<tr key=${g.name}><td><b>${g.name}</b></td><td class="num">${g.blocks}</td><td class="num">${fmt.n(g.yield_t_ha_yr, 1)}</td><td class=${"num " + (g.yield_vs_age_peers < 0 ? "down" : "up")}>${fmt.signed(g.yield_vs_age_peers)}</td><td class="small">${g.traits}</td></tr>`)}</tbody></table></div></div>
    </div>`;
  }

  function System({ D, ctx }) {
    const [check, setCheck] = useState(null);
    const fm = D.forecast_metrics;
    function onFile(e) {
      const f = e.target.files[0]; if (!f) return;
      if (f.size > 50e6) { setCheck({ ok: false, msg: "File is over 50 MB." }); return; }
      f.text().then((t) => {
        const lines = t.split(/\r?\n/).filter(Boolean); const head = lines[0].split(",").map((h) => h.trim().replace(/"/g, ""));
        const need = ["block_id", "harvest_cycle_no", "ffb_yield_t_ha", "productive_area_ha", "harvest_interval_days", "palm_age_years", "estate_name"];
        const miss = need.filter((n) => !head.includes(n));
        setCheck(miss.length ? { ok: false, msg: `Missing required columns: ${miss.join(", ")}.` } : { ok: true, msg: `${lines.length - 1} rows and ${head.length} columns read. Required columns present. In production the server now runs the 22 quality checks and re-trains the models, and every page updates.` });
      });
    }
    const log = ctx.aiLog;
    return html`<div>
      <${Head} eyebrow="Data and system" title="Data, models and integration" sub="How the data flows, how good it is, how accurate the models are, and how PalmYield connects to other systems." />
      <div class="card"><h2 style=${{ marginBottom: 12 }}>Data flow</h2>
        <div class="flow"><div class="step"><b>Data in</b>${ctx.option === "B" ? "SAP extract, daily (SAP Datasphere)" : "CSV upload each harvest cycle"}</div><span class="arrow">→</span>
        <div class="step"><b>Prepare</b>22 quality checks, 20 engineered features</div><span class="arrow">→</span>
        <div class="step core"><b>Models</b>5 algorithms compared; drivers, forecast, groups, what-if</div><span class="arrow">→</span>
        <div class="step"><b>Database + API</b>Results stored once; REST API serves every screen</div><span class="arrow">→</span>
        <div class="step"><b>Act</b>Web app, ${ctx.option === "B" ? "AI assistant, SAP Analytics Cloud" : "built-in answers"}, work orders</div></div></div>
      <div class="grid g2" style=${{ marginTop: 16 }}>
        <div class="card"><h2>Data quality</h2><p class="small muted" style=${{ marginBottom: 8 }}>${D.meta.rows.toLocaleString()} block-cycles · ${D.meta.blocks} blocks · ${D.meta.estates} estates · ${D.meta.cycles} cycles · synthetic sample</p>
          <div class="table-wrap scroll" style=${{ maxHeight: 330 }}><table class="t"><thead><tr><th>Check</th><th class="num">Pass rate</th><th>Status</th></tr></thead><tbody>
          ${D.quality.map((q, i) => html`<tr key=${i}><td><b>${q.area}</b> · ${q.check}${q.note && html`<div class="small muted">${q.note}</div>`}</td><td class="num">${q.pass_rate_pct}%</td><td><span class=${"risk " + (q.status === "Pass" ? "Low" : q.status === "Fixed" || q.status === "Info" ? "Medium" : "High")}>${q.status}</span></td></tr>`)}</tbody></table></div></div>
        <div class="card"><h2>Model accuracy</h2><p class="small muted" style=${{ marginBottom: 8 }}>Tested on blocks the models never saw. Forecast error ${fm.mae_improvement_vs_last_cycle_pct}% lower than "same as last cycle".</p>
          <div class="table-wrap"><table class="t"><thead><tr><th>Model</th><th class="num">Error (MAE)</th><th class="num">R²</th></tr></thead><tbody>
          ${D.models.map((m) => html`<tr key=${m.model}><td>${m.model}${m.chosen ? html` <span class="risk Low">chosen</span>` : ""}</td><td class="num">${m.mae}</td><td class="num">${m.r2}</td></tr>`)}</tbody></table></div>
          <${ChartCard} D=${D} S=${null} name="accuracy" height=${220} bare=${true} /></div>
      </div>
      <div class="grid g2" style=${{ marginTop: 16 }}>
        <div class="card"><h2>${ctx.option === "B" ? "SAP connection" : "Upload a new harvest cycle"}</h2>
          ${ctx.option === "B" ? html`<div class="list" style=${{ marginTop: 8 }}>${[["Source", "SAP S/4HANA plantation data via SAP Datasphere"], ["Schedule", "Daily at 02:00"], ["Status", "Demo: sample extract in the SAP format"], ["Last extract", `${D.meta.rows.toLocaleString()} rows · ${D.meta.cycle_dates.at(-1)}`]].map(([k, v]) => html`<div class="li" key=${k}><div class="main-t"><b>${k}</b><span>${v}</span></div></div>`)}</div>`
          : html`<div><p class="small" style=${{ margin: "6px 0 10px" }}>One row per block per harvest cycle, in the 117-column template. The file is checked here first.</p><input type="file" accept=".csv" onChange=${onFile} />${check && html`<div class=${"notice " + (check.ok ? "info" : "")} style=${{ marginTop: 10 }}>${check.msg}</div>`}</div>`}</div>
        <div class="card"><h2>Integration API</h2><p class="small muted" style=${{ marginBottom: 8 }}>The same REST API (FastAPI) serves this app, the AI and other systems such as SAP Analytics Cloud or Power BI.</p>
          <div class="table-wrap"><table class="t"><tbody>${[["GET /summary", "Headline numbers by estate"], ["GET /insights", "Automated findings"], ["GET /actions", "Ranked action plan"], ["GET /forecast", "Next-cycle forecast and range"], ["GET /blocks/{id}", "One block: history, forecast, action"]].map(([e, d]) => html`<tr key=${e}><td><code>${e}</code></td><td class="small">${d}</td></tr>`)}</tbody></table></div></div>
      </div>
      ${ctx.option === "B" && html`<div class="card" style=${{ marginTop: 16 }}><div class="card-head"><div><h2>AI usage log</h2><p>Who asked the AI what, and when, for cost and governance${ctx.role !== "admin" ? " · administrators only" : ""}</p></div></div>
        ${ctx.role !== "admin" ? html`<p class="muted">Sign in as the administrator to see the log.</p>` : log.length ? html`<div class="table-wrap scroll" style=${{ maxHeight: 280 }}><table class="t"><thead><tr><th>Time</th><th>User</th><th>Question</th><th>Answered</th></tr></thead><tbody>${[...log].reverse().map((r, i) => html`<tr key=${i}><td class="small">${r.at}</td><td>${r.user}</td><td class="small">${r.q}</td><td>${r.ok ? "Yes" : "No"}</td></tr>`)}</tbody></table></div>` : html`<p class="muted">No AI questions yet on this device.</p>`}</div>`}
    </div>`;
  }

  function Settings({ ctx }) {
    const [k, setK] = useState(ctx.key || ""); const [test, setTest] = useState(null);
    async function save() {
      ctx.setKey(k.trim());
      if (!k.trim()) { setTest({ ok: true, msg: "Key removed from this browser." }); return; }
      setTest({ ok: true, msg: "Testing…" });
      try { await PY.askGemini(k.trim(), ctx.D, ctx.S, "Reply with the word OK.", []); setTest({ ok: true, msg: "Connected. The AI assistant is on." }); }
      catch (e) { setTest({ ok: false, msg: "Saved, but the test failed: " + e.message }); }
    }
    return html`<div>
      <${Head} eyebrow="Settings" title="Settings" />
      <div class="grid g2">
        <div class="card"><h2 style=${{ marginBottom: 10 }}>Proposal option</h2>
          <div class="seg" style=${{ marginBottom: 10 }}><button class=${ctx.option === "A" ? "on" : ""} onClick=${() => ctx.setOption("A")}>Option A · Lean</button><button class=${ctx.option === "B" ? "on" : ""} onClick=${() => ctx.setOption("B")}>Option B · Enterprise</button></div>
          <p class="small">${ctx.option === "A" ? "All analytics, early warnings, action plan and simulator, with built-in answers. No AI assistant and no company login: lowest running cost." : "Everything in A, plus the AI assistant and AI briefing, company sign-in with roles, the SAP data link and the AI usage log."}</p>
          <div class="field" style=${{ marginTop: 16 }}><label>FFB price (RM per tonne)</label><input type="number" min="300" max="2000" step="10" value=${ctx.price} onInput=${(e) => ctx.setPrice(+e.target.value || 930)} /><span class="hint">Used to value every gain. MPOB 2025 average: RM 930.</span></div></div>
        <div class="card"><h2 style=${{ marginBottom: 10 }}>AI assistant (Option B)</h2>
          <div class="field"><label>Google Gemini API key</label><input type="password" autocomplete="off" placeholder="Paste your key" value=${k} onInput=${(e) => setK(e.target.value)} />
            <span class="hint">Stored only in this browser and sent only to Google. Get a free key at aistudio.google.com. In production the key sits on the server, never in the browser.</span></div>
          <div class="row"><button class="btn primary" onClick=${save}>Save and test</button>${ctx.key && html`<button class="btn" onClick=${() => { setK(""); ctx.setKey(""); setTest({ ok: true, msg: "Key removed." }); }}>Remove key</button>`}</div>
          ${test && html`<div class=${"notice " + (test.ok ? "info" : "")} style=${{ marginTop: 10 }}>${test.msg}</div>`}</div>
      </div>
      <div class="card" style=${{ marginTop: 16 }}><h2 style=${{ marginBottom: 8 }}>Demo data</h2>
        <p class="small" style=${{ marginBottom: 10 }}>This hosted demo runs on a synthetic sample, not real SOPB results. Work orders and the AI log are kept in this browser only.</p>
        <div class="row"><button class="btn" onClick=${() => { if (confirm("Delete all work orders and the AI log in this browser?")) ctx.resetDemo(); }}>Reset demo data</button><a class="btn" href=${STREAMLIT} target="_blank" rel="noopener">Open the analytics prototype (backup) ↗</a></div></div>
    </div>`;
  }

  function SignIn({ ctx }) {
    return html`<div class="login">
      <div class="hero"><div><div class="brand" style=${{ padding: 0 }}><img src="icon.svg" alt="" /><div><b>PalmYield</b><small>Plantation yield command centre</small></div></div>
        <h1>See where yield is lost, why, and what to do first.</h1>
        <ul><li>Management briefing, updated every harvest cycle</li><li>Early warnings before the yield is lost</li><li>Ranked, valued actions turned into work orders</li><li>An AI assistant that answers from your own data</li></ul></div>
        <p class="small" style=${{ color: "#8EA698" }}>Demo on a synthetic sample · not real SOPB results</p></div>
      <div class="panel"><h2 style=${{ fontSize: 24 }}>Sign in</h2>
        <p class="muted">In production you sign in with your company account (single sign-on), and your role sets what you see. For this demo, pick a role:</p>
        ${Object.entries(ROLES).map(([k, r]) => html`<button class="role" key=${k} onClick=${() => ctx.signIn(k)}><span class="avatar">${r.initials}</span><span><b>${r.name}</b><span class="small muted">${r.role}${k === "admin" ? " · sees the AI usage log" : ""}</span></span><span style=${{ marginLeft: "auto" }}>→</span></button>`)}
        <p class="small muted">Option B · Enterprise. <a href="#" onClick=${(e) => { e.preventDefault(); ctx.setOption("A"); }}>Use Option A instead</a> (no sign-in).</p></div>
    </div>`;
  }

  /* ---------- App ---------- */
  function App({ D }) {
    const route = useRoute();
    const params = new URLSearchParams(location.search);
    const [option, setOptionRaw] = usePersist("option", params.get("option") === "A" ? "A" : "B");
    const [role, setRole] = usePersist("role", ROLES[params.get("role")] ? params.get("role") : null);
    const [estate, setEstate] = usePersist("estate", "");
    const [price, setPrice] = usePersist("price", D.meta.price);
    const [key, setKey] = usePersist("gemini", "");
    const [orders, setOrders] = usePersist("orders", {});
    const [aiLog, setAiLog] = usePersist("ailog", []);
    const [pending, setPending] = useState(null);
    const [chats, setChats] = usePersist("chats", []);
    const [chatKey, setChatKey] = useState(0);
    const [toastMsg, setToast] = useState(null);
    const [menu, setMenu] = useState(false);
    useEffect(() => { setMenu(false); }, [route.join("/")]);
    const toast = (m) => { setToast(m); clearTimeout(window.__t); window.__t = setTimeout(() => setToast(null), 2600); };
    const S = useMemo(() => PY.scope(D, estate, price), [estate, price]);
    const user = option === "A" ? { name: "Estate team", role: "Option A · no sign-in", initials: "ET" } : ROLES[role] || null;
    const due = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); };
    const ctx = {
      D, S, option, role, user, estate, price, key, orders, aiLog, pending, chats,
      setOption: (o) => { setOptionRaw(o); toast(o === "A" ? "Option A · Lean: no AI, no sign-in" : "Option B · Enterprise: AI, sign-in, SAP link"); },
      setEstate, setPrice, setKey,
      signIn: (k) => { setRole(k); go("home"); },
      ask: (q) => { setPending(q); setChatKey((k) => k + 1); go("home"); },
      newChat: () => { setChatKey((k) => k + 1); go("home"); },
      saveChat: (c) => setChats((cs) => [c, ...cs.filter((x) => x.id !== c.id)].slice(0, 20)),
      clearPending: () => setPending(null),
      log: (q, ok) => setAiLog((l) => [...l.slice(-199), { at: new Date().toLocaleString("en-GB"), user: user ? user.name : "?", q, ok }]),
      createOrders: (bs) => {
        const add = bs.filter((b) => !orders[b.id]);
        if (!add.length) { toast("Already on the work order board"); return; }
        setOrders((o) => { const n = { ...o }; add.forEach((b) => { n[b.id] = { id: b.id, estate: b.estate, action: b.action, gain_t: b.gain_t, owner: b.issues.includes("harvest") || b.action.startsWith("Cut the harvest") ? "Harvest team" : "Estate manager", status: "todo", due: due(b.risk === "High" ? 7 : 21), created: new Date().toISOString() }; }); return n; });
        toast(`${add.length} work order${add.length > 1 ? "s" : ""} created · ${fmt.rm(add.reduce((s, b) => s + b.gain_t, 0) * price)} a year`);
      },
      updateOrder: (id, patch) => setOrders((o) => ({ ...o, [id]: { ...o[id], ...patch } })),
      removeOrder: (id) => setOrders((o) => { const n = { ...o }; delete n[id]; return n; }),
      resetDemo: () => { setOrders({}); setAiLog([]); setChats([]); toast("Demo data reset"); },
      toast,
    };

    if (option === "B" && !user) return html`<${SignIn} ctx=${ctx} />`;
    const [page, sub] = route;
    const NAV = [
      ["", [["home", "✦", "Ask PalmYield"], ["dashboard", "◉", "Dashboard"]]],
      ["Act", [["warnings", "⚠", "Early warnings", S.high], ["actions", "✓", "Action plan"]]],
      ["Explore", [["map", "⌖", "Block map"], ["simulator", "⇅", "What-if simulator"], ["insights", "◈", "Why yield differs"]]],
      ["System", [["system", "⛁", "Data and system"], ["settings", "⚙", "Settings"]]],
    ];
    const pages = {
      home: () => html`<${window.PYAsk} key=${"new" + chatKey} D=${D} S=${S} ctx=${ctx} />`,
      chat: () => html`<${window.PYAsk} key=${"chat" + sub + chatKey} D=${D} S=${S} ctx=${ctx} chatId=${sub} />`,
      assistant: () => html`<${window.PYAsk} key=${"new" + chatKey} D=${D} S=${S} ctx=${ctx} />`,
      dashboard: () => html`<${Home} D=${D} S=${S} ctx=${ctx} />`,
      warnings: () => html`<${Warnings} D=${D} S=${S} ctx=${ctx} />`,
      actions: () => html`<${Actions} D=${D} S=${S} ctx=${ctx} sub=${sub} />`,
      map: () => html`<${Explorer} D=${D} S=${S} ctx=${ctx} />`,
      block: () => html`<${Block} key=${sub} D=${D} S=${S} ctx=${ctx} id=${sub} />`,
      simulator: () => html`<${Simulator} key=${(sub || "") + estate} D=${D} S=${S} ctx=${ctx} id=${sub} />`,
      insights: () => html`<${Insights} D=${D} S=${S} />`,
      system: () => html`<${System} D=${D} ctx=${ctx} />`,
      settings: () => html`<${Settings} ctx=${ctx} />`,
    };
    return html`<div class="shell">
      <aside class=${"side" + (menu ? " open" : "")}>
        <a class="brand" href="#/home"><img src="icon.svg" alt="" /><div><b>PalmYield</b><small>AI yield assistant</small></div></a>
        <button class="newchat" onClick=${ctx.newChat}><span>＋</span> New chat</button>
        ${NAV.map(([sec, items]) => html`<div key=${sec || "main"}>${sec ? html`<div class="nav-sec">${sec}</div>` : ""}<nav class="nav">${items.map(([k, ico, label, pill]) => html`<a key=${k} href=${"#/" + k} class=${page === k || (k === "map" && page === "block") || (k === "home" && (page === "chat" || page === "assistant")) ? "on" : ""}><span class="ico">${ico}</span>${label}${pill ? html`<span class="pill">${pill}</span>` : ""}</a>`)}</nav></div>`)}
        ${chats.length > 0 && html`<div class="nav-sec">Recent chats</div><nav class="recent">${chats.slice(0, 6).map((c) => html`<a key=${c.id} href=${"#/chat/" + c.id} class=${page === "chat" && sub === c.id ? "on" : ""} title=${c.title}>${c.title}</a>`)}</nav>`}
        <div class="side-foot">${option === "A" ? "Option A · Lean" : "Option B · Enterprise"}<br />Synthetic sample data<br /><a href=${STREAMLIT} target="_blank" rel="noopener" style=${{ color: "#9DB5A7" }}>Analytics prototype ↗</a></div>
      </aside>
      <div class="main">
        <header class="top">
          <button class="menu" onClick=${() => setMenu(!menu)} aria-label="Menu">☰</button>
          <span class="small muted hide-sm">Estate</span><select value=${estate} onChange=${(e) => setEstate(e.target.value)} aria-label="Estate"><option value="">All estates (${D.meta.estates})</option>${D.estates.map((e) => html`<option key=${e.estate_id} value=${e.estate_name}>${e.estate_name}</option>`)}</select>
          <span class="chip syn hide-sm">Synthetic sample data</span>
          <span class="grow"></span>
          <button class=${"chip " + (option === "A" ? "a" : "b")} style=${{ border: 0 }} onClick=${() => go("settings")} title="Change option">${option === "A" ? "Option A · Lean" : "Option B · Enterprise"}</button>
          <button class="btn sm hide-sm" onClick=${() => go("dashboard")}>◉ Dashboard</button>
          <div class="user"><span class="avatar">${user.initials}</span><span class="hide-sm"><b>${user.name}</b><br /><span class="small muted">${user.role}</span></span>
            ${option === "B" && html`<button class="btn sm" onClick=${() => { setRole(null); }}>Sign out</button>`}</div>
        </header>
        <main class=${"content" + (page === "home" || page === "chat" || page === "assistant" ? " wide" : "")}>${(pages[page] || pages.home)()}</main>
      </div>
      ${toastMsg && html`<div class="toast">${toastMsg}</div>`}
    </div>`;
  }

  class Guard extends React.Component {
    constructor(p) { super(p); this.state = { err: null }; }
    static getDerivedStateFromError(err) { return { err }; }
    render() {
      return this.state.err ? html`<div class="boot"><div style=${{ textAlign: "center" }}><h2>Something went wrong on this page.</h2><p class="muted" style=${{ margin: "8px 0 14px" }}>${String(this.state.err.message || this.state.err)}</p><button class="btn primary" onClick=${() => { location.hash = "#/home"; location.reload(); }}>Back to the start</button></div></div>` : this.props.children;
    }
  }

  fetch("data/app.json?v=3").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((D) => ReactDOM.createRoot(document.getElementById("root")).render(html`<${Guard}><${App} D=${D} /><//>`))
    .catch((e) => { document.getElementById("root").innerHTML = '<div class="boot">Could not load the data (' + e.message + '). Please reload.</div>'; });
})();
