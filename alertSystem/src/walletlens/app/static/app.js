"use strict";
/* EventLens front end: no build step, no libraries. */

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pts = (dp) => { const v = Math.round(dp * 100); return v === 0 ? "0" : `${v > 0 ? "+" : "−"}${Math.abs(v)}`; };
const pct = (p) => `${Math.round(p * 100)}%`;
const dirClass = (dp) => (Math.round(dp * 100) > 0 ? "up" : Math.round(dp * 100) < 0 ? "down" : "");
const usd = (v) => { const a = Math.abs(v); const s = a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : a >= 1e3 ? `$${(a / 1e3).toFixed(a >= 1e4 ? 0 : 1)}k` : `$${a.toFixed(0)}`; return s; };
const ago = (ts, now) => { const m = Math.round((now - ts) / 60); return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`; };
const clock = (ts) => new Date(ts * 1000).toLocaleString([], { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
const GROUP_NAMES = { rates: "Fed and rates", macro: "Macro data", trade_china: "Tariffs and China", energy_mideast: "Oil and Middle East",
  war_europe: "Russia and Ukraine", crypto: "Crypto", ai_tech: "AI and tech", us_politics: "US politics" };
const CLUSTER_COLOURS = { C0: "#16212b", C1: "#0e8a84", C2: "#c98200", unknown: "#cbd3da" };

let state = null;
let view = "today";

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || response.statusText);
  return body;
}

/* ------------------------------------------------------------------ data */
async function refresh() {
  try {
    state = await api("/api/state");
    render();
  } catch (error) {
    $("#status").textContent = `Cannot reach the EventLens server: ${error.message}`;
  }
}

const scan = () => (state && state.scan) || {};
const mine = () => new Set(state ? state.holdings : []);
const linkedToMine = (m) => m.assets.some((a) => mine().has(a));
const marketsFor = (pred) => (scan().markets || []).filter(pred);

/* ------------------------------------------------------------------ status */
function renderStatus() {
  const s = scan();
  const el = $("#status");
  if (s.pending) { el.innerHTML = `<span class="dot"></span> First scan running (about 30 s)…`; return; }
  if (!s.ok) { el.innerHTML = `Scan failed: ${esc(s.error || "unknown")} <button type="button" id="rescan">Retry</button>`; bindRescan(); return; }
  const live = s.source === "live";
  const when = live ? `updated ${ago(s.updated_at, Date.now() / 1000)}` : `replay of ${new Date(s.updated_at * 1000).toUTCString().slice(5, 22)} UTC`;
  el.innerHTML = `<span class="dot ${live ? "" : "replay"}"></span> ${live ? "Live" : "Replay"} · ${s.markets.length} markets · ${when}`
    + (live ? ` <button type="button" id="rescan">Rescan</button>` : "");
  bindRescan();
}
function bindRescan() {
  const b = $("#rescan");
  if (b) b.onclick = async () => { b.disabled = true; b.textContent = "Scanning…"; await api("/api/rescan", { method: "POST" }); setTimeout(refresh, 25000); };
}

/* ------------------------------------------------------------------ today */
function seismograph(d, now) {
  const W = 320, H = 46, mid = 24, x = (ts) => W - ((now - ts) / 86400) * W;
  let ticks = "";
  for (const s of d.shocks) {
    const h = Math.min(20, 6 + Math.abs(s.dp) * 60);
    const colour = !s.reliable ? "#9aa6b1" : s.dp >= 0 ? "var(--yes)" : "var(--no)";
    const y1 = s.dp >= 0 ? mid - h : mid, y2 = s.dp >= 0 ? mid : mid + h;
    ticks += `<line x1="${x(s.ts).toFixed(1)}" x2="${x(s.ts).toFixed(1)}" y1="${y1}" y2="${y2}" stroke="${colour}" stroke-width="3" stroke-linecap="round" ${s.reliable ? "" : 'stroke-dasharray="2 3"'}><title>${esc(s.question)}: ${pts(s.dp)} points</title></line>`;
  }
  const warn = d.warnings.length ? `<circle cx="${W - 5}" cy="${mid}" r="5" fill="var(--warn)"><title>Unusual wallet activity in ${d.warnings.length} linked market(s)</title></circle>` : "";
  let grid = "";
  for (let h = 6; h < 24; h += 6) grid += `<line x1="${W - (h / 24) * W}" x2="${W - (h / 24) * W}" y1="8" y2="40" stroke="var(--rule-soft)"/>`;
  return `<svg class="seismo" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${d.shocks.length} linked jumps in 24 hours">
    ${grid}<line x1="0" x2="${W}" y1="${mid}" y2="${mid}" stroke="var(--rule)" stroke-width="1"/>${ticks}${warn}</svg>`;
}

const LINK_LABEL = { confirmed: "confirmed", likely: "likely", untested: "not enough history", weak: "weak link", dropped: "dropped" };

function linkChips(profile) {
  const links = (profile && profile.links) || {};
  return Object.entries(links).filter(([, st]) => st !== "dropped").map(([g, st]) =>
    `<span class="chip link-${st}" title="${esc(LINK_LABEL[st])}">${esc(GROUP_NAMES[g] || g)}${st === "confirmed" ? " ✓" : st === "weak" ? " · weak" : ""}</span>`).join("");
}

function noteLine(n) {
  const pct = n.shown_effect != null ? `${n.shown_effect >= 0 ? "+" : ""}${Math.round(n.shown_effect * 100)}%` : "";
  return `<div class="note-line"><span class="pulse" aria-hidden="true"></span>${esc(n.name)}: next-hour moves have run ${pct} larger than usual for this holding</div>`;
}

function renderBook() {
  const now = scan().updated_at || Date.now() / 1000;
  const list = $("#holdings");
  if (!state.digest.length) { list.innerHTML = `<li class="empty">Waiting for the first scan…</li>`; return; }
  list.innerHTML = state.digest.map((d) => {
    const p = d.profile || {};
    if (p.status === "checking") {
      return `<li class="holding"><div class="holding-top"><span class="ticker">${esc(d.symbol)}</span><span class="asset-name">Checking its history…</span></div>
        <p class="note">Finding linked bets and testing them against ${esc(d.symbol)}'s past hourly moves. About a minute.</p></li>`;
    }
    if (p.supported === false) {
      return `<li class="holding"><div class="holding-top"><span class="ticker">${esc(d.symbol)}</span><span class="asset-name">Not supported</span></div>
        <p class="note">${esc(p.reason || "")}</p></li>`;
    }
    const label = { calm: "Calm", elevated: "Elevated", high: "Jumping now" }[d.level];
    const rel = d.shocks.filter((s) => s.reliable).length;
    const ratio = d.info && d.info.jump_ratio ? d.info.jump_ratio.toFixed(1) : null;
    const active = (d.notes || []).filter((n) => n.active);
    return `<li class="holding" data-holding="${esc(d.symbol)}" role="button" tabindex="0">
      <div class="holding-top"><span class="ticker">${esc(d.symbol)}</span><span class="asset-name">${esc(state.names[d.symbol] && state.names[d.symbol] !== d.symbol ? state.names[d.symbol] : "")}</span>
      <span class="level ${d.level}">${label}</span></div>
      ${seismograph(d, now)}
      <div class="holding-foot"><span><b>${rel}</b> linked jump${rel === 1 ? "" : "s"} in 24 h · ${d.linked_markets} markets watched</span>
      <span>${ratio ? `moves ${ratio}× normal in jump hours` : ""}</span></div>
      <div class="chips links">${linkChips(p)}</div>
      ${active.map(noteLine).join("")}</li>`;
  }).join("");
}

