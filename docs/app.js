// ====== CONFIG: set this to your deployed backend (must be HTTPS when hosted on GitHub Pages) ======
const API_BASE = "https://asynccoin.fastapicloud.dev";
// ================================================================================================

const $ = (s, el = document) => el.querySelector(s);
const app = $("#app"), dlg = $("#dlg");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = n => n == null ? "–" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: n < 1 ? 6 : 2 }).format(n);
const big = n => n == null ? "–" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 }).format(n);
const pct = n => n == null ? "–" : `<span class="${n >= 0 ? "pos" : "neg"}">${n >= 0 ? "+" : ""}${n.toFixed(2)}%</span>`;
const ago = d => d ? new Date(d).toLocaleString() : "never";

// ---------- session ----------
const token = () => { const t = localStorage.getItem("ac_token"), e = +localStorage.getItem("ac_exp"); if (t && e && Date.now() > e) { logout(true); return null; } return t; };
function login(t, secs, email) { localStorage.setItem("ac_token", t); localStorage.setItem("ac_exp", Date.now() + secs * 1000); localStorage.setItem("ac_email", email); }
function logout(silent) { ["ac_token", "ac_exp", "ac_email"].forEach(k => localStorage.removeItem(k)); if (!silent) toast("Logged out"); location.hash = "#/login"; }

// ---------- http ----------
async function api(path, { method = "GET", body } = {}) {
  const h = {}; if (body) h["Content-Type"] = "application/json";
  const t = token(); if (t) h.Authorization = "Bearer " + t;
  let r;
  try { r = await fetch(API_BASE + path, { method, headers: h, body: body ? JSON.stringify(body) : undefined }); }
  catch { throw new Error("Can't reach the server. Check API_BASE in app.js, and that the backend uses HTTPS."); }
  if (r.status === 401 && t) { logout(true); throw new Error("Session expired. Log in again."); }
  if (r.status === 204) return null;
  const d = await r.json().catch(() => null);
  if (!r.ok) {
    const det = d?.detail;
    throw new Error(typeof det === "string" ? det : Array.isArray(det) ? det.map(x => x.msg.replace(/^Value error, /, "")).join("; ") : `Request failed (${r.status})`);
  }
  return d;
}
let tt; function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 3000); }
const note = (m, err) => `<div class="note ${err ? "err" : ""}">${esc(m)}</div>`;
const loading = () => app.innerHTML = `<p class="empty">Loading…</p>`;
const fail = e => app.innerHTML = note(e.message, true);

// ---------- router ----------
const routes = { market, watchlist, alerts, login: loginView, register: registerView, verify: verifyView, forgot: forgotView, reset: resetView };
const publicRoutes = ["login", "register", "verify", "forgot", "reset"];
async function route() {
  const [path, qs] = location.hash.slice(2).split("?");
  const name = routes[path] ? path : "market";
  if (!token() && !publicRoutes.includes(name)) return void (location.hash = "#/login");
  if (token() && ["login", "register"].includes(name)) return void (location.hash = "#/market");
  const authed = !!token();
  $("#nav").hidden = !authed;
  $("#nav").querySelectorAll("a").forEach(a => a.classList.toggle("on", a.hash === "#/" + name));
  $("#acct").innerHTML = authed ? `<span>${esc(localStorage.getItem("ac_email"))}</span><button id="out">Log out</button>` : "";
  if (authed) $("#out").onclick = () => logout();
  try { await routes[name](new URLSearchParams(qs || "")); } catch (e) { fail(e); }
}
addEventListener("hashchange", route);
addEventListener("DOMContentLoaded", route);

// ---------- auth views ----------
function authForm(title, sub, fields, btn, extra = "") {
  app.innerHTML = `<form class="panel auth" novalidate><h1>${title}</h1><p class="sub">${sub}</p><div id="msg"></div>${fields}
  <button class="primary">${btn}</button>${extra}</form>`;
  return $("form");
}
async function submit(form, fn) {
  form.onsubmit = async e => {
    e.preventDefault(); const b = $("button.primary", form); b.disabled = true;
    try { await fn(Object.fromEntries(new FormData(form))); } catch (err) { $("#msg").innerHTML = note(err.message, true); }
    b.disabled = false;
  };
}
const emailPw = `<label for="e">Email</label><input id="e" name="email" type="email" autocomplete="email" required>
<label for="p">Password</label><input id="p" name="password" type="password" minlength="8" maxlength="128" required>`;

