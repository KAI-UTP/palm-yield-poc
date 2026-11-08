/* PalmYield "Ask" screen: the AI-first start page and chat (loaded before app.js, uses its globals via window.PYUI). */
(function () {
  const { useState, useEffect, useRef } = React;
  const html = htm.bind(React.createElement);
  const { fmt } = PY;

  const STARTERS = {
    manager: [
      ["☀", "Brief me on this cycle", "Problem, cause, action and value"],
      ["⚠", "Which blocks will under-perform next cycle?", "Early warnings before the harvest"],
      ["✓", "What should we fix first, and what is it worth?", "Ranked actions in RM"],
      ["⌖", "Which estate needs the most attention?", "Estates against age peers"],
      ["📋", "What work orders are open?", "Progress of the action plan"],
      ["🔎", "Tell me about EST005-D08-B01", "One block's full story"]],
    agronomist: [
      ["🌱", "Is fertilizer working?", "Leaf nutrients and feeding"],
      ["🐛", "Which pest treatments work best?", "Ganoderma and bagworm"],
      ["◈", "Why does yield differ between blocks?", "The main drivers"],
      ["⚠", "Which blocks will under-perform next cycle?", "Early warnings before the harvest"],
      ["📋", "What are my tasks?", "Agronomy work orders"],
      ["🔎", "Tell me about EST005-D08-B01", "One block's full story"]],
    field: [
      ["📋", "What are my tasks today?", "Your team's work orders"],
      ["🔎", "Tell me about EST005-D08-B01", "Why this block needs work"],
      ["🛠", "How do we fix poor road access?", "What the action involves"],
      ["⏱", "Why does the harvest round matter?", "7 to 10 days, and why"]],
    admin: [
      ["◎", "How accurate is the forecast?", "Model checks on unseen blocks"],
      ["☀", "Brief me on this cycle", "Problem, cause, action and value"],
      ["📋", "What work orders are open?", "Usage of the action plan"],
      ["⌖", "Which estate needs the most attention?", "Estates against age peers"]],
  };

  const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"; };

  function Composer({ onSend, busy, big, ai, hasKey, autoFocus, canSet }) {
    const [v, setV] = useState("");
    const ta = useRef(null);
    useEffect(() => { if (autoFocus && ta.current && window.innerWidth > 820) ta.current.focus(); }, []);
    const grow = (el) => { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 220) + "px"; };
    const submit = () => { const q = v.trim(); if (!q || busy) return; onSend(q); setV(""); if (ta.current) { ta.current.style.height = "auto"; } };
    return html`<div class=${"ask-box" + (big ? " big" : "")}>
      <textarea ref=${ta} rows=${big ? 2 : 1} value=${v} maxLength="500" placeholder=${big ? "Ask anything about your yield, blocks, risks or actions…" : "Reply or ask something new…"}
        onInput=${(e) => { setV(e.target.value); grow(e.target); }} onKeyDown=${(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}></textarea>
      <div class="bar"><span class="small muted">${ai ? (hasKey ? "✦ AI on · answers only from your data" : canSet ? html`AI is off on this device · <a href="#/settings">add a key</a>` : "AI is off on this device · built-in answers") : "Built-in answers"}</span>
        <button class="send" onClick=${submit} disabled=${busy || !v.trim()} aria-label="Send">↑</button></div>
    </div>`;
  }

  function actionsFor(m, D, S, ctx) {
    const out = [];
    const ids = [...new Set((m.text.match(/EST\d{3}-D\d{2}-B\d{2}/g) || []))].filter((id) => D.blocks.find((b) => b.id === id)).slice(0, 3);
    ids.forEach((id) => out.push({ label: "Open " + id, href: "#/block/" + id }));
    const fresh = ids.filter((id) => !ctx.orders[id]);  // blocks that already have a work order get no create button
    if (fresh.length && ctx.canAssign) out.push({ label: fresh.length > 1 ? `+ Work orders for these ${fresh.length}` : "+ Work order", orders: fresh });
    if (m.chart === "tasks") out.push(ctx.allowed("tasks") ? { label: "Open My tasks", href: "#/tasks" } : { label: "Open work order board", href: "#/actions/board" });
    const page = { risk: ["See all early warnings", "#/warnings"], levers: ["Open action plan", "#/actions"], top_blocks: ["Open action plan", "#/actions"],
      estates: ["Open block map", "#/map"], drivers: ["Why yield differs", "#/insights"], age_curve: ["Why yield differs", "#/insights"],
      accuracy: ["Model accuracy", "#/system"], block: m.block ? ["Simulate fixes", "#/simulator/" + m.block] : null }[m.chart];
    if (page) out.push({ label: page[0], href: page[1] });
    return out.filter((a) => !a.href || ctx.allowed(a.href.replace("#/", "").split("/")[0]));
  }

  function tasksAnswer(ctx) {
    const mine = Object.values(ctx.orders).filter((o) => o.status !== "done" && (!ctx.user.teams || ctx.user.teams.includes(o.owner)))
      .sort((a, b) => (a.status === "inprog" ? 0 : 1) - (b.status === "inprog" ? 0 : 1) || a.due.localeCompare(b.due));
    const who = ctx.user.teams ? "Your team has" : "There are";
    if (!mine.length) return { text: `${who} no open work orders right now.`, chart: "tasks" };
    const rm = mine.reduce((s, o) => s + o.gain_t, 0) * ctx.price;
    return { text: `${who} **${mine.length} open work order${mine.length > 1 ? "s" : ""}**, worth ${fmt.rm(rm)} a year in total:\n` +
      mine.slice(0, 6).map((o) => `- **${o.id}** (${o.estate.replace(" Estate", "")}): ${o.action}. ${o.status === "inprog" ? "In progress" : "To do"}, due ${o.due}, ${o.owner.toLowerCase()}`).join("\n") +
      (mine.length > 6 ? `\n\n…and ${mine.length - 6} more.` : ""), chart: "tasks" };
  }

  function Ask({ D, S, ctx, chatId }) {
    const { Md, ChartCard, CHARTS } = window.PYUI;
    const saved = chatId && ctx.chats.find((c) => c.id === chatId);
    const [msgs, setMsgs] = useState(saved ? saved.msgs : []);
    const [busy, setBusy] = useState(false);
    const idRef = useRef(saved ? saved.id : null);
    const end = useRef(null);
    const ai = ctx.option === "B";

    useEffect(() => { if (msgs.length) end.current && end.current.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, busy]);
    useEffect(() => {
      if (!msgs.length || busy) return;
      const title = (msgs.find((m) => m.role === "user") || {}).text || "Chat";
      ctx.saveChat({ id: idRef.current, title: title.slice(0, 60), msgs: msgs.slice(-40), at: Date.now() });
    }, [msgs, busy]);

    const patchLast = (p) => setMsgs((ms) => { const n = ms.slice(); n[n.length - 1] = { ...n[n.length - 1], ...p }; return n; });

    function reveal(text, done) {
      let i = 0; const step = Math.max(6, Math.ceil(text.length / 45));
      const t = setInterval(() => { i += step; patchLast({ text: text.slice(0, i) }); if (i >= text.length) { clearInterval(t); done(); } }, 22);
    }

    async function send(q) {
      if (busy) return;
      if (!idRef.current) { idRef.current = "c" + Date.now(); history.replaceState(null, "", "#/chat/" + idRef.current); }
      const hist = msgs.filter((m) => m.text);
      setMsgs((m) => [...m, { role: "user", text: q }, { role: "bot", text: "", streaming: true }]);
      setBusy(true);
      const local = /\b(tasks?|work orders?|to do today)\b/i.test(q) && !/\bEST\d{3}/i.test(q) ? tasksAnswer(ctx) : PY.answer(D, S, q);
      const finish = (text, chart, block, src) => {
        patchLast({ text, chart, block, src, streaming: false, follow: PY.followUps(q, chart, D, S) });
        setBusy(false);
      };
      const id = (q.match(/EST\d{3}-D\d{2}-B\d{2}/i) || [])[0];
      if (ai && ctx.key) {
        try {
          const r = await PY.askGeminiStream(ctx.key, D, S, q, hist, (t) => patchLast({ text: t.replace(/\n?\s*CHART:[\s\S]*$/i, "") }));
          const s = PY.splitChart(r.text);
          ctx.log(q, true);
          finish(s.text, s.chart || local.chart, id ? id.toUpperCase() : local.block, `✦ Google Gemini (${r.model}) · answered only from PalmYield's results`);
          return;
        } catch (e) {
          ctx.log(q, false);
          reveal(local.text, () => finish(local.text, local.chart, local.block, `AI unavailable (${e.message}) · built-in answer`));
          return;
        }
      }
      reveal(local.text, () => finish(local.text, local.chart, local.block, ai ? "Built-in answer · add a Gemini key in Settings to switch on AI" : "Built-in answer engine · no AI cost"));
    }

    useEffect(() => { if (ctx.pending) { const q = ctx.pending; ctx.clearPending(); send(q); } }, [ctx.pending]);

    if (!msgs.length) {
      const openWO = Object.values(ctx.orders).filter((o) => o.status !== "done");
      const myOpen = openWO.filter((o) => !ctx.user.teams || ctx.user.teams.includes(o.owner));
      return html`<div class="ask"><div class="ask-hero">
        <div class="hero-mark">✦</div>
        <h1>${greeting()}, ${ctx.user.name.split(" ")[0]}</h1>
        <p class="hero-sub">${ai ? "What would you like to know about your plantation today?" : "Ask a question about your plantation's yield."} ${ctx.estate ? html`<b>${ctx.estate}</b>` : `${S.blocks.length} blocks, ${S.estates.length} estates`}.</p>
        <${Composer} big=${true} onSend=${send} busy=${busy} ai=${ai} hasKey=${!!ctx.key} autoFocus=${true} canSet=${ctx.allowed("settings")} />
        <div class="starters">${(STARTERS[ctx.role] || STARTERS.manager).map(([i, q, d]) => html`<button class="starter" key=${q} onClick=${() => send(q)}><span class="i">${i}</span><b>${q}</b><span>${d}</span></button>`)}</div>
        <div class="glance-head small muted">This cycle at a glance</div>
        <div class="glance">${[
          ["dashboard", "#/dashboard", fmt.rm(S.totalRM), "a year at stake", ""],
          ["warnings", "#/warnings", S.high, "blocks at high risk", "down"],
          ["actions", "#/actions", S.leverT[0] ? S.leverT[0].short : "–", "biggest fix", ""],
          ["actions", "#/actions/board", openWO.length, "open work orders", ""],
          ["tasks", "#/tasks", myOpen.length, "my open tasks", ""],
          ["insights", "#/insights", "8 of 8", "patterns confirmed", ""],
          ["system", "#/system", "±" + fmt.n(D.forecast_metrics.model.mae, 2), "forecast error, t/ha/yr", ""],
        ].filter(([pg]) => ctx.allowed(pg)).slice(0, 4).map(([pg, href, v, l, cls]) => html`<a key=${href} href=${href}><div class=${"v " + cls}>${v}</div><div class="l">${l}</div></a>`)}</div>
      </div></div>`;
    }

    return html`<div class="ask">
      <div class="thread">
        ${msgs.map((m, i) => m.role === "user" ? html`<div class="q" key=${i}>${m.text}</div>` : html`<div class="a" key=${i}>
          <div class="av">✦</div>
          <div class="body">
            ${m.text ? html`<div class=${m.streaming ? "cursor" : ""}><${Md} text=${m.text} /></div>` : html`<div class="thinking"><span></span><span></span><span></span> ${ai && ctx.key ? "Thinking" : "Working it out"}</div>`}
            ${!m.streaming && m.chart && CHARTS[m.chart] && html`<div class="chart-box"><${ChartCard} D=${D} S=${S} name=${m.chart} block=${m.block ? D.blocks.find((b) => b.id === m.block) : null} height=${250} bare=${true} /></div>`}
            ${!m.streaming && html`<div class="acts">${actionsFor(m, D, S, ctx).map((a) => a.href ? html`<a key=${a.label} class="btn sm" href=${a.href}>${a.label}</a>`
              : html`<button key=${a.label} class="btn sm primary" onClick=${() => ctx.createOrders(a.orders.map((id) => D.blocks.find((b) => b.id === id)))}>${a.label}</button>`)}</div>`}
            ${!m.streaming && m.follow && i === msgs.length - 1 && html`<div class="follow sugg">${m.follow.map((f) => html`<button key=${f} onClick=${() => send(f)}>${f} →</button>`)}</div>`}
            ${!m.streaming && m.src && html`<div class="src">${m.src}</div>`}
          </div></div>`)}
        <div ref=${end}></div>
      </div>
      <div class="dock"><${Composer} onSend=${send} busy=${busy} ai=${ai} hasKey=${!!ctx.key} canSet=${ctx.allowed("settings")} />
        <div class="small muted" style=${{ textAlign: "center", marginTop: 6 }}>Answers use only PalmYield's computed results · synthetic sample data</div></div>
    </div>`;
  }

  window.PYAsk = Ask;
})();