function headline() {
  const d = state.digest;
  const high = d.filter((x) => x.level === "high"), elev = d.filter((x) => x.level === "elevated");
  if (!scan().ok) return ["Checking the event markets linked to your holdings…", ""];
  const names = (xs) => xs.map((x) => x.symbol).join(", ").replace(/, ([^,]*)$/, " and $1");
  if (high.length) return [`A linked event is jumping right now for ${names(high)}.`,
    `In past jumps like this, the linked asset made an unusually large move 25% of the time, against 18% for unrelated assets. It is a risk flag, not a prediction of direction.`];
  if (elev.length) return [`Event risk is up today for ${names(elev)}.`,
    `${elev.length === 1 ? "It has" : "They have"} a linked event that jumped in the last 24 hours. Nothing is jumping this hour.`];
  return [`Quiet day: no linked event has jumped in the last 24 hours.`, `EventLens rescans every 5 minutes and logs every jump it sees.`];
}

function marketChips(m) {
  const assets = m.assets.map((a) => `<span class="chip ${mine().has(a) ? "mine" : ""}">${esc(a)}</span>`).join("");
  const groups = m.groups.map((g) => `<span class="chip ${state.model.groups[g] && !state.model.groups[g].reliable ? "weak" : ""}" title="${state.model.groups[g] && !state.model.groups[g].reliable ? "Weak link: in tests, jumps in this group did not move the linked assets" : ""}">${esc(GROUP_NAMES[g] || g)}${state.model.groups[g] && !state.model.groups[g].reliable ? " · weak link" : ""}</span>`).join("");
  return `<div class="chips">${groups}${assets}</div>`;
}