const confirmPw = `<label for="p2">Confirm password</label><input id="p2" name="confirm" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>`;
const back = `<p class="sub" style="margin:1rem 0 0"><a href="#/login">Back to log in</a></p>`;

function loginView() {
  const f = authForm("Log in", "Track the market and your watchlist.", emailPw, "Log in",
    `<p class="sub" style="margin:1rem 0 0">New here? <a href="#/register">Create an account</a><br>Forgot your password? <a href="#/forgot">Reset it</a></p>`);
  submit(f, async d => { const r = await api("/api/auth/login", { method: "POST", body: d }); login(r.access_token, r.expires_in, d.email.toLowerCase()); location.hash = "#/market"; });
}
function registerView() {
  const f = authForm("Create account", "You'll get an email to verify your address.", emailPw + confirmPw, "Create account",
    `<p class="sub" style="margin:1rem 0 0">Have an account? <a href="#/login">Log in</a></p>`);
  submit(f, async d => {
    if (d.password !== d.confirm) throw new Error("Passwords don't match.");
    const r = await api("/api/auth/register", { method: "POST", body: { email: d.email, password: d.password } });
    f.reset(); $("#msg").innerHTML = note(r.message);
  });
}
function forgotView() {
  const f = authForm("Forgot password", "Enter your email and we'll send a link to set a new password.",
    `<label for="e">Email</label><input id="e" name="email" type="email" autocomplete="email" required>`, "Send reset link", back);
  submit(f, async d => { const r = await api("/api/auth/forgot-password", { method: "POST", body: { email: d.email } }); $("#msg").innerHTML = note(r.message); });
}
function resetView(q) {
  const t = q.get("token");
  if (!t) { app.innerHTML = `<div class="panel auth"><h1>Reset password</h1>${note("This link is missing its token.", true)}<a href="#/forgot">Request a new link</a></div>`; return; }
  const f = authForm("Set a new password", "Choose a password you'll remember.",
    `<label for="p">New password</label><input id="p" name="password" type="password" autocomplete="new-password" minlength="8" maxlength="128" required>` + confirmPw.replace("Confirm password", "Confirm new password"), "Save password", back);
  submit(f, async d => {
    if (d.password !== d.confirm) throw new Error("Passwords don't match.");
    const r = await api("/api/auth/reset-password", { method: "POST", body: { token: t, new_password: d.password } });
    f.innerHTML = `<h1>Password updated</h1>${note(r.message)}<a class="btn" href="#/login">Log in</a>`;
  });
}
async function verifyView(q) {
  const t = q.get("token");
  const f = authForm("Verify email", t ? "Verifying your email…" : "Paste the token from your verification email.",
    t ? "" : `<label for="t">Token</label><input id="t" name="token" required>`, "Verify", `<p class="sub" style="margin:1rem 0 0"><a href="#/login">Back to log in</a></p>`);
  const go = async token => { const r = await api("/api/auth/verify-email", { method: "POST", body: { token } }); $("#msg").innerHTML = note(r.message); };
  if (t) { $("button.primary").hidden = true; try { await go(t); } catch (e) { $("#msg").innerHTML = note(e.message, true); } }
  else submit(f, d => go(d.token.trim()));
}

