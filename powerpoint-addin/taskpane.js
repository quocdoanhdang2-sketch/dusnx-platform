(function (root) {
  "use strict";
  const state = { token: null, sessionId: null, proposal: null, language: "auto", generation: 0, busy: false };
  const byId = id => typeof document === "undefined" ? null : document.getElementById(id);
  const safe = value => String(value == null ? "" : value).replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 4000);
  function clearProposal() { state.generation++; state.proposal = null; renderProposal(null); }
  function controls() {
    for (const id of ["ask", "newSession", "session", "language", "login"]) if (byId(id)) byId(id).disabled = state.busy;
    if (byId("apply")) byId("apply").disabled = state.busy || !state.proposal;
  }
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
    if (state.busy) throw new Error("Wait for the current operation.");
    clearProposal(); state.busy = true; controls();
    const generation = state.generation;
    try {
      const data = await api("/v1/auth/login", { method: "POST", body: JSON.stringify({ username: byId("username").value.trim(), password: byId("password").value }) });
      byId("password").value = "";
      if (generation !== state.generation) return;
      state.token = data.token; await loadSessions();
      if (state.token === data.token) status("Connected", false);
    } finally { state.busy = false; controls(); }
  }
  function logout() {
    if (state.token) api("/v1/auth/logout", { method: "POST" }).catch(() => {});
    state.token = state.sessionId = null; clearProposal(); status("Disconnected", true);
  }
  async function loadSessions() {
    const token = state.token, generation = state.generation;
    const sessions = await api("/v1/sessions");
    if (token !== state.token || generation !== state.generation) return;
    const select = byId("session"); select.replaceChildren();
    sessions.forEach(item => { const option = document.createElement("option"); option.value = item.session_id; option.textContent = safe(item.title); select.appendChild(option); });
    if (!sessions.length) await createSession(); else state.sessionId = select.value;
  }
  async function createSession() {
    clearProposal();
    const token = state.token, generation = state.generation;
    const item = await api("/v1/sessions", { method: "POST", body: JSON.stringify({ title: "PowerPoint" }) });
    if (token !== state.token || generation !== state.generation) return;
    const option = document.createElement("option"); option.value = item.session_id; option.textContent = "PowerPoint"; byId("session").appendChild(option);
    state.sessionId = item.session_id; byId("session").value = item.session_id;
  }
  async function selectedTarget(context) {
    const slides = context.presentation.getSelectedSlides(); slides.load("items/id");
    const shapes = context.presentation.getSelectedShapes(); shapes.load("items/id"); await context.sync();
    if (slides.items.length !== 1 || shapes.items.length !== 1) throw new Error("Select exactly one slide and one text shape.");
    const shape = shapes.items[0]; shape.textFrame.load("hasText"); await context.sync();
    if (!shape.textFrame.hasText) throw new Error("Select a text shape with existing text.");
    shape.textFrame.textRange.load("text"); await context.sync();
    return { shape, slideId: slides.items[0].id, shapeId: shape.id, text: shape.textFrame.textRange.text };
  }
  async function readSlideContext() {
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable.");
    return root.PowerPoint.run(async context => {
      const { shape, ...snapshot } = await selectedTarget(context); return snapshot;
    });
  }
  function validateProposal(result, originalText) {
    if (!result || result.provider_ok !== true || result.response_source !== "llm" || result.provider_called !== true ||
        typeof result.provider_used !== "string" || !result.provider_used.trim() ||
        typeof result.model_used !== "string" || !result.model_used.trim())
      throw new Error("A measured LLM response with provenance is required; no proposal was created.");
    if (typeof result.reply !== "string" || !result.reply.trim() || result.reply.length > 4000 ||
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(result.reply))
      throw new Error("Proposal must be non-empty plain text of at most 4000 characters.");
    const text = result.reply.trim();
    if (/^\s*(?:```|[\[{])/.test(text)) throw new Error("Structured metadata is not slide text.");
    if (text === originalText.trim()) throw new Error("Proposal does not change the selected text.");
    return text;
  }
  async function ask() {
    if (!state.token || !state.sessionId) throw new Error("Sign in and select a session first.");
    if (state.busy) throw new Error("Wait for the current operation.");
    clearProposal(); state.busy = true; controls();
    const generation = state.generation, sessionId = state.sessionId, token = state.token;
    try {
      const context = await readSlideContext(); const requestId = root.crypto?.randomUUID?.() || `ppt-${Date.now()}`;
      if (context.text.length > 4000) throw new Error("Selected text exceeds 4000 characters; choose a smaller text box.");
      if (generation !== state.generation || token !== state.token) return;
      const instruction = byId("prompt").value.trim();
      if (!instruction) throw new Error("Enter an instruction first.");
      const message = `${safe(instruction)}\n\n[PowerPoint selected text shape]\nText: ${context.text}`;
      const result = await api("/v1/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId, message,
        preferred_language: state.language, request_id: requestId }) });
      if (generation !== state.generation || token !== state.token || sessionId !== state.sessionId) return;
      state.proposal = { text: validateProposal(result, context.text), target: context, sessionId, provenance: { intent: result.intent, routing_source: result.routing_source,
        response_source: result.response_source, provider_used: result.provider_used, model_used: result.model_used } }; renderProposal(state.proposal);
      status("Review the proposal, then Apply to the original selected text shape.", false);
    } finally { state.busy = false; controls(); }
  }
  async function applyProposal() {
    if (!state.proposal) throw new Error("No proposal to apply.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable; proposal was not applied.");
    const proposal = state.proposal, generation = state.generation;
    state.busy = true; controls();
    try {
      await root.PowerPoint.run(async context => {
        const target = await selectedTarget(context);
        if (!state.token || generation !== state.generation || proposal.sessionId !== state.sessionId ||
            target.slideId !== proposal.target.slideId || target.shapeId !== proposal.target.shapeId || target.text !== proposal.target.text)
          throw new Error("Selection or text changed. Create and review a new proposal before Apply.");
        target.shape.textFrame.textRange.text = proposal.text; await context.sync();
      }); clearProposal(); status("Proposal applied after confirmation.", false);
    } catch (error) { clearProposal(); throw error; }
    finally { state.busy = false; controls(); }
  }
  function renderProposal(value) { if (!byId("proposal")) return; byId("proposal").textContent = value ? value.text : "";
    byId("provenance").textContent = value ? JSON.stringify(value.provenance, null, 2) : ""; byId("apply").disabled = !value; }
  function status(message, error) { if (byId("status")) { byId("status").textContent = safe(message); byId("status").className = error ? "error" : "ok"; } }
  async function guarded(fn) { try { status("Working…", false); await fn(); } catch (error) { status(error.message, true); } }
  function bind() { byId("login").onclick = () => guarded(login); byId("logout").onclick = logout; byId("newSession").onclick = () => guarded(createSession);
    byId("ask").onclick = () => guarded(ask); byId("apply").onclick = () => guarded(applyProposal);
    byId("session").onchange = event => { state.sessionId = event.target.value; clearProposal(); }; byId("language").onchange = event => { state.language = event.target.value; clearProposal(); }; }
  if (root.Office?.onReady) root.Office.onReady(info => { if (info.host === root.Office.HostType.PowerPoint) bind(); });
  const exported = { safe, state, api, login, logout, readSlideContext, ask, applyProposal, renderProposal, validateProposal };
  if (typeof module !== "undefined") module.exports = exported; else root.DusnxPowerPoint = exported;
})(typeof window !== "undefined" ? window : globalThis);