function renderToday() {
  const [h, sub] = headline();
  $("#headline").textContent = h;
  $("#subhead").textContent = sub;
  const now = scan().updated_at;
  const alerts = marketsFor((m) => m.alert && m.reliable && linkedToMine(m)).sort((a, b) => Math.abs(b.dp_1h) - Math.abs(a.dp_1h));
  const others = marketsFor((m) => m.alert && !(m.reliable && linkedToMine(m))).length;
  $("#alerts").innerHTML = alerts.length ? alerts.map((m) => `<button class="alert" type="button" data-market="${esc(m.id)}">
      <div class="jump ${m.dp_1h >= 0 ? "up" : "down"}">${pts(m.dp_1h)}<small>points in 1 h · now ${pct(m.price)} YES</small></div>
      <div class="q">${esc(m.question)}</div>${marketChips(m)}</button>`).join("")
    : `<p class="empty">No market linked to your holdings moved 10 points in the last hour${others ? ` (${others} elsewhere or on a weak link, see Markets)` : ""}.</p>`;

  if (!state.early_warning_live) {
    $("#warnings").innerHTML = `<p class="empty">In testing. The early warning passed every research test, but on live markets it flagged 16% of hours instead of about 5% (check D7, How we know). It keeps running in the background and comes back once it passes on live data.</p>`;
  }
  const warns = !state.early_warning_live ? [] : marketsFor((m) => m.warning.flag && linkedToMine(m) && !m.alert).sort((a, b) => b.warning.score - a.warning.score);
  const driver = { wallets_z: "many more wallets than usual", gross_z: "much more money than usual", whale_z: "more $5k+ trades than usual" };
  if (state.early_warning_live) $("#warnings").innerHTML = warns.length ? warns.map((m) => `<div class="row" data-market="${esc(m.id)}" role="button" tabindex="0">
      <div class="q">${esc(m.question)}</div>
      <div class="figure">${pct(m.warning.jump_chance)}<small>jump chance next hour (usually ${(m.warning.usual_chance * 100).toFixed(1)}%)</small></div>
      <div class="meta">${driver[m.warning.driver]} in the last hour · now ${pct(m.price)} YES · linked to ${m.assets.filter((a) => mine().has(a)).join(", ")}</div></div>`).join("")
    : `<p class="empty">Wallet activity in your linked markets looks normal.</p>`;

  const notes = state.digest.flatMap((d) => (d.notes || []).filter((n) => n.active).map((n) => ({ ...n, symbol: d.symbol })));
  $("#wallet-notes").innerHTML = notes.length ? notes.map((n) => `<div class="row" data-holding="${esc(n.symbol)}" role="button" tabindex="0">
      <div class="q">${esc(n.symbol)} · ${esc(n.name)} in its linked bets</div>
      <div class="figure">${n.shown_effect >= 0 ? "+" : ""}${Math.round(n.shown_effect * 100)}%<small>larger next-hour moves (this holding's history)</small></div>
      <div class="meta">Context, not an alert: this pattern came before bigger moves in ${esc(n.symbol)} in the past.</div></div>`).join("")
    : `<p class="empty">No wallet pattern that matters for your holdings is active right now.</p>`;
  const press = marketsFor((m) => m.pressure_usd !== 0 && m.reliable && linkedToMine(m)).sort((a, b) => Math.abs(b.pressure_usd) - Math.abs(a.pressure_usd)).slice(0, 8);
  $("#pressure").innerHTML = press.length ? press.map((m) => {
    const yes = m.pressure_usd > 0;
    return `<div class="row" data-market="${esc(m.id)}" role="button" tabindex="0">
      <div class="q">${esc(m.question)}</div>
      <div class="figure ${yes ? "up" : "down"}">${usd(m.pressure_usd)}<small>net ${yes ? "YES" : "NO"}</small></div>
      <div class="meta">Large wallets ${yes ? "buying YES" : "buying NO"} in the last hour · now ${pct(m.price)} YES</div></div>`;
  }).join("") : `<p class="empty">No large-wallet buying above $500 net in your linked markets this hour.</p>`;
  if (press.length) $("#pressure").insertAdjacentHTML("beforeend", `<p class="note">After large-wallet buying, the probability moved on average ${state.model.pressure.whale_follow_points.toFixed(2)} points their way in the next hour, against ${state.model.pressure.retail_follow_points.toFixed(2)} after small-wallet buying (tested out of sample). A lean, not a forecast.</p>`);
}