// ---------- market ----------
const m = { q: "", sort: "market_cap_rank", offset: 0, limit: 25 };
async function market() {
  app.innerHTML = `<h1>Market</h1><p class="sub" id="sync"></p>
  <div class="bar"><input id="q" type="search" placeholder="Search name, symbol or id" aria-label="Search coins" value="${esc(m.q)}">
  <select id="sort" aria-label="Sort by">${[["market_cap_rank", "Rank"], ["market_cap", "Market cap"], ["current_price", "Price"], ["total_volume", "Volume"], ["price_change_percentage_24h", "24h change"], ["name", "Name"]].map(([v, l]) => `<option value="${v}" ${v === m.sort ? "selected" : ""}>${l}</option>`).join("")}</select></div>
  <div class="tw"><table><thead><tr><th>#</th><th class="l">Coin</th><th>Price</th><th>24h</th><th>Market cap</th><th>Volume</th></tr></thead><tbody id="rows"></tbody></table></div>
  <div class="pager"><span id="info"></span><div><button id="prev">Previous</button><button id="next">Next</button></div></div>`;
  let timer; $("#q").oninput = e => { clearTimeout(timer); timer = setTimeout(() => { m.q = e.target.value.trim(); m.offset = 0; load(); }, 300); };
  $("#sort").onchange = e => { m.sort = e.target.value; m.offset = 0; load(); };
  $("#prev").onclick = () => { m.offset = Math.max(0, m.offset - m.limit); load(); };
  $("#next").onclick = () => { m.offset += m.limit; load(); };
  load();
  async function load() {
    const p = new URLSearchParams({ limit: m.limit, offset: m.offset, sort_by: m.sort }); if (m.q) p.set("search", m.q);
    try {
      const r = await api("/api/crypto/coins?" + p);
      $("#sync").textContent = "Last synced " + ago(r.last_synced);
      $("#rows").innerHTML = r.data.length ? r.data.map(c => `<tr class="click" tabindex="0" data-id="${esc(c.coin_id)}"><td>${c.market_cap_rank ?? "–"}</td>
        <td class="l"><div class="coin">${c.image ? `<img src="${esc(c.image)}" alt="" loading="lazy">` : ""}<span>${esc(c.name)}<small>${esc(c.symbol)}</small></span></div></td>
        <td>${usd(c.current_price)}</td><td>${pct(c.price_change_percentage_24h)}</td><td>${big(c.market_cap)}</td><td>${big(c.total_volume)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty">No coins found.</td></tr>`;
      $("#rows").querySelectorAll("tr.click").forEach(tr => { tr.onclick = () => detail(tr.dataset.id); tr.onkeydown = e => e.key === "Enter" && detail(tr.dataset.id); });
      const end = Math.min(r.offset + r.limit, r.total);
      $("#info").textContent = r.total ? `${r.offset + 1}–${end} of ${r.total}` : "";
      $("#prev").disabled = r.offset === 0; $("#next").disabled = end >= r.total;
    } catch (e) { $("#rows").innerHTML = `<tr><td colspan="6">${note(e.message, true)}</td></tr>`; }
  }
}

async function detail(id) {
  dlg.innerHTML = `<p class="empty">Loading…</p>`; dlg.showModal();
  try {
    const [c, h] = await Promise.all([api("/api/crypto/coins/" + encodeURIComponent(id)), api(`/api/crypto/coins/${encodeURIComponent(id)}/history?limit=300`)]);
    const rows = [["Price", usd(c.current_price)], ["24h change", pct(c.price_change_percentage_24h)], ["24h high", usd(c.high_24h)], ["24h low", usd(c.low_24h)], ["Market cap", big(c.market_cap)], ["Volume", big(c.total_volume)], ["All-time high", usd(c.ath)], ["Supply", c.circulating_supply?.toLocaleString("en-US", { maximumFractionDigits: 0 }) ?? "–"]];
    dlg.innerHTML = `<h2 class="coin">${c.image ? `<img src="${esc(c.image)}" alt="" width="32" height="32">` : ""}${esc(c.name)} <small>${esc(c.symbol.toUpperCase())}</small></h2>
    ${spark(h.data.slice().reverse())}<div class="grid2">${rows.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("")}</div>
    <div class="row"><button id="x">Close</button><button class="primary" id="add">Add to watchlist</button></div>`;
    $("#x").onclick = () => dlg.close();
    $("#add").onclick = async () => {
      try { const r = await api("/api/crypto/watchlist", { method: "POST", body: { coin_ids: [id] } }); toast(r.added.length ? "Added to watchlist" : "Already on your watchlist"); dlg.close(); } catch (e) { toast(e.message); }
    };
  } catch (e) { dlg.innerHTML = note(e.message, true) + `<div class="row"><button onclick="dlg.close()">Close</button></div>`; }
}
dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });

function spark(pts) {
  const v = pts.map(p => p.current_price).filter(x => x != null);
  if (v.length < 2) return `<p class="empty">Price history builds up with each sync. Check back soon.</p>`;
  const lo = Math.min(...v), hi = Math.max(...v), W = 600, H = 160, s = hi - lo || 1;
  const d = v.map((y, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 8 - (y - lo) / s * (H - 16)).toFixed(1)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Price history, low ${usd(lo)}, high ${usd(hi)}"><polyline points="${d}" fill="none" stroke="${up ? "#16794a" : "#b8322a"}" stroke-width="2.5" vector-effect="non-scaling-stroke"/></svg>
  <div class="pager" style="margin:0"><span>Low ${usd(lo)}</span><span>High ${usd(hi)}</span></div>`;
}

// ---------- watchlist ----------
function item(w) {
  const c = w.coin;
  return `<div class="item ${w.alert_status ? "hit" : ""}" data-id="${esc(w.coin_id)}">
  <div><div class="coin">${c?.image ? `<img src="${esc(c.image)}" alt="">` : ""}<span><b>${esc(c?.name ?? w.coin_id)}</b>${c ? `<small>${esc(c.symbol)}</small>` : ""}</span>${w.alert_status ? `<span class="tag">${w.alert_status === "above" ? "Above target" : "Below target"}</span>` : ""}</div>
  <div class="price">${usd(c?.current_price)} ${pct(c?.price_change_percentage_24h)}</div></div>
  <form><div><label>Note</label><input name="note" maxlength="500" value="${esc(w.note)}"></div>
  <div><label>Alert above ($)</label><input name="alert_above" type="number" step="any" min="0" value="${w.alert_above ?? ""}"></div>
  <div><label>Alert below ($)</label><input name="alert_below" type="number" step="any" min="0" value="${w.alert_below ?? ""}"></div>
  <button class="primary">Save</button><button type="button" class="danger rm">Remove</button></form></div>`;
}
function wireItems(reload) {
  document.querySelectorAll(".item").forEach(el => {
    const id = el.dataset.id;
    $("form", el).onsubmit = async e => {
      e.preventDefault(); const f = e.target;
      const num = v => v === "" ? null : Number(v);
      try { await api("/api/crypto/watchlist/" + encodeURIComponent(id), { method: "PATCH", body: { note: f.note.value.trim() || null, alert_above: num(f.alert_above.value), alert_below: num(f.alert_below.value) } }); toast("Saved"); reload(); } catch (err) { toast(err.message); }
    };
    $(".rm", el).onclick = async () => { try { await api("/api/crypto/watchlist/" + encodeURIComponent(id), { method: "DELETE" }); toast("Removed"); reload(); } catch (err) { toast(err.message); } };
  });
}
async function watchlist() {
  loading();
  const [w, s] = await Promise.all([api("/api/crypto/watchlist"), api("/api/crypto/watchlist/summary")]);
  const stat = (l, v) => `<div class="stat"><span>${l}</span><b>${v}</b></div>`;
  const perf = p => p ? `${esc(p.symbol.toUpperCase())} ${pct(p.change_24h_pct)}` : "–";
  app.innerHTML = `<h1>Watchlist</h1><p class="sub">Last synced ${ago(w.last_synced)}</p>
  <form class="bar" id="add"><input id="ids" placeholder="Coin ids, comma separated (e.g. bitcoin, solana)" aria-label="Coin ids"><button class="primary">Add coins</button></form><div id="msg"></div>
  ${w.count ? `<div class="stats">${stat("Tracking", s.tracked_count)}${stat("Total market cap", big(s.total_market_cap))}${stat("Best 24h", perf(s.best_24h))}${stat("Worst 24h", perf(s.worst_24h))}</div>
  <div class="wl">${w.data.map(item).join("")}</div>` : `<p class="empty">Your watchlist is empty. Add a coin above, or open one from the <a href="#/market">market</a>.</p>`}`;
  $("#add").onsubmit = async e => {
    e.preventDefault(); const ids = $("#ids").value.split(",").map(x => x.trim()).filter(Boolean); if (!ids.length) return;
    try {
      const r = await api("/api/crypto/watchlist", { method: "POST", body: { coin_ids: ids } });
      const parts = [r.added.length && `Added: ${r.added.join(", ")}`, r.already_tracked.length && `Already tracked: ${r.already_tracked.join(", ")}`, r.not_found.length && `Not found: ${r.not_found.join(", ")}`].filter(Boolean);
      toast(parts.join(" · ") || "Nothing to add"); watchlist();
    } catch (err) { $("#msg").innerHTML = note(err.message, true); }
  };
  wireItems(watchlist);
}

// ---------- alerts ----------
async function alerts() {
  loading();
  const r = await api("/api/crypto/watchlist/alerts");
  app.innerHTML = `<h1>Alerts</h1><p class="sub">Coins past your price targets · synced ${ago(r.last_synced)}</p>
  ${r.count ? `<div class="wl">${r.data.map(item).join("")}</div>` : `<p class="empty">No alerts triggered. Set targets on your <a href="#/watchlist">watchlist</a>.</p>`}`;
  wireItems(alerts);
}