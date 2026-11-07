(function (root) {
  "use strict";
  const MAX_SLIDES = 6, MAX_BULLETS = 5, MAX_TITLE = 120, MAX_BULLET = 180, MAX_TOTAL = 4000;
  const state = { token: null, sessionId: null, proposal: null, language: "auto", generation: 0, busy: false };
  let templateCache = null;
  const byId = id => typeof document === "undefined" ? null : document.getElementById(id);
  const safe = value => String(value == null ? "" : value).replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 4000);
  const mode = () => byId("mode")?.value === "generate" ? "generate" : "edit";
  function clearProposal() { state.generation++; state.proposal = null; renderProposal(null); }
  function controls() {
    for (const id of ["ask", "newSession", "session", "language", "login", "mode", "count"]) if (byId(id)) byId(id).disabled = state.busy;
    if (byId("apply")) byId("apply").disabled = state.busy || !state.proposal;
  }
  async function api(path, options = {}) {
    const base = String(root.DUSNX_GATEWAY || "").replace(/\/$/, "");
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
  function validateProvenance(result) {
    if (!result || result.provider_ok !== true || result.response_source !== "llm" || result.provider_called !== true ||
        typeof result.provider_used !== "string" || !result.provider_used.trim() ||
        typeof result.model_used !== "string" || !result.model_used.trim())
      throw new Error("A measured LLM response with provenance is required; no proposal was created.");
  }
  function validateProposal(result, originalText) {
    validateProvenance(result);
    if (typeof result.reply !== "string" || !result.reply.trim() || result.reply.length > 4000 ||
        /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(result.reply))
      throw new Error("Proposal must be non-empty plain text of at most 4000 characters.");
    const text = result.reply.trim();
    if (/^\s*(?:```|[\[{])/.test(text)) throw new Error("Structured metadata is not slide text.");
    if (text === originalText.trim()) throw new Error("Proposal does not change the selected text.");
    return text;
  }
  function outlineMessage(instruction, count, language) {
    const lang = language === "vi" ? "Vietnamese" : language === "en" ? "English" : "the same language as the instruction";
    return `${instruction}\n\n[PowerPoint slide generation]\nCreate exactly ${count} slide(s) in ${lang}.\nReturn only the outline in this exact format:\n# Slide title\n- bullet text\n- bullet text\nRules: one "# " title per slide, 1-${MAX_BULLETS} "- " bullets under each title, each bullet at most 160 characters, no preamble, no explanations, no numbering, no code fences.`;
  }
  const SLIDE_LABEL = /^(?:slide|bài)\s*\d+\s*(?:[-–—:.)]|\s-)\s*/i;
  const TITLE_LABEL = /^(?:title|tiêu đề)\s*[:：]\s*/i;
  const BULLET_LABEL = /^(?:bullet(?:\s*text)?|gạch đầu dòng)\s*[:：]\s*/i;
  function parseOutline(reply) {
    if (typeof reply !== "string" || !reply.trim()) throw new Error("The model returned an empty slide outline.");
    const text = reply.replace(/^\uFEFF/, "").trim();
    if (text.includes("```")) throw new Error("Code fences are not a slide outline.");
    if (/^[\[{]/.test(text)) throw new Error("Structured metadata is not a slide outline.");
    const plan = [];
    let current = null, preamble = 0;
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(line)) continue;
      const heading = line.match(/^#{1,3}\s+(.+)$/);
      if (heading) {
        const title = heading[1].replace(SLIDE_LABEL, "").replace(TITLE_LABEL, "").trim();
        if (!title || /^(?:slide|bài)\s*\d+$/i.test(title)) continue;
        if (current) plan.push(current);
        current = { title, bullets: [] };
        continue;
      }
      if (line.startsWith("#")) throw new Error("Slide titles must start with '# ' on their own line.");
      const bullet = line.match(/^[-•*]\s+(.+)$/);
      if (bullet) {
        if (!current) throw new Error("The outline starts with a bullet before any slide title.");
        current.bullets.push(bullet[1].replace(BULLET_LABEL, "").trim());
        continue;
      }
      if (!current) {
        const labelled = line.match(/^(?:slide|bài)\s*\d+\s*[-–—:.)]\s*(.+)$/i);
        if (labelled && labelled[1].trim()) { current = { title: labelled[1].replace(TITLE_LABEL, "").trim(), bullets: [] }; continue; }
        if (/^(?:slide|bài)\s*\d+\s*[-–—:.)]?$/i.test(line)) continue;
        if (++preamble > 3 || line.length > 300) throw new Error(`Unexpected outline line: ${safe(line).slice(0, 80)}`);
        continue;
      }
      current.bullets.push(line.replace(BULLET_LABEL, "").trim());
    }
    if (current) plan.push(current);
    return plan;
  }
  function validatePlan(plan, expectedCount) {
    if (!Array.isArray(plan) || !plan.length) throw new Error("The slide outline is empty.");
    if (plan.length > MAX_SLIDES) throw new Error(`At most ${MAX_SLIDES} slides can be generated at once.`);
    if (expectedCount != null && plan.length !== expectedCount) throw new Error(`Expected ${expectedCount} slide(s), received ${plan.length}.`);
    let total = 0;
    const normalized = plan.map((slide, index) => {
      const title = typeof slide?.title === "string" ? slide.title.trim() : "";
      if (!title || title.length > MAX_TITLE) throw new Error(`Slide ${index + 1} needs a title of 1-${MAX_TITLE} characters.`);
      if (/[\u0000-\u001f\u007f]/.test(title)) throw new Error(`Slide ${index + 1} title contains control characters.`);
      if (!Array.isArray(slide.bullets) || !slide.bullets.length || slide.bullets.length > MAX_BULLETS)
        throw new Error(`Slide ${index + 1} needs 1-${MAX_BULLETS} bullets.`);
      const bullets = slide.bullets.map((raw, bulletIndex) => {
        const bullet = typeof raw === "string" ? raw.trim() : "";
        if (!bullet || bullet.length > MAX_BULLET) throw new Error(`Slide ${index + 1} bullet ${bulletIndex + 1} must be 1-${MAX_BULLET} characters.`);
        if (/[\u0000-\u001f\u007f]/.test(bullet)) throw new Error(`Slide ${index + 1} bullet ${bulletIndex + 1} contains control characters.`);
        total += bullet.length;
        return bullet;
      });
      total += title.length;
      return { title, bullets };
    });
    if (total > MAX_TOTAL) throw new Error(`The slide outline exceeds ${MAX_TOTAL} characters.`);
    return normalized;
  }
  function formatPlan(plan) {
    return plan.map((slide, index) => `${index + 1}. ${slide.title}\n${slide.bullets.map(bullet => `   • ${bullet}`).join("\n")}`).join("\n\n");
  }
  function provenance(result) {
    return { intent: result.intent, routing_source: result.routing_source, response_source: result.response_source,
      provider_used: result.provider_used, model_used: result.model_used };
  }
  async function ask() {
    if (!state.token || !state.sessionId) throw new Error("Sign in and select a session first.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (mode() === "generate") return askPlan();
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
      state.proposal = { kind: "edit", text: validateProposal(result, context.text), target: context, sessionId, provenance: provenance(result) };
      renderProposal(state.proposal);
      status("Review the proposal, then Apply to the original selected text shape.", false);
    } finally { state.busy = false; controls(); }
  }
  async function askPlan() {
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable.");
    clearProposal(); state.busy = true; controls();
    const generation = state.generation, sessionId = state.sessionId, token = state.token;
    try {
      const instruction = byId("prompt").value.trim();
      if (!instruction) throw new Error("Enter an instruction first.");
      if (instruction.length > 2000) throw new Error("Instruction must be at most 2000 characters.");
      const requested = Number(byId("count")?.value || 3);
      if (!Number.isInteger(requested) || requested < 1 || requested > MAX_SLIDES) throw new Error(`Slide count must be between 1 and ${MAX_SLIDES}.`);
      const requestId = root.crypto?.randomUUID?.() || `ppt-${Date.now()}`;
      const result = await api("/v1/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId,
        message: outlineMessage(instruction, requested, state.language), preferred_language: state.language, request_id: requestId }) });
      if (generation !== state.generation || token !== state.token || sessionId !== state.sessionId) return;
      validateProvenance(result);
      const plan = validatePlan(parseOutline(result.reply), requested);
      state.proposal = { kind: "plan", plan, text: formatPlan(plan), sessionId, requested, provenance: provenance(result) };
      renderProposal(state.proposal);
      status(`Review ${plan.length} slide(s), then append them to the presentation.`, false);
    } finally { state.busy = false; controls(); }
  }
  function bytesBase64(bytes) {
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode.apply(null, bytes.subarray(index, index + 0x8000));
    return root.btoa(binary);
  }
  async function templateBase64() {
    if (templateCache) return templateCache;
    const response = await fetch("deck-template.pptx", { cache: "no-store" });
    if (!response.ok) throw new Error("The slide template is unavailable; no slides were added.");
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength < 1000 || buffer.byteLength > 2000000) throw new Error("The slide template is invalid; no slides were added.");
    templateCache = bytesBase64(new Uint8Array(buffer));
    return templateCache;
  }
  async function insertPlan(plan, base64, guard) {
    return root.PowerPoint.run(async context => {
      const slides = context.presentation.slides;
      slides.load("items/id"); await context.sync();
      const beforeCount = slides.items.length, beforeIds = new Set(slides.items.map(slide => slide.id));
      const targetSlideId = beforeCount ? `${slides.items[beforeCount - 1].id}#` : null;
      const added = [], addedIds = new Set();
      try {
        for (let index = plan.length - 1; index >= 0; index--) {
          guard();
          const options = { formatting: "UseDestinationTheme", ...(targetSlideId ? { targetSlideId } : {}) };
          context.presentation.insertSlidesFromBase64(base64, options);
          await context.sync();
          slides.load("items/id"); await context.sync();
          if (slides.items.length !== beforeCount + plan.length - index)
            throw new Error("The slide template did not insert exactly one slide.");
          for (const slide of slides.items) if (!beforeIds.has(slide.id) && !addedIds.has(slide.id)) { addedIds.add(slide.id); added.push(slide); }
        }
        if (added.length !== plan.length) throw new Error("The slide template did not insert the expected slides.");
        const deckOrder = slides.items.filter(slide => !beforeIds.has(slide.id));
        if (deckOrder.length !== plan.length) throw new Error("The inserted slides are not in the presentation.");
        for (let index = 0; index < plan.length; index++) {
          guard();
          const slide = deckOrder[index];
          slide.shapes.load("items/name"); await context.sync();
          const shapes = new Map(slide.shapes.items.map(shape => [shape.name, shape]));
          const title = shapes.get("DUSN-X Title"), body = shapes.get("DUSN-X Body");
          if (!title || !body) throw new Error("The slide template is missing its named title or body shape.");
          title.textFrame.textRange.text = plan[index].title;
          body.textFrame.textRange.text = plan[index].bullets.map(bullet => `• ${bullet}`).join("\r");
          const footer = shapes.get("DUSN-X Footer");
          if (footer) footer.textFrame.textRange.text = `DUSN-X · ${beforeCount + index + 1}`;
          await context.sync();
        }
        return { before: beforeCount, added: added.length };
      } catch (error) {
        try {
          for (let index = added.length - 1; index >= 0; index--) added[index].delete();
          await context.sync();
        } catch { /* the original error is reported below */ }
        throw error;
      }
    });
  }
  async function applyProposal() {
    if (!state.proposal) throw new Error("No proposal to apply.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable; proposal was not applied.");
    const proposal = state.proposal, generation = state.generation;
    state.busy = true; controls();
    try {
      if (proposal.kind === "plan") {
        const plan = validatePlan(proposal.plan, proposal.requested);
        const base64 = await templateBase64();
        const guard = () => {
          if (!state.token || generation !== state.generation || proposal.sessionId !== state.sessionId)
            throw new Error("Session changed. Create and review a new outline before Apply.");
        };
        guard();
        const result = await insertPlan(plan, base64, guard);
        clearProposal();
        status(result.before ? `Appended ${result.added} slide(s) after slide ${result.before} of the presentation.`
          : `Appended ${result.added} slide(s) to the empty presentation.`, false);
        return;
      }
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
  function updateMode() {
    const generate = mode() === "generate";
    if (byId("countRow")) byId("countRow").style.display = generate ? "" : "none";
    if (byId("ask")) byId("ask").textContent = generate ? "Create slide outline" : "Create proposal from selected text shape";
    if (byId("apply")) byId("apply").textContent = generate ? "Append slides to presentation" : "Apply to original text shape";
    if (byId("prompt")) byId("prompt").placeholder = generate
      ? "Ví dụ: Tạo 3 slide tóm tắt kế hoạch ra mắt DUSN-X cho khối vận hành."
      : "Ví dụ: Viết lại nội dung đang chọn, giữ nguyên ý.";
    clearProposal();
  }
  function bind() { byId("login").onclick = () => guarded(login); byId("logout").onclick = logout; byId("newSession").onclick = () => guarded(createSession);
    byId("ask").onclick = () => guarded(ask); byId("apply").onclick = () => guarded(applyProposal);
    byId("session").onchange = event => { state.sessionId = event.target.value; clearProposal(); }; byId("language").onchange = event => { state.language = event.target.value; clearProposal(); };
    if (byId("mode")) byId("mode").onchange = updateMode; updateMode(); }
  if (root.Office?.onReady) root.Office.onReady(info => { if (info.host === root.Office.HostType.PowerPoint) bind(); });
  const exported = { safe, state, api, login, logout, readSlideContext, ask, applyProposal, renderProposal, validateProposal,
    parseOutline, validatePlan, formatPlan, outlineMessage, MAX_SLIDES, MAX_BULLETS, MAX_TITLE, MAX_BULLET, MAX_TOTAL };
  if (typeof module !== "undefined") module.exports = exported; else root.DusnxPowerPoint = exported;
})(typeof window !== "undefined" ? window : globalThis);