/* ------------------------------------------------------------------ markets */
function renderMarkets() {
  const onlyMine = $("#only-mine").checked, onlyActive = $("#only-active").checked;
  const rows = marketsFor((m) => (!onlyMine || linkedToMine(m)) && (!onlyActive || m.alert || m.warning.flag));
  const head = `<thead><tr><th>Market</th><th>Chance YES</th><th class="num">Last hour</th><th class="num">24 h volume ($250+ trades)</th><th class="num">Wallets 24 h</th><th>Linked assets</th><th></th></tr></thead>`;
  const body = rows.map((m) => `<tr data-market="${esc(m.id)}">
      <td>${esc(m.question)}</td>
      <td><div class="prob"><div class="rail"><span style="width:${(m.price * 100).toFixed(1)}%"></span></div>${pct(m.price)}</div></td>
      <td class="num ${dirClass(m.dp_1h)}">${pts(m.dp_1h)}</td>
      <td class="num">${usd(m.volume_24h)}</td><td class="num">${m.wallets_24h}</td>
      <td>${m.assets.map((a) => `<span class="chip ${mine().has(a) ? "mine" : ""}">${esc(a)}</span>`).join(" ")}</td>
      <td>${m.alert ? '<span class="flag alert-f">Jumping</span>' : ""} ${m.warning.flag ? '<span class="flag warn-f">Unusual wallets</span>' : ""} ${m.reliable ? "" : '<span class="chip weak">weak link</span>'}</td></tr>`).join("");
  $("#market-table").innerHTML = head + `<tbody>${body || `<tr><td colspan="7" class="empty">No markets match these filters.</td></tr>`}</tbody>`;
}

/* ------------------------------------------------------------------ charts */
function lineChart(points, opts = {}) {
  const W = 640, H = opts.height || 180, L = 38, R = 10, T = 10, B = 24;
  if (points.length < 2) return `<p class="empty">Not enough price history.</p>`;
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = opts.min ?? Math.min(...ys), y1 = opts.max ?? Math.max(...ys);
  const sx = (x) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R), sy = (y) => T + (1 - (y - y0) / (y1 - y0 || 1)) * (H - T - B);
  const path = points.map((p, i) => `${i ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
  let axis = "";
  for (const v of opts.ticks || [y0, (y0 + y1) / 2, y1]) axis += `<line x1="${L}" x2="${W - R}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--rule-soft)"/><text x="${L - 6}" y="${sy(v) + 4}" text-anchor="end">${opts.fmt ? opts.fmt(v) : v}</text>`;
  for (let k = 0; k <= 3; k++) { const t = x0 + (k / 3) * (x1 - x0); axis += `<text x="${sx(t)}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === 3 ? "end" : "middle"}">${clock(t)}</text>`; }
  const marks = (opts.marks || []).map((m) => `<circle cx="${sx(m.ts)}" cy="${sy(m.y)}" r="4.5" fill="${m.dp >= 0 ? "var(--yes)" : "var(--no)"}" stroke="#fff" stroke-width="1.5"><title>${pts(m.dp)} points</title></circle>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "chart")}">${axis}<path d="${path}" fill="none" stroke="${opts.colour || "var(--ink)"}" stroke-width="2"/>${marks}</svg>`;
}

