(function (root) {
  "use strict";
  const MAX_SLIDES = 6, MAX_BULLETS = 5, MAX_TITLE = 120, MAX_BULLET = 180, MAX_TOTAL = 4000;
  const MAX_TABLE_ROWS = 12, MAX_TABLE_COLS = 6, MAX_CELL = 160, MAX_TABLE_TOTAL = 4000;
  const MIN_CHART_ROWS = 2, MAX_CHART_ROWS = 12, MAX_CHART_LABEL = 60, MAX_CHART_TITLE = 120, MAX_CHART_TOTAL = 2000;
  const CHART_TYPES = new Set(["bar", "line", "pie"]);
  const state = { token: null, sessionId: null, proposal: null, language: "auto", generation: 0, busy: false, lastApply: null };
  let templateCache = null;
  const byId = id => typeof document === "undefined" ? null : document.getElementById(id);
  const safe = value => String(value == null ? "" : value).replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, 4000);
  const mode = () => byId("mode")?.value === "generate" ? "generate" : "edit";
  const layout = () => byId("layout")?.value === "table" ? "table" : "bullets";
  const afterSelected = () => byId("afterSelected")?.checked === true;
  const SENSITIVE = [
    [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, "private key"],
    [/\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b/, "API key"],
    [/\bBearer\s+[A-Za-z0-9._~+/-]{20,}/i, "bearer token"],
    [/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/, "JSON Web Token"],
  ];
  function findSensitive(value) {
    const text = String(value == null ? "" : value);
    for (const [pattern, label] of SENSITIVE) if (pattern.test(text)) return label;
    return null;
  }
  function tableSupported() {
    const requirements = root.Office?.context?.requirements;
    return typeof requirements?.isSetSupported === "function" && requirements.isSetSupported("PowerPointApi", "1.8");
  }
  function chartSupported() {
    const requirements = root.Office?.context?.requirements;
    return typeof requirements?.isSetSupported === "function" && requirements.isSetSupported("PowerPointApi", "1.5");
  }
  function parseChartData(raw) {
    if (typeof raw !== "string" || !raw.trim()) throw new Error("Enter at least two data rows (label<TAB>value).");
    const text = raw.replace(/^\uFEFF/, "").trim();
    if (text.length > MAX_CHART_TOTAL) throw new Error(`Chart data exceeds ${MAX_CHART_TOTAL} characters.`);
    const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    if (lines.length < MIN_CHART_ROWS || lines.length > MAX_CHART_ROWS)
      throw new Error(`Chart data needs ${MIN_CHART_ROWS}-${MAX_CHART_ROWS} rows.`);
    const rows = lines.map((line, index) => {
      const cells = line.includes("\t") ? line.split("\t") : line.split("|");
      if (cells.length !== 2) throw new Error(`Row ${index + 1} must be "label<TAB>value".`);
      const label = cells[0].trim(), valueText = cells[1].trim().replace(/,/g, ".");
      if (!label || label.length > MAX_CHART_LABEL) throw new Error(`Row ${index + 1} needs a label of 1-${MAX_CHART_LABEL} characters.`);
      if (/[\u0000-\u001f\u007f]/.test(label)) throw new Error(`Row ${index + 1} label contains control characters.`);
      if (!/^-?\d+(?:\.\d+)?$/.test(valueText)) throw new Error(`Row ${index + 1} needs a plain number, for example 12.5.`);
      const value = Number(valueText);
      if (!Number.isFinite(value) || Math.abs(value) > 1e12) throw new Error(`Row ${index + 1} value is out of range.`);
      return { label, value };
    });
    return { labels: rows.map(row => row.label), values: rows.map(row => row.value) };
  }
  function clearProposal() { state.generation++; state.proposal = null; renderProposal(null); }
  function controls() {
    for (const id of ["ask", "newSession", "session", "language", "login", "mode", "count", "afterSelected", "layout",
      "chartTitle", "chartType", "chartData", "chartAfterSelected", "insertChart"])
      if (byId(id)) byId(id).disabled = state.busy;
    if (byId("apply")) byId("apply").disabled = state.busy || !state.proposal;
    if (byId("undo")) byId("undo").disabled = state.busy || !state.lastApply;
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
    state.token = state.sessionId = null; state.lastApply = null; clearProposal(); controls(); status("Disconnected", true);
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
  function tableMessage(instruction, count, language) {
    const lang = language === "vi" ? "Vietnamese" : language === "en" ? "English" : "the same language as the instruction";
    return `${instruction}\n\n[PowerPoint table slide]\nCreate exactly ${count} slide(s) in ${lang}, each with a short title and one table.\nReturn only this exact format:\n# Slide title\n| Header | Header |\n| --- | --- |\n| value | value |\nRules: one "# " title per slide, 1-${MAX_TABLE_COLS} columns, at most ${MAX_TABLE_ROWS} rows including the header row, each cell at most ${MAX_CELL} characters, no preamble, no explanations, no code fences.`;
  }
  function parseTablePlan(reply) {
    if (typeof reply !== "string" || !reply.trim()) throw new Error("The model returned an empty table outline.");
    const text = reply.replace(/^\uFEFF/, "").trim();
    if (text.includes("```")) throw new Error("Code fences are not a table outline.");
    if (/^[\[{]/.test(text)) throw new Error("Structured metadata is not a table outline.");
    const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const plans = [];
    let current = null;
    for (const line of lines) {
      const heading = line.match(/^#{1,3}\s+(.+)$/);
      if (heading) {
        const title = heading[1].replace(SLIDE_LABEL, "").replace(TITLE_LABEL, "").trim();
        if (!title) throw new Error("Every table slide needs a '# Slide title' line.");
        if (current) plans.push(current);
        current = { title, table: [] };
        continue;
      }
      if (!current) throw new Error("The table outline starts before any slide title.");
      if (!line.startsWith("|")) throw new Error(`Unexpected table line: ${safe(line).slice(0, 80)}`);
      const cells = line.replace(/^\|/, "").replace(/\|$/, "").split("|").map(cell => cell.trim());
      if (cells.every(cell => /^:?-{2,}:?$/.test(cell))) continue;
      current.table.push(cells);
    }
    if (current) plans.push(current);
    return validateTablePlan(plans);
  }
  function validateTable(rows) {
    if (!Array.isArray(rows) || rows.length < 2) throw new Error("A table needs a header row and at least one data row.");
    if (rows.length > MAX_TABLE_ROWS) throw new Error(`At most ${MAX_TABLE_ROWS} table rows are supported.`);
    const columns = Array.isArray(rows[0]) ? rows[0].length : 0;
    if (!columns || columns > MAX_TABLE_COLS) throw new Error(`A table needs 1-${MAX_TABLE_COLS} columns.`);
    let total = 0;
    const normalized = rows.map((row, rowIndex) => {
      if (!Array.isArray(row) || row.length !== columns) throw new Error(`Table row ${rowIndex + 1} does not have ${columns} cells.`);
      return row.map((raw, columnIndex) => {
        const cell = typeof raw === "string" ? raw.trim() : "";
        if (rowIndex === 0 && !cell) throw new Error(`Header cell ${columnIndex + 1} is empty.`);
        if (cell.length > MAX_CELL) throw new Error(`Cell ${rowIndex + 1}:${columnIndex + 1} exceeds ${MAX_CELL} characters.`);
        if (/[\u0000-\u001f\u007f]/.test(cell)) throw new Error(`Cell ${rowIndex + 1}:${columnIndex + 1} contains control characters.`);
        total += cell.length;
        return cell;
      });
    });
    if (total > MAX_TABLE_TOTAL) throw new Error(`The table outline exceeds ${MAX_TABLE_TOTAL} characters.`);
    return normalized;
  }
  function validateTablePlan(plans) {
    if (!Array.isArray(plans) || !plans.length) throw new Error("The table outline is empty.");
    if (plans.length > MAX_SLIDES) throw new Error(`At most ${MAX_SLIDES} slides can be generated at once.`);
    return plans.map((plan, index) => {
      const title = typeof plan?.title === "string" ? plan.title.trim() : "";
      if (!title || title.length > MAX_TITLE) throw new Error(`Slide ${index + 1} needs a title of 1-${MAX_TITLE} characters.`);
      if (/[\u0000-\u001f\u007f]/.test(title)) throw new Error(`Slide ${index + 1} title contains control characters.`);
      return { title, table: validateTable(plan.table) };
    });
  }
  function formatTable(rows) { return rows.map(row => row.join(" | ")).join("\n"); }
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
      if (/^(?:slide|bài)\s*\d+\s*[-–—:.)]?$/i.test(line)) continue;
      const labelled = line.match(/^(?:slide|bài)\s*\d+\s*[-–—:.)]\s*(.+)$/i);
      if (labelled && labelled[1].trim()) {
        if (current) plan.push(current);
        current = { title: labelled[1].replace(TITLE_LABEL, "").trim(), bullets: [] };
        continue;
      }
      if (!current) {
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
      const secret = findSensitive(instruction) || findSensitive(context.text);
      if (secret) throw new Error(`The selection or instruction looks like it contains a ${secret}. Remove secrets before sending them to the provider.`);
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
      const secret = findSensitive(instruction);
      if (secret) throw new Error(`The instruction looks like it contains a ${secret}. Remove secrets before sending it to the provider.`);
      const requested = Number(byId("count")?.value || 3);
      if (!Number.isInteger(requested) || requested < 1 || requested > MAX_SLIDES) throw new Error(`Slide count must be between 1 and ${MAX_SLIDES}.`);
      const tables = layout() === "table";
      if (tables && !tableSupported())
        throw new Error("This PowerPoint version cannot insert tables (PowerPointApi 1.8 or newer is required).");
      const target = await plannedTarget();
      if (generation !== state.generation || token !== state.token) return;
      const requestId = root.crypto?.randomUUID?.() || `ppt-${Date.now()}`;
      const result = await api("/v1/chat", { method: "POST", body: JSON.stringify({ session_id: sessionId,
        message: tables ? tableMessage(safe(instruction), requested, state.language) : outlineMessage(instruction, requested, state.language),
        preferred_language: state.language, request_id: requestId }) });
      if (generation !== state.generation || token !== state.token || sessionId !== state.sessionId) return;
      validateProvenance(result);
      if (tables) {
        const plan = parseTablePlan(result.reply);
        if (plan.length !== requested) throw new Error(`Expected ${requested} slide(s), received ${plan.length}.`);
        state.proposal = { kind: "table", plan, text: plan.map((slide, index) => `${index + 1}. ${slide.title}\n${formatTable(slide.table)}`).join("\n\n"),
          sessionId, requested, targetId: target.id, targetLabel: target.label, provenance: provenance(result) };
        renderProposal(state.proposal);
        status(`Review ${plan.length} table slide(s), then insert them ${target.label}.`, false);
        return;
      }
      const plan = validatePlan(parseOutline(result.reply), requested);
      state.proposal = { kind: "plan", plan, text: formatPlan(plan), sessionId, requested,
        targetId: target.id, targetLabel: target.label, provenance: provenance(result) };
      renderProposal(state.proposal);
      status(`Review ${plan.length} slide(s), then insert them ${target.label}.`, false);
    } finally { state.busy = false; controls(); }
  }
  async function plannedTarget(after = afterSelected()) {
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable.");
    return root.PowerPoint.run(async context => {
      const slides = context.presentation.slides; slides.load("items/id");
      // Only request the selection when the user asked for it; older hosts that
      // can generate slides still work without PowerPointApi selection support.
      const selected = after ? context.presentation.getSelectedSlides() : null;
      if (selected) selected.load("items/id");
      await context.sync();
      if (!slides.items.length) return { id: null, label: "into the empty presentation" };
      const chosen = selected ? selected.items[0] : null;
      const index = chosen ? slides.items.findIndex(slide => String(slide.id) === String(chosen.id)) : -1;
      if (index >= 0) return { id: String(chosen.id), label: `after slide ${index + 1}` };
      const last = slides.items[slides.items.length - 1];
      return { id: String(last.id), label: `after slide ${slides.items.length}` };
    });
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
  async function insertPlan(plan, base64, guard, requestedTargetId) {
    return root.PowerPoint.run(async context => {
      const slides = context.presentation.slides;
      slides.load("items/id"); await context.sync();
      const beforeCount = slides.items.length, beforeIds = new Set(slides.items.map(slide => String(slide.id)));
      // Real hosts can return slide ids such as "256#3520995159"; keep them intact.
      const targetSlideId = requestedTargetId ? String(requestedTargetId) : null;
      if (targetSlideId && !beforeIds.has(targetSlideId))
        throw new Error("The target slide no longer exists. Create and review a new outline before Apply.");
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
          for (const slide of slides.items) if (!beforeIds.has(String(slide.id)) && !addedIds.has(String(slide.id))) { addedIds.add(String(slide.id)); added.push(slide); }
        }
        if (added.length !== plan.length) throw new Error("The slide template did not insert the expected slides.");
        const deckOrder = slides.items.filter(slide => !beforeIds.has(String(slide.id)));
        if (deckOrder.length !== plan.length) throw new Error("The inserted slides are not in the presentation.");
        for (let index = 0; index < plan.length; index++) {
          guard();
          const slide = deckOrder[index];
          slide.shapes.load("items/name"); await context.sync();
          const shapes = new Map(slide.shapes.items.map(shape => [shape.name, shape]));
          const title = shapes.get("DUSN-X Title"), body = shapes.get("DUSN-X Body");
          if (!title) throw new Error("The slide template is missing its named title or body shape.");
          title.textFrame.textRange.text = plan[index].title;
          if (plan[index].table) {
            if (!tableSupported()) throw new Error("This PowerPoint version cannot insert tables (PowerPointApi 1.8 or newer is required).");
            if (body) body.delete();
            const rows = plan[index].table;
            const shape = slide.shapes.addTable(rows.length, rows[0].length,
              { left: 48, top: 120, width: 864, height: Math.min(340, Math.max(60, rows.length * 30)) });
            const table = shape.getTable(); table.load(); await context.sync();
            const cells = rows.map((_, row) => rows[0].map((__, column) => table.getCellOrNullObject(row, column)));
            cells.forEach(row => row.forEach(cell => cell.load("isNullObject")));
            await context.sync();
            cells.forEach((row, rowIndex) => row.forEach((cell, column) => {
              if (!cell.isNullObject) cell.text = rows[rowIndex][column];
            }));
            await context.sync();
          } else {
            if (!body) throw new Error("The slide template is missing its named title or body shape.");
            body.textFrame.textRange.text = plan[index].bullets.map(bullet => `• ${bullet}`).join("\r");
          }
          const footer = shapes.get("DUSN-X Footer");
          const position = slides.items.findIndex(item => String(item.id) === String(slide.id)) + 1;
          if (footer) footer.textFrame.textRange.text = `DUSN-X · ${position}`;
          await context.sync();
        }
        return { before: beforeCount, added: added.length, ids: deckOrder.map(slide => String(slide.id)) };
      } catch (error) {
        try {
          for (let index = added.length - 1; index >= 0; index--) added[index].delete();
          await context.sync();
        } catch { /* the original error is reported below */ }
        throw error;
      }
    });
  }
  async function insertChart() {
    if (!state.token || !state.sessionId) throw new Error("Sign in and select a session first.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable.");
    if (!chartSupported()) throw new Error("This PowerPoint version cannot insert slides (PowerPointApi 1.5 or newer is required).");
    const title = String(byId("chartTitle")?.value || "").trim();
    if (!title || title.length > MAX_CHART_TITLE) throw new Error(`Chart title must be 1-${MAX_CHART_TITLE} characters.`);
    const type = CHART_TYPES.has(byId("chartType")?.value) ? byId("chartType").value : "bar";
    const raw = byId("chartData")?.value || "";
    const secret = findSensitive(title) || findSensitive(raw);
    if (secret) throw new Error(`The chart title or data looks like it contains a ${secret}. Remove secrets before sending it.`);
    const { labels, values } = parseChartData(raw);
    const target = await plannedTarget(byId("chartAfterSelected")?.checked === true);
    state.busy = true; controls();
    const generation = state.generation, token = state.token, sessionId = state.sessionId;
    try {
      const payload = await api("/v1/office/chart-slide", { method: "POST", body: JSON.stringify({ title, chart_type: type, labels, values }) });
      if (generation !== state.generation || token !== state.token || sessionId !== state.sessionId) return;
      const base64 = typeof payload.file_base64 === "string" ? payload.file_base64 : "";
      if (base64.length < 1000 || base64.length > 4000000) throw new Error("The chart slide response was invalid; no slide was added.");
      const inserted = await root.PowerPoint.run(async context => {
        const slides = context.presentation.slides; slides.load("items/id"); await context.sync();
        const before = new Set(slides.items.map(slide => String(slide.id))), count = slides.items.length;
        context.presentation.insertSlidesFromBase64(base64, { formatting: "UseDestinationTheme",
          ...(target.id ? { targetSlideId: String(target.id) } : {}) });
        await context.sync();
        slides.load("items/id"); await context.sync();
        const added = slides.items.filter(slide => !before.has(String(slide.id)));
        if (slides.items.length !== count + 1 || added.length !== 1) {
          for (const slide of added) slide.delete();
          await context.sync();
          throw new Error("The chart slide did not insert exactly one slide.");
        }
        return String(added[0].id);
      });
      state.lastApply = { ids: [inserted], label: target.label };
      reportApply("insert_chart", `${labels.length} data points from user input (${type})`);
      status(`Inserted one native chart slide ${target.label}.`, false);
    } finally { state.busy = false; controls(); }
  }
  function reportApply(eventType, content) {
    if (!state.token) return;
    api("/v1/me/events", { method: "POST", body: JSON.stringify({ platform: "powerpoint", event_type: eventType,
      content: safe(content), event_id: root.crypto?.randomUUID?.() || `ppt-${Date.now()}` }) }).catch(() => {});
  }
  async function undoLastApply() {
    const last = state.lastApply;
    if (!last) throw new Error("No slide insertion to undo.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable.");
    state.busy = true; controls();
    try {
      const removed = await root.PowerPoint.run(async context => {
        const slides = context.presentation.slides; slides.load("items/id"); await context.sync();
        const ids = new Set(last.ids.map(String));
        const doomed = slides.items.filter(slide => ids.has(String(slide.id)));
        for (const slide of doomed) slide.delete();
        await context.sync();
        return doomed.length;
      });
      state.lastApply = null;
      reportApply("undo", `removed ${removed} slide(s)`);
      status(removed ? `Removed ${removed} inserted slide(s).` : "The inserted slides were already removed.", false);
    } finally { state.busy = false; controls(); }
  }
  async function applyProposal() {
    if (!state.proposal) throw new Error("No proposal to apply.");
    if (state.busy) throw new Error("Wait for the current operation.");
    if (!root.PowerPoint?.run) throw new Error("Office API is unavailable; proposal was not applied.");
    const proposal = state.proposal, generation = state.generation;
    state.busy = true; controls();
    try {
      if (proposal.kind === "plan" || proposal.kind === "table") {
        const plan = proposal.kind === "table" ? validateTablePlan(proposal.plan) : validatePlan(proposal.plan, proposal.requested);
        if (plan.length !== proposal.requested) throw new Error(`Expected ${proposal.requested} slide(s), received ${plan.length}.`);
        if (proposal.kind === "table" && !tableSupported())
          throw new Error("This PowerPoint version cannot insert tables (PowerPointApi 1.8 or newer is required).");
        const base64 = await templateBase64();
        const guard = () => {
          if (!state.token || generation !== state.generation || proposal.sessionId !== state.sessionId)
            throw new Error("Session changed. Create and review a new outline before Apply.");
        };
        guard();
        const result = await insertPlan(plan, base64, guard, proposal.targetId);
        state.lastApply = { ids: result.ids, label: proposal.targetLabel };
        clearProposal();
        reportApply("apply", `${proposal.kind === "table" ? "table" : "bullets"} slides=${result.added}`);
        status(result.before ? `Inserted ${result.added} slide(s) ${proposal.targetLabel}.`
          : `Inserted ${result.added} slide(s) into the empty presentation.`, false);
        return;
      }
      await root.PowerPoint.run(async context => {
        const target = await selectedTarget(context);
        if (!state.token || generation !== state.generation || proposal.sessionId !== state.sessionId ||
            target.slideId !== proposal.target.slideId || target.shapeId !== proposal.target.shapeId || target.text !== proposal.target.text)
          throw new Error("Selection or text changed. Create and review a new proposal before Apply.");
        target.shape.textFrame.textRange.text = proposal.text; await context.sync();
      }); clearProposal(); reportApply("apply", `text rewrite ${proposal.text.length} characters`);
      status("Proposal applied after confirmation.", false);
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
    if (byId("targetRow")) byId("targetRow").style.display = generate ? "" : "none";
    if (byId("layoutRow")) byId("layoutRow").style.display = generate ? "" : "none";
    if (byId("ask")) byId("ask").textContent = generate ? "Create slide outline" : "Create proposal from selected text shape";
    if (byId("apply")) byId("apply").textContent = generate ? "Append slides to presentation" : "Apply to original text shape";
    if (byId("prompt")) byId("prompt").placeholder = generate
      ? "Ví dụ: Tạo 3 slide tóm tắt kế hoạch ra mắt DUSN-X cho khối vận hành."
      : "Ví dụ: Viết lại nội dung đang chọn, giữ nguyên ý.";
    clearProposal();
  }
  function bind() { byId("login").onclick = () => guarded(login); byId("logout").onclick = logout; byId("newSession").onclick = () => guarded(createSession);
    byId("ask").onclick = () => guarded(ask); byId("apply").onclick = () => guarded(applyProposal); byId("undo").onclick = () => guarded(undoLastApply);
    if (byId("insertChart")) byId("insertChart").onclick = () => guarded(insertChart);
    byId("session").onchange = event => { state.sessionId = event.target.value; clearProposal(); }; byId("language").onchange = event => { state.language = event.target.value; clearProposal(); };
    if (byId("mode")) byId("mode").onchange = updateMode; updateMode();
    if (byId("layout")) byId("layout").onchange = () => { clearProposal(); status("Generated content changed. Create a new outline.", false); };
    if (byId("afterSelected")) byId("afterSelected").onchange = () => { clearProposal(); status("Insertion target changed. Create a new outline.", false); }; }
  if (root.Office?.onReady) root.Office.onReady(info => { if (info.host === root.Office.HostType.PowerPoint) bind(); });
  const exported = { safe, state, api, login, logout, readSlideContext, ask, applyProposal, undoLastApply, renderProposal, validateProposal,
    parseOutline, validatePlan, formatPlan, outlineMessage, plannedTarget, tableMessage, parseTablePlan, validateTable, validateTablePlan, formatTable,
    tableSupported, findSensitive, MAX_SLIDES, MAX_BULLETS, MAX_TITLE, MAX_BULLET, MAX_TOTAL, MAX_TABLE_ROWS, MAX_TABLE_COLS, MAX_CELL, MAX_TABLE_TOTAL,
    chartSupported, parseChartData, insertChart, MIN_CHART_ROWS, MAX_CHART_ROWS, MAX_CHART_LABEL, MAX_CHART_TITLE, MAX_CHART_TOTAL };
  if (typeof module !== "undefined") module.exports = exported; else root.DusnxPowerPoint = exported;
})(typeof window !== "undefined" ? window : globalThis);
