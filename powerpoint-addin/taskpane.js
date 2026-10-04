(function (root) {
  "use strict";
  const state = { token: null, sessionId: null, proposal: null, language: "auto" };
  const byId = id => typeof document === "undefined" ? null : document.getElementById(id);
  const safe = value => String(value == null ? "" : value).replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 4000);
  async function api(path, options = {}) {
    const base = (root.DUSNX_GATEWAY || "http://localhost:8080").replace(/\/$/, "");
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(base + path, { ...options, headers });
    const type = response.headers.get("content-type") || "";
    const body = type.includes("json") ? await response.json() : { detail: `HTTP ${response.status}` };
    if (!response.ok) throw new Error(safe(body.detail || body.message || `HTTP ${response.status}`));
    return body;
  }
  async function login() {
    const data = await api("/v1/auth/login", { method: "POST", body: JSON.stringify({ username: byId("username").value.trim(), password: byId("password").value }) });
    state.token = data.token; byId("password").value = ""; await loadSessions(); status("Connected", false);
  }
  function logout() {
    if (state.token) api("/v1/auth/logout", { method: "POST" }).catch(() => {});
    state.token = state.sessionId = state.proposal = null; renderProposal(null); status("Disconnected", true);
  }
  async function loadSessions() {
    const sessions = await api("/v1/sessions"); const select = byId("session"); select.replaceChildren();
    sessions.forEach(item => { const option = document.createElement("option"); option.value = item.session_id; option.textContent = safe(item.title); select.appendChild(option); });
    if (!sessions.length) await createSession(); else state.sessionId = select.value;
  }
  async function createSession() {
    const item = await api("/v1/sessions", { method: "POST", body: JSON.stringify({ title: "PowerPoint" }) });
    const option = document.createElement("option"); option.value = item.session_id; option.textContent = "PowerPoint"; byId("session").appendChild(option);
    state.sessionId = item.session_id; byId("session").value = item.session_id;
  }
  async function readSlideContext() {
    if (!root.PowerPoint?.run) return { title: "", text: "" };
    return root.PowerPoint.run(async context => {
      const slides = context.presentation.getSelectedSlides(); slides.load("items"); await context.sync();
      if (!slides.items.length) return { title: "", text: "" };
      const shapes = slides.items[0].shapes; shapes.load("items/name,textFrame/hasText,textFrame/textRange/text"); await context.sync();
      const texts = shapes.items.filter(shape => shape.textFrame?.hasText).map(shape => safe(shape.textFrame.textRange.text));
      return { title: texts[0] || "", text: texts.join("\n").slice(0, 4000) };
    });
  }
  async function ask() {
    if (!state.token || !state.sessionId) throw new Error("Sign in and select a session first.");
    const context = await readSlideContext(); const requestId = root.crypto?.randomUUID?.() || `ppt-${Date.now()}`;
    const message = `${safe(byId("prompt").value)}\n\n[PowerPoint selected slide]\nTitle: ${context.title}\nText: ${context.text}`;
    const result = await api("/v1/chat", { method: "POST", body: JSON.stringify({ session_id: state.sessionId, message,
      preferred_language: state.language, request_id: requestId }) });
    if (!result.provider_ok) throw new Error(result.reply);
    state.proposal = { text: safe(result.reply), provenance: { intent: result.intent, routing_source: result.routing_source,
      response_source: result.response_source, provider_used: result.provider_used, model_used: result.model_used } }; renderProposal(state.proposal);
  }
  async function applyProposal() {
    if (!state.proposal) throw new Error("No proposal to apply.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable; proposal was not applied.");
    await root.PowerPoint.run(async context => {
      const slides = context.presentation.getSelectedSlides(); slides.load("items"); await context.sync();
      if (!slides.items.length) throw new Error("Select one slide first.");
      const shapes = slides.items[0].shapes; shapes.load("items/textFrame/hasText"); await context.sync();
      const target = shapes.items.find(shape => shape.textFrame?.hasText); if (!target) throw new Error("The selected slide has no editable text shape.");
      target.textFrame.textRange.text = state.proposal.text; await context.sync();
    }); status("Proposal applied after confirmation.", false);
  }
  function renderProposal(value) { if (!byId("proposal")) return; byId("proposal").textContent = value ? value.text : "";
    byId("provenance").textContent = value ? JSON.stringify(value.provenance, null, 2) : ""; byId("apply").disabled = !value; }
  function status(message, error) { if (byId("status")) { byId("status").textContent = safe(message); byId("status").className = error ? "error" : "ok"; } }
  async function guarded(fn) { try { status("Working…", false); await fn(); } catch (error) { status(error.message, true); } }
  function bind() { byId("login").onclick = () => guarded(login); byId("logout").onclick = logout; byId("newSession").onclick = () => guarded(createSession);
    byId("ask").onclick = () => guarded(ask); byId("apply").onclick = () => guarded(applyProposal);
    byId("session").onchange = event => { state.sessionId = event.target.value; }; byId("language").onchange = event => { state.language = event.target.value; }; }
  if (root.Office?.onReady) root.Office.onReady(info => { if (info.host === root.Office.HostType.PowerPoint) bind(); });
  const exported = { safe, state, api, login, logout, readSlideContext, ask, applyProposal, renderProposal };
  if (typeof module !== "undefined") module.exports = exported; else root.DusnxPowerPoint = exported;
})(typeof window !== "undefined" ? window : globalThis);