function walletChart(hours) {
  const W = 640, H = 150, L = 38, R = 10, T = 10, B = 24, n = hours.length;
  if (!n) return `<p class="empty">No $250+ trades in the last two days.</p>`;
  const max = Math.max(4, ...hours.map((h) => h.wallets));
  const bw = (W - L - R) / n;
  const trailing = hours.slice(0, -1).reduce((s, h) => s + Math.log1p(h.wallets), 0) / Math.max(1, n - 1);
  const usual = Math.expm1(trailing);
  const sy = (v) => T + (1 - v / max) * (H - T - B);
  let bars = "";
  hours.forEach((h, i) => {
    const last = i === n - 1;
    bars += `<rect x="${(L + i * bw + 1).toFixed(1)}" y="${sy(h.wallets).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${(H - B - sy(h.wallets)).toFixed(1)}" fill="${last ? "var(--warn)" : "#9fb0bd"}" rx="1.5"><title>${clock(h.end)}: ${h.wallets} wallets, ${usd(h.gross)}</title></rect>`;
  });
  const axis = `<line x1="${L}" x2="${W - R}" y1="${sy(usual)}" y2="${sy(usual)}" stroke="var(--ink)" stroke-dasharray="4 4"/>
    <text x="${L + 4}" y="${sy(usual) - 5}" text-anchor="start" style="paint-order:stroke;stroke:#fff;stroke-width:3px">usual: ${usual.toFixed(1)} wallets/hour</text>
    <text x="${L - 6}" y="${sy(max) + 4}" text-anchor="end">${max}</text><text x="${L - 6}" y="${sy(0) + 4}" text-anchor="end">0</text>
    <text x="${L}" y="${H - 6}">${clock(hours[0].end)}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">last hour</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distinct wallets per hour, last 48 hours">${axis}${bars}</svg>`;
}

/* ------------------------------------------------------------------ drawer */
async function openMarket(id) {
  const drawer = $("#drawer");
  drawer.hidden = false;
  $("#drawer-body").innerHTML = `<p class="empty">Loading…</p>`;
  $(".drawer-panel").focus();
  try {
    const m = await api(`/api/market/${encodeURIComponent(id)}`);
    const w = m.warning;
    const marks = m.shocks_24h.map((s) => ({ ts: s.ts, dp: s.dp, y: (m.prices.find((p) => p[0] === s.ts) || [0, null])[1] })).filter((s) => s.y != null);
    const mix = m.mix.filter((c) => c.share >= 0.005);
    const assets = m.assets.map((a) => {
      const info = m.asset_info[a] || {}, move = m.asset_moves[a];
      const how = (m.links || {})[a] || {};
      const hs = how.groups ? how.groups.map((g) => (info.history || {})[g]).filter((h) => h && h.effect != null) : [];
      const ratio = hs.length ? (1 + hs.reduce((x, h) => x + h.effect, 0) / hs.length).toFixed(1) : info.normal_abs_r ? (info.shock_abs_r / info.normal_abs_r).toFixed(1) : "–";
      const big = how.direct ? "Linked because the bet names this company." : `Linked by topic: ${(how.groups || []).map((g) => esc(GROUP_NAMES[g] || g)).join(", ")}${how.reliable ? "" : " (weak link)"}.`;
      const now = move && move.r_last_hour != null ? `<span class="${move.r_last_hour >= 0 ? "up" : "down"}">${(move.r_last_hour * 100).toFixed(2)}% last hour</span>` : "";
      return `<div class="asset-line"><b>${esc(a)}</b><div>${esc((state.names || {})[a] || "")} · moves ${ratio}× normal in jump hours<div class="note">${big}</div></div><div>${now}</div></div>`;
    }).join("");
    $("#drawer-body").innerHTML = `
      <h2 id="drawer-title">${esc(m.question)}</h2>
      ${marketChips(m)}
      <div class="stats">
        <div class="stat"><div class="v">${pct(m.price)}</div><div class="k">chance of YES now</div></div>
        <div class="stat"><div class="v ${dirClass(m.dp_1h)}">${pts(m.dp_1h)}</div><div class="k">points in the last hour</div></div>
        <div class="stat"><div class="v">${m.wallets_24h}</div><div class="k">wallets traded $250+ in 24 h</div></div>
        <div class="stat"><div class="v ${m.pressure_usd > 0 ? "up" : m.pressure_usd < 0 ? "down" : ""}">${m.pressure_usd ? usd(m.pressure_usd) : "–"}</div><div class="k">${m.pressure_usd ? `large wallets net ${m.pressure_usd > 0 ? "YES" : "NO"}, last hour` : "no large-wallet pressure"}</div></div>
      </div>
      <h3>Chance of YES, last 3 days</h3>
      <div class="chart">${lineChart(m.prices, { min: 0, max: 1, ticks: [0, 0.5, 1], fmt: (v) => pct(v), marks, colour: "var(--yes)", label: "Probability of YES" })}</div>
      <p class="note">Dots mark 10-point jumps in the last 24 hours.</p>
      <h3>Wallets trading each hour ($250+ trades)</h3>
      <div class="chart">${walletChart(m.wallet_hours)}</div>
      <p class="note">A surge in distinct wallets was the strongest early sign of a jump in the research data. The live early warning built on it is still being tested (D7), so this chart is for context only.</p>
      <h3>Who traded in the last 24 hours</h3>
      ${mix.length ? `<div class="mixbar">${mix.map((c) => `<span style="width:${(c.share * 100).toFixed(1)}%;background:${CLUSTER_COLOURS[c.cluster] || "#9aa6b1"}"></span>`).join("")}</div>
      <div class="mixlegend">${mix.map((c) => `<div><span class="sw" style="background:${CLUSTER_COLOURS[c.cluster] || "#9aa6b1"}"></span>${esc(c.name)} · ${Math.round(c.share * 100)}% of volume (${usd(c.usd)})${state.model.clusters[c.cluster] ? ` <span class="note">${esc(state.model.clusters[c.cluster].description)}</span>` : ""}</div>`).join("")}</div>
      <p class="note">Wallet groups come from the team's behaviour clustering. Shown for context only: no group's buying predicted the price better than others in tests.</p>` : `<p class="empty">No trades of $250 or more in the last 24 hours.</p>`}
      <h3>Linked assets</h3>${assets}
      ${m.slug ? `<p class="note"><a href="https://polymarket.com/event/${encodeURIComponent(m.slug)}" target="_blank" rel="noopener">Open on Polymarket</a></p>` : ""}`;
  } catch (error) {
    $("#drawer-body").innerHTML = `<p class="empty">${esc(error.message)}. The market may have dropped out of the latest scan.</p>`;
  }
}
async function openHolding(symbol) {
  const drawer = $("#drawer");
  drawer.hidden = false;
  $("#drawer-body").innerHTML = `<p class="empty">Loading…</p>`;
  $(".drawer-panel").focus();
  try {
    const p = await api(`/api/holding/${encodeURIComponent(symbol)}`);
    const info = p.info || {};
    const hist = p.history || {};
    const groups = Object.keys(p.links || {});
    const linkRows = groups.map((g) => {
      const h = hist[g] || {};
      const eff = h.effect != null ? `${h.effect >= 0 ? "+" : ""}${Math.round(h.effect * 100)}%` : "–";
      const ci = h.low != null ? ` (90% range ${Math.round(h.low * 100)}% to ${Math.round(h.high * 100)}%)` : "";
      return `<tr><td>${esc(GROUP_NAMES[g] || g)}</td><td><span class="chip link-${p.links[g]}">${esc(LINK_LABEL[p.links[g]])}</span></td>
        <td class="num">${h.jump_hours ?? 0}</td><td>${eff}${ci}</td></tr>`;
    }).join("");
    const w = (p.wallet_checks || {}).signals || {};
    const walletRows = Object.entries(w).map(([k, v]) => `<tr><td>${esc(v.name)}</td><td class="num">${v.hours}</td>
      <td>${v.effect != null ? `${v.effect >= 0 ? "+" : ""}${Math.round(v.effect * 100)}%` : "–"}</td>
      <td>${v.pass ? `<span class="chip link-confirmed">shown (${Math.round(v.shown_effect * 100)}%)</span>` : `<span class="chip">not shown</span>`}</td></tr>`).join("");
    $("#drawer-body").innerHTML = `
      <h2 id="drawer-title">${esc(p.symbol)}${info.name && info.name !== p.symbol ? ` · ${esc(info.name)}` : ""}</h2>
      <p class="note">${esc(info.type || "")}${info.sector ? ` · ${esc(info.sector)}` : ""}${info.industry ? ` · ${esc(info.industry)}` : ""}</p>
      ${p.supported === false ? `<p>${esc(p.reason)}</p>` : `
      <h3>How its bets are found</h3>
      <p class="note"><b>Direct mention:</b> ${(p.terms || []).length ? (p.terms || []).map((t) => `“${esc(t)}”`).join(", ") : "none (funds are linked by topic only)"}.
      <b>By topic:</b> from ${esc(p.candidate_reason || "")}, then each topic is tested on ${esc(p.symbol)}'s own hourly moves in past jump hours of that topic (${p.history_bars || 0} hours of history).</p>
      <div class="table-wrap"><table><thead><tr><th>Topic</th><th>Status</th><th class="num">Past jump hours</th><th>Move vs normal in those hours</th></tr></thead><tbody>${linkRows || `<tr><td colspan="4" class="empty">No topics.</td></tr>`}</tbody></table></div>
      <h3>Wallet patterns tested for this holding</h3>
      <p class="note">Each pattern is shown only if it came before bigger ${esc(p.symbol)} moves in its own history (≥ 20 cases). The number shown is pulled toward the research average so a few lucky hours can't make a big claim.</p>
      <div class="table-wrap"><table><thead><tr><th>Pattern</th><th class="num">Past cases</th><th>Next-hour move vs normal</th><th>In the app</th></tr></thead><tbody>${walletRows || `<tr><td colspan="4" class="empty">${esc((p.wallet_checks || {}).note || "Not checked yet.")}</td></tr>`}</tbody></table></div>`}
      <p class="note">Checked ${esc((p.checked_at || "").slice(0, 16).replace("T", " "))} UTC · app version ${esc(p.version || "")}</p>`;
  } catch (error) {
    $("#drawer-body").innerHTML = `<p class="empty">${esc(error.message)}</p>`;
  }
}
function closeDrawer() { $("#drawer").hidden = true; }

/* ------------------------------------------------------------------ track + evidence */
async function renderTrack() {
  const t = await api("/api/track");
  t.notes = t.notes || { notes: 0, scored: 0, mean_vs_normal: null, recent: [] };
  const rate = t.big_rate == null ? "–" : pct(t.big_rate);
  $("#track").innerHTML = `
    <div class="summary-strip">
      <div class="big-number"><div class="v">${t.alerts}</div><div class="k">alerts logged so far</div></div>
      <div class="big-number"><div class="v">${t.scored_pairs}</div><div class="k">alert–asset pairs checked</div></div>
      <div class="big-number"><div class="v">${rate}</div><div class="k">followed by a big asset move. Research: ${pct(t.research_rate)} (unrelated assets ${pct(t.unrelated_rate)})</div></div>
    </div>
    <div class="summary-strip">
      <div class="big-number"><div class="v">${t.notes.notes}</div><div class="k">wallet notes logged (patterns D2/D3)</div></div>
      <div class="big-number"><div class="v">${t.notes.mean_vs_normal == null ? "–" : t.notes.mean_vs_normal.toFixed(2) + "×"}</div><div class="k">average next-hour move after a note, vs normal (${t.notes.scored} checked; research: about 1.1–1.2×)</div></div>
    </div>
    ${t.scored_pairs < 30 ? `<p class="note">Fewer than 30 checked pairs: too early to compare with the research figure. Leave EventLens running and this fills in.</p>` : ""}
    <div class="table-wrap"><table><thead><tr><th>When</th><th>Market</th><th class="num">Jump</th><th>What the linked assets did</th></tr></thead><tbody>
    ${t.recent.map((r) => `<tr data-market="${esc(r.market)}"><td>${clock(r.ts)}</td><td>${esc(r.question)}${r.reliable ? "" : ' <span class="chip weak">weak link</span>'}</td>
      <td class="num ${r.dp >= 0 ? "up" : "down"}">${pts(r.dp)}</td>
      <td>${r.assets.map((a) => { const s = r.scores[a]; if (!s) return `<span class="chip">${esc(a)}: pending</span>`; if (s.status !== "scored") return `<span class="chip">${esc(a)}: ${esc(s.status)}</span>`;
        return `<span class="chip ${s.big ? "mine" : ""}">${esc(a)} ${(s.move * 100).toFixed(2)}%${s.big ? " big" : ""}</span>`; }).join(" ")}</td></tr>`).join("")
      || `<tr><td colspan="4" class="empty">No alerts yet. They are logged the moment a watched market jumps.</td></tr>`}
    </tbody></table></div>`;
}

const LIMITS = [
  "Recent data is thin: the two most recent quarters have very few markets. The forward track record is how this gets checked.",
  "An alert means elevated risk, not a move: a big asset move followed 25% of alerts, against 18% for unrelated assets.",
  "US-politics markets did not move the linked assets in tests, so they are marked as a weak link and never raise the holding's level.",
  "Stocks only react while US markets are open; a jump at night shows up at the next open, which hourly tests do not measure.",
  "Links between events and assets come from keyword groups, not a learned model.",
  "The wallet early warning failed its live check (D7): on today's markets it flagged about 16% of hours, not 5%. It runs in the background only.",
  "No buy or sell advice. A direction hint was only right about 53% of the time, so it is left out.",
];
async function renderEvidence() {
  const e = await api("/api/evidence");
  const c = e.early_warning_check;
  $("#evidence").innerHTML = e.tests.map((t) => `<div class="test"><div class="verdict ${esc(t.verdict)}">${esc(t.verdict)}</div>
      <div><h3>${esc(t.id.toUpperCase())} · ${esc(t.title)}</h3><p><b>${esc(t.question)}</b></p><p>${esc(t.headline)}</p></div></div>`).join("")
    + (e.d7 ? `<div class="test"><div class="verdict ${esc(e.d7.verdict)}">${esc(e.d7.verdict)}</div><div><h3>D7 · Early warning on live data</h3>
      <p><b>Does the early warning flag a sensible share of hours on today's live markets (2–12%)?</b></p>
      <p>Last 24 hours of ${e.d7.market_hours} watched market-hours: ${(e.d7.flag_rate * 100).toFixed(1)}% flagged; ${e.d7.jumps_after_flag} of ${e.d7.jumps} jumps came after a flag. In the research data the same model ranks next-hour jumps with AUC ${c.auc_with_wallets.toFixed(3)} against ${c.auc_price_only.toFixed(3)} from price alone, but live markets move more per hour, so the research thresholds over-fire. Hidden until it passes.</p></div></div>` : "")
    + `<div class="limits"><h2>Limits to keep in mind</h2><ul>${LIMITS.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>`;
}

/* ------------------------------------------------------------------ portfolio dialog */
let draft = [];
function drawDraft() {
  $("#asset-grid").innerHTML = draft.length ? draft.map((s) => `<span class="ticker-pill">${esc(s)}<button type="button" data-remove="${esc(s)}" aria-label="Remove ${esc(s)}">×</button></span>`).join("")
    : `<p class="empty">No holdings yet.</p>`;
  $("#book-count").textContent = `${draft.length} of 15`;
}
function openBook() {
  draft = [...state.holdings];
  drawDraft();
  $("#ticker-input").value = "";
  $("#book-dialog").showModal();
  $("#ticker-input").focus();
}
function addTickers() {
  const raw = $("#ticker-input").value.toUpperCase().split(/[\s,;]+/).map((t) => t.trim()).filter(Boolean);
  for (const t of raw) if (!draft.includes(t) && draft.length < 15) draft.push(t);
  $("#ticker-input").value = "";
  drawDraft();
}
$("#ticker-add").addEventListener("click", addTickers);
$("#ticker-input").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addTickers(); } });
$("#asset-grid").addEventListener("click", (e) => {
  const b = e.target.closest("[data-remove]");
  if (b) { draft = draft.filter((s) => s !== b.dataset.remove); drawDraft(); }
});
$("#book-form").addEventListener("submit", async (event) => {
  if (event.submitter && event.submitter.value === "save") {
    addTickers();
    try { await api("/api/portfolio", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ holdings: draft }) });
      setTimeout(refresh, 400); setTimeout(refresh, 15000); setTimeout(refresh, 60000); } catch (error) { alert(error.message); }
  }
});

/* ------------------------------------------------------------------ routing */
function render() {
  renderStatus();
  if (view === "today") { renderBook(); renderToday(); }
  if (view === "markets") renderMarkets();
}
function route() {
  view = (location.hash || "#today").slice(1);
  if (!["today", "markets", "track", "evidence"].includes(view)) view = "today";
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== `view-${view}`; });
  document.querySelectorAll(".tabs a").forEach((a) => { if (a.dataset.view !== view) a.removeAttribute("aria-current"); else a.setAttribute("aria-current", "page"); });
  if (state) render();
  if (view === "track") renderTrack().catch((e) => { $("#track").textContent = e.message; });
  if (view === "evidence") renderEvidence().catch((e) => { $("#evidence").textContent = e.message; });
}

document.addEventListener("click", (event) => {
  const holding = event.target.closest("[data-holding]");
  if (holding && !event.target.closest("[data-market]")) return openHolding(holding.dataset.holding);
  const target = event.target.closest("[data-market]");
  if (target && !event.target.closest("a")) return openMarket(target.dataset.market);
  if (event.target.closest("[data-close]")) closeDrawer();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (event.key === "Enter" && event.target.matches(".row[data-market]")) openMarket(event.target.dataset.market);
  if (event.key === "Enter" && event.target.matches("[data-holding]")) openHolding(event.target.dataset.holding);
});
$("#edit-book").addEventListener("click", openBook);
$("#only-mine").addEventListener("change", renderMarkets);
$("#only-active").addEventListener("change", renderMarkets);
window.addEventListener("hashchange", route);

route();
refresh();
setInterval(refresh, 60000);
