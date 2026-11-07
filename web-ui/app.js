/**
 * DUSN-X Web Assistant — Main Application Logic
 *
 * Security notes:
 * - All user/API content is set via .textContent (never innerHTML on untrusted data)
 * - Tokens stored in memory only (sessionStorage for page reloads, cleared on logout)
 * - User cannot supply arbitrary linkedUserId to read other users' memory
 */

const GATEWAY = window.DUSNX_GATEWAY || (window.location?.protocol?.startsWith("http") ? "" : "http://localhost:8080");

// ── State ──────────────────────────────────────────────────────────────────────
let authToken = sessionStorage.getItem("dusnx_token") || null;
let authGeneration = 0;
let currentUser = null;
let currentSessionId = null;
let historyGeneration = 0;
let nextMessageBefore = null;
let historyLoading = false;

function resetMessageHistory() {
  historyGeneration += 1;
  nextMessageBefore = null;
  historyLoading = false;
  el("olderMessagesBtn").hidden = true;
  el("olderMessagesBtn").disabled = false;
  el("sendBtn").disabled = isSending;
}
let allMemories = [];
let allProjects = [];
let nextTimelineCursor = null;
let isSending = false;
let isResolving = false;
let isCreatingSession = false;
let failedRequest = null;
let preferredLanguage = (typeof localStorage !== "undefined" && localStorage.getItem("dusnx_language")) || "auto";

// ── Utilities ──────────────────────────────────────────────────────────────────

function el(id) { return document.getElementById(id); }

function safeText(container, text) {
  // Always use textContent for untrusted content — never innerHTML
  container.textContent = typeof text === "string" ? text : JSON.stringify(text, null, 2);
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch { return iso; }
}

async function apiFetch(path, options = {}) {
  // Use explicit DUSNX_GATEWAY if set, otherwise relative "" so requests route through
  // Gateway (:8080) in native mode or Nginx (:3000) in Docker Compose mode.
  const base = window.DUSNX_GATEWAY || "";
  const generation = authGeneration;
  const requestToken = authToken;
  const assertCurrentSession = () => {
    if (generation !== authGeneration || requestToken !== authToken) {
      const error = new Error("Phiên đăng nhập đã thay đổi; bỏ qua phản hồi cũ.");
      error.name = "SessionChangedError";
      throw error;
    }
  };
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  let resp;
  try {
    resp = await fetch(`${base}${path}`, { ...options, headers });
  } catch (err) {
    assertCurrentSession();
    throw new Error(`Không thể kết nối Gateway (${err.message}). Vui lòng đảm bảo Gateway đang chạy tại ${GATEWAY || window.location?.origin || "http://localhost:8080"}.`);
  }
  assertCurrentSession();
  if (!resp.ok) {
    if (resp.status === 401 && authToken) {
      clearAuthentication();
      el("loginError").textContent = "Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục; nội dung chưa gửi vẫn được giữ.";
      el("loginError").hidden = false;
      throw new Error("Phiên đăng nhập không hợp lệ hoặc đã hết hạn.");
    }
    let msg = `HTTP ${resp.status}`;
    try {
      const ct = resp.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        const body = await resp.json();
        msg = body.detail || body.message || msg;
      } else if (resp.status === 404) {
        msg = `HTTP 404: Đường dẫn '${path}' không tồn tại trên máy chủ này. Nếu bạn đang chạy 'python -m http.server 3000' mà không có proxy, vui lòng mở Web qua Gateway: ${window.location?.origin || "http://localhost:8080"} (Native) hoặc http://localhost:3000 (Docker Compose).`;
      }
    } catch {}
    assertCurrentSession();
    throw new Error(msg);
  }
  if (resp.status === 204) return null;
  const data = await resp.json();
  assertCurrentSession();
  return data;
}


// ── Auth ───────────────────────────────────────────────────────────────────────

function switchTab(tab) {
  const isLogin = tab === "login";
  el("loginForm").hidden = !isLogin;
  el("registerForm").hidden = isLogin;
  el("tabLogin").classList.toggle("active", isLogin);
  el("tabRegister").classList.toggle("active", !isLogin);
  el("tabLogin").setAttribute("aria-selected", String(isLogin));
  el("tabRegister").setAttribute("aria-selected", String(!isLogin));
}

async function handleLogin(event) {
  event.preventDefault();
  const btn = el("loginBtn");
  const errorEl = el("loginError");
  errorEl.hidden = true;
  btn.disabled = true;
  btn.textContent = "Đang đăng nhập…";
  try {
    const data = await apiFetch("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: el("loginUsername").value.trim(),
        password: el("loginPassword").value,
      }),
    });
    authGeneration += 1;
    authToken = data.token;
    sessionStorage.setItem("dusnx_token", authToken);
    await enterApp();
  } catch (err) {
    if (err.name === "SessionChangedError") return;
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Đăng nhập";
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const btn = el("registerBtn");
  const errorEl = el("registerError");
  errorEl.hidden = true;
  btn.disabled = true;
  btn.textContent = "Đang tạo tài khoản…";
  try {
    await apiFetch("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username: el("regUsername").value.trim(),
        password: el("regPassword").value,
      }),
    });
    // Auto-login after register
    const data = await apiFetch("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: el("regUsername").value.trim(),
        password: el("regPassword").value,
      }),
    });
    authGeneration += 1;
    authToken = data.token;
    sessionStorage.setItem("dusnx_token", authToken);
    await enterApp();
  } catch (err) {
    if (err.name === "SessionChangedError") return;
    errorEl.textContent = err.message;
    errorEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Tạo tài khoản";
  }
}

function clearAuthentication() {
  authGeneration += 1;
  authToken = null;
  currentUser = null;
  currentSessionId = null;
  failedRequest = null;
  allMemories = [];
  allProjects = [];
  nextTimelineCursor = null;
  isSending = false;
  isResolving = false;
  isCreatingSession = false;
  resetMessageHistory();
  hideStatus();
  hideError();
  el("projectSelect").disabled = false;
  for (const id of ["messageList", "sessionList", "memoryList", "projectList",
                    "projectDecisions", "projectHistory", "timelineList"]) {
    el(id)?.replaceChildren();
  }
  renderPendingBanner(null);
  sessionStorage.removeItem("dusnx_token");
  showScreen("authScreen");
}

async function handleLogout() {
  const previousToken = authToken;
  clearAuthentication();
  if (!previousToken) return;
  // Revoke the captured token after clearing local state. A late response must
  // never clear or restore a different login that started in the meantime.
  try {
    await fetch(`${window.DUSNX_GATEWAY || ""}/v1/auth/logout`, {
      method: "POST", headers: { Authorization: `Bearer ${previousToken}` },
    });
  } catch {
    // Local logout remains effective when the network is unavailable.
  }
}

async function enterApp() {
  const generation = authGeneration;
  currentUser = await apiFetch("/v1/auth/me");
  showScreen("appScreen");
  if (el("languageSelect")) {
    el("languageSelect").value = preferredLanguage;
    el("languageSelect").onchange = () => {
      preferredLanguage = el("languageSelect").value;
      if (typeof localStorage !== "undefined") localStorage.setItem("dusnx_language", preferredLanguage);
      applyUiLanguage(preferredLanguage === "en" ? "en" : "vi");
    };
  }
  await Promise.all([loadSessions(), loadProjects(), checkProviderHealth()]);
  if (generation !== authGeneration) return;
  showView("chat");
  await startNewSession();
}

function applyUiLanguage(language) {
  document.documentElement.lang = language;
  const dictionary = language === "en" ? {
    newChatBtn: "＋ New chat", statusText: "Processing…", messageInput: "Type a message…"
  } : {
    newChatBtn: "＋ Phiên chat mới", statusText: "Đang xử lý…", messageInput: "Nhập tin nhắn…"
  };
  if (el("newChatBtn")) el("newChatBtn").textContent = dictionary.newChatBtn;
  if (el("statusText")) el("statusText").textContent = dictionary.statusText;
  if (el("messageInput")) el("messageInput").placeholder = dictionary.messageInput;
}

// ── App Init ───────────────────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  el(id).classList.add("active");
}

function showView(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".sidebar-nav-item").forEach(b => b.classList.remove("active"));
  if (view === "chat") {
    el("viewChat").classList.add("active");
  } else if (view === "memory") {
    el("viewMemory").classList.add("active");
    el("navMemory").classList.add("active");
    loadMemories();
  } else if (view === "projects") {
    el("viewProjects").classList.add("active");
    el("navProjects").classList.add("active");
    renderProjectsView();
  } else if (view === "timeline") {
    el("viewTimeline").classList.add("active");
    el("navTimeline").classList.add("active");
  }
}

function toggleSidebar() {
  el("sidebar").classList.toggle("open");
}

// ── Provider Health ────────────────────────────────────────────────────────────

async function checkProviderHealth() {
  const statusEl = el("providerStatus");
  const modelEl = el("modelStatus");
  try {
    const health = await apiFetch("/v1/health");
    const provider = health.provider || {};
    const modelLoaded = health.model_loaded;
    const providerOk = health.provider_ok;

    if (modelEl) {
      if (modelLoaded) {
        const checkpoint = (health.model_version || "").match(/[^:/]+\.pt/);
        const label = checkpoint ? checkpoint[0] : (health.model_version || "v2");
        modelEl.textContent = `⬡ Router: ${label} (${health.runtime_mode === "trained_dusnx" ? "trained" : "bootstrap"})`;
        modelEl.title = health.model_version || "";
        modelEl.className = "model-status ok";
      } else {
        modelEl.textContent = `⬡ DUSN-X: Bootstrap`;
        modelEl.className = "model-status";
      }
    }

    if (providerOk) {
      const fallback = provider.fallback;
      if (fallback && fallback.available) {
        statusEl.textContent = `✓ LLM dự phòng: ${fallback.configured_model || "ollama"} (sẵn sàng)`;
      } else {
        statusEl.textContent = `✓ LLM: ${provider.configured_model || provider.provider} (sẵn sàng)`;
      }
      statusEl.className = "provider-status ok";
    } else {
      const pName = provider.provider || "none";
      const err = provider.error ? `: ${provider.error.slice(0, 45)}` : "";
      if (pName === "ollama" && provider.reachable && provider.model_available === false) {
        statusEl.textContent = `✕ Ollama đang chạy nhưng chưa có model ${provider.configured_model || "được cấu hình"}`;
      } else if (pName === "ollama" && provider.error === "unreachable") {
        statusEl.textContent = "✕ Không kết nối được Ollama; kiểm tra dịch vụ và địa chỉ kết nối";
      } else {
        statusEl.textContent = `✕ LLM không khả dụng (${pName}${err})`;
      }
      statusEl.className = "provider-status err";
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = `✕ Không kết nối được Gateway/API: ${err.message.slice(0, 60)}`;
      statusEl.className = "provider-status err";
    }
  }
}


// ── Sessions ───────────────────────────────────────────────────────────────────

async function loadSessions() {
  try {
    const sessions = await apiFetch("/v1/sessions");
    renderSessionList(sessions);
  } catch (err) {
    showError(`Không tải được danh sách phiên: ${err.message}`);
  }
}

function renderSessionList(sessions) {
  const list = el("sessionList");
  list.replaceChildren();
  // Empty sessions are hidden unless they are the one currently open.
  const visible = sessions.filter(sess =>
    sess.message_count === undefined || sess.message_count > 0 || sess.session_id === currentSessionId);
  if (visible.length === 0) {
    const empty = document.createElement("li");
    empty.className = "session-empty";
    empty.textContent = "Chưa có phiên chat";
    list.appendChild(empty);
  }
  for (const sess of visible) {
    const li = document.createElement("li");
    li.role = "listitem";
    const btn = document.createElement("button");
    btn.className = "session-item" + (sess.session_id === currentSessionId ? " active" : "");
    btn.setAttribute("data-session-id", sess.session_id);
    const textEl = document.createElement("span");
    textEl.className = "session-item-text";
    textEl.textContent = sess.title || "Phiên chat mới";  // textContent — safe
    btn.appendChild(textEl);
    btn.onclick = () => openSession(sess.session_id, sess.title);
    li.appendChild(btn);
    list.appendChild(li);
  }
}

async function startNewSession() {
  if (isSending || isResolving || isCreatingSession) return;
  // A session row is created only when the first message is sent. Creating it
  // here left a trail of empty "Phiên chat mới" rows on every login.
  currentSessionId = null;
  resetMessageHistory();
  el("messageList").replaceChildren();
  el("welcomeState").style.display = "";
  el("chatTitle").textContent = "Phiên chat mới";
  el("chatMeta").textContent = "";
  el("mobileTitle").textContent = "DUSN-X";
  renderPendingBanner(null);
  showView("chat");
  el("messageInput").focus();
}

async function ensureSession() {
  if (currentSessionId || isCreatingSession) return;
  isCreatingSession = true;
  try {
    const sess = await apiFetch("/v1/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "Phiên chat mới" }),
    });
    currentSessionId = sess.session_id;
  } finally {
    isCreatingSession = false;
  }
}

async function openSession(sessionId, title) {
  if (isSending || isResolving) return;
  currentSessionId = sessionId;
  resetMessageHistory();
  const generation = historyGeneration;
  historyLoading = true;
  el("sendBtn").disabled = true;
  el("chatTitle").textContent = title || "Phiên chat";
  el("mobileTitle").textContent = title || "DUSN-X";
  el("welcomeState").style.display = "none";
  el("messageList").replaceChildren();
  renderPendingBanner(null);
  showView("chat");
  // Close mobile sidebar
  el("sidebar").classList.remove("open");
  // Mark active
  document.querySelectorAll(".session-item").forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-session-id") === sessionId);
  });
  // Load history
  try {
    const page = await apiFetch(`/v1/sessions/${sessionId}/messages/page`);
    if (generation !== historyGeneration) return;
    const messages = page.messages;
    for (const msg of messages) {
      appendMessageBubble(msg.role, msg.content, {
        memory_ids_used: msg.memory_ids_used,
        state_version: msg.state_version,
        created_at: msg.created_at,
      });
    }
    if (messages.length > 0) el("welcomeState").style.display = "none";
    nextMessageBefore = page.next_before;
    el("olderMessagesBtn").hidden = !nextMessageBefore;
    scrollToBottom();
    await checkPendingDecisions();
  } catch (err) {
    if (generation === historyGeneration) showError(`Không tải được lịch sử: ${err.message}`);
  } finally {
    if (generation === historyGeneration) {
      historyLoading = false;
      el("sendBtn").disabled = isSending;
    }
  }
}

async function loadOlderMessages() {
  if (!nextMessageBefore || historyLoading) return;
  const generation = historyGeneration;
  const sessionId = currentSessionId;
  const button = el("olderMessagesBtn");
  historyLoading = true;
  button.disabled = true;
  el("sendBtn").disabled = true;
  try {
    const page = await apiFetch(`/v1/sessions/${sessionId}/messages/page?before=${encodeURIComponent(nextMessageBefore)}`);
    if (generation !== historyGeneration) return;
    const list = el("messageList");
    const previousHeight = list.scrollHeight;
    const previousTop = list.scrollTop;
    const fragment = document.createDocumentFragment();
    for (const msg of page.messages) {
      fragment.appendChild(appendMessageBubble(msg.role, msg.content, {
        memory_ids_used: msg.memory_ids_used,
        state_version: msg.state_version,
        created_at: msg.created_at,
      }, false));
    }
    list.prepend(fragment);
    list.scrollTop = previousTop + list.scrollHeight - previousHeight;
    nextMessageBefore = page.next_before;
    button.hidden = !nextMessageBefore;
  } catch (err) {
    if (generation === historyGeneration) showError(`Không tải được tin nhắn cũ: ${err.message}`);
  } finally {
    if (generation === historyGeneration) {
      historyLoading = false;
      button.disabled = false;
      el("sendBtn").disabled = isSending;
    }
  }
}


// ── Chat ───────────────────────────────────────────────────────────────────────

function handleInputKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function autoResizeTextarea(ta) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
}

function useHint(btn) {
  el("messageInput").value = btn.textContent;
  autoResizeTextarea(el("messageInput"));
  el("messageInput").focus();
}

// ── Pending Decisions in Chat ──────────────────────────────────────────────────

async function checkPendingDecisions() {
  if (!currentSessionId) return;
  const generation = historyGeneration;
  try {
    const pendings = await apiFetch(`/v1/pending-decisions?session_id=${encodeURIComponent(currentSessionId)}`);
    if (generation !== historyGeneration) return;
    renderPendingBanner(pendings && pendings.length > 0 ? pendings[0] : null);
  } catch {
    if (generation === historyGeneration) renderPendingBanner(null);
  }
}

function renderPendingBanner(pending) {
  let banner = el("pendingDecisionBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "pendingDecisionBanner";
    banner.className = "pending-decision-banner";
    const inputArea = document.querySelector(".input-area");
    if (inputArea) inputArea.prepend(banner);
  }
  if (!pending) {
    banner.hidden = true;
    banner.replaceChildren();
    return;
  }
  banner.hidden = false;
  banner.replaceChildren();

  const title = document.createElement("div");
  title.className = "pending-title";
  title.textContent = "⚠️ Xác nhận sửa đổi quyết định:";

  const body = document.createElement("div");
  body.className = "pending-body";

  const oldP = document.createElement("p");
  const oldStrong = document.createElement("strong");
  oldStrong.textContent = "Cũ: ";
  const oldSpan = document.createElement("span");
  oldSpan.textContent = pending.old_content;
  oldP.appendChild(oldStrong);
  oldP.appendChild(oldSpan);

  const newP = document.createElement("p");
  const newStrong = document.createElement("strong");
  newStrong.textContent = "Mới: ";
  const newSpan = document.createElement("span");
  newSpan.textContent = pending.proposed_content;
  newP.appendChild(newStrong);
  newP.appendChild(newSpan);

  body.appendChild(oldP);
  body.appendChild(newP);

  const actions = document.createElement("div");
  actions.className = "pending-actions";

  const btnConfirm = document.createElement("button");
  btnConfirm.className = "btn-primary btn-sm";
  btnConfirm.textContent = "✓ Đồng ý sửa (Confirm)";
  btnConfirm.onclick = () => resolvePending(pending.pending_id, true);

  const btnReject = document.createElement("button");
  btnReject.className = "btn-secondary btn-sm";
  btnReject.textContent = "✕ Giữ bản cũ (Cancel)";
  btnReject.onclick = () => resolvePending(pending.pending_id, false);

  actions.appendChild(btnConfirm);
  actions.appendChild(btnReject);

  banner.appendChild(title);
  banner.appendChild(body);
  banner.appendChild(actions);
}

async function resolvePending(pendingId, accepted) {
  if (isResolving || isSending) return;
  const generation = authGeneration;
  isResolving = true;
  const buttons = el("pendingDecisionBanner")?.querySelectorAll("button") || [];
  buttons.forEach(b => { b.disabled = true; });
  try {
    showStatus("Đang xử lý quyết định…");
    const res = await apiFetch(`/v1/pending-decisions/${encodeURIComponent(pendingId)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ accepted }),
    });
    hideStatus();
    renderPendingBanner(null);
    if (accepted) {
      appendMessageBubble("assistant", `✅ Đã cập nhật quyết định thành công:\nCũ: ${res.resolved?.old_content || ""}\nMới: ${res.resolved?.proposed_content || ""}`, {
        created_at: new Date().toISOString(),
        intent: "decision_update",
      });
    } else {
      appendMessageBubble("assistant", `Đã huỷ sửa đổi, giữ nguyên quyết định hiện tại:\n${res.resolved?.old_content || ""}`, {
        created_at: new Date().toISOString(),
        intent: "decision_update_cancelled",
      });
    }
    await loadMemories();
    scrollToBottom();
  } catch (err) {
    if (err.name === "SessionChangedError") return;
    hideStatus();
    showError(`Lỗi xử lý quyết định: ${err.message}. Kiểm tra trí nhớ trước khi thử lại.`);
    await checkPendingDecisions();
  } finally {
    if (generation === authGeneration) {
      isResolving = false;
      buttons.forEach(b => { b.disabled = false; });
    }
  }
}

async function sendMessage(overrideText = null, { isRetry = false, retryRequest = null } = {}) {
  if (isSending || isResolving || historyLoading) return;
  const generation = authGeneration;
  const input = el("messageInput");
  const text = (overrideText !== null ? overrideText : input.value).trim();
  if (!text) return;
  if (retryRequest && (retryRequest.sessionId !== currentSessionId || retryRequest.projectId !== (el("projectSelect").value || null))) {
    showError("Mở lại phiên và dự án của tin nhắn bị lỗi trước khi thử lại.");
    return;
  }
  if (!currentSessionId) {
    await ensureSession();
  }

  if (generation !== authGeneration) return;
  if (!currentSessionId) return;
  const previous = retryRequest || (failedRequest && failedRequest.text === text && failedRequest.sessionId === currentSessionId && failedRequest.projectId === (el("projectSelect").value || null) ? failedRequest : null);
  isRetry = isRetry || !!previous;
  const requestId = previous?.requestId || (window.crypto?.randomUUID?.() || `web-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const sessionId = currentSessionId;
  const projectId = previous?.projectId || el("projectSelect").value || null;
  const submission = { text, sessionId, projectId, requestId };
  failedRequest = submission;
  isSending = true;
  if (overrideText === null) {
    input.value = "";
    input.style.height = "auto";
  }
  // Match the backend's first-message title so the header and sidebar agree.
  if (el("chatTitle").textContent === "Phiên chat mới") {
    const sessionTitle = text.slice(0, 60);
    el("chatTitle").textContent = sessionTitle;
    el("mobileTitle").textContent = sessionTitle;
  }
  el("sendBtn").disabled = true;
  el("projectSelect").disabled = true;
  hideError();

  // Show user message immediately only if not retry
  if (!isRetry) {
    el("welcomeState").style.display = "none";
    appendMessageBubble("user", text, { created_at: new Date().toISOString() });
    scrollToBottom();
  }

  // Show typing indicator
  showStatus("Đang xử lý…");

  try {
    const response = await apiFetch("/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        request_id: requestId,
        message: text,
        project_id: projectId || null,
        feedback_value: 0,
        is_retry: isRetry,
        preferred_language: preferredLanguage,
      }),
    });

    hideStatus();

    if (response.provider_ok) {
      failedRequest = null;
      if (input.value.trim() === text) input.value = "";
      appendMessageBubble("assistant", response.reply, {
        intent: response.intent,
        agent: response.selected_agent,
        routing: response.routing_source,
        runtime: response.runtime_mode,
        provider_ok: response.provider_ok,
        provider: response.provider_used,
        response_source: response.response_source,
        state_version: response.state_version,
        memory_ids_used: response.memory_ids_used,
        response_language: response.response_language,
        sources: response.sources,
        rag_used: response.rag_used,
        inspector: response.inspector,
        created_at: new Date().toISOString(),
      });
    } else {
      // Clear error presentation: DO NOT present error as valid AI reply
      appendProviderErrorCard(response.reply, response.provider_used, text, submission);
    }
    scrollToBottom();

    // Check for pending decisions
    await checkPendingDecisions();

    // Update session title in sidebar
    await loadSessions();
  } catch (err) {
    if (err.name === "SessionChangedError") return;
    hideStatus();
    if (!input.value.trim()) input.value = text;
    appendProviderErrorCard(`Lỗi gửi tin: ${err.message}`, null, text, submission);
    showError(`Lỗi gửi tin: ${err.message}`);
  } finally {
    if (generation === authGeneration) {
      isSending = false;
      el("sendBtn").disabled = false;
      el("projectSelect").disabled = false;
      el("messageInput").focus();
    }
  }
}

function appendProviderErrorCard(errorText, providerName, failedMessage, requestData = null) {
  const list = el("messageList");
  const card = document.createElement("div");
  card.className = "message system-error";

  const header = document.createElement("div");
  header.className = "error-header";
  header.textContent = `⚠️ Lỗi Provider sinh câu trả lời (${providerName || "LLM"})`;

  const body = document.createElement("div");
  body.className = "error-body";
  safeText(body, errorText);

  const actions = document.createElement("div");
  actions.className = "error-actions";

  const retryBtn = document.createElement("button");
  retryBtn.className = "btn-secondary btn-sm";
  retryBtn.textContent = "🔄 Thử lại (Retry)";
  retryBtn.onclick = () => {
    if (isSending || isResolving) return;
    if (requestData && (requestData.sessionId !== currentSessionId || requestData.projectId !== (el("projectSelect").value || null))) {
      showError("Mở lại phiên và dự án của tin nhắn bị lỗi trước khi thử lại.");
      return;
    }
    card.remove();
    sendMessage(failedMessage, { isRetry: true, retryRequest: requestData });
  };

  actions.appendChild(retryBtn);
  card.appendChild(header);
  card.appendChild(body);
  card.appendChild(actions);
  list.appendChild(card);
}

function textSpan(value) {
  if (typeof document.createTextNode === "function") return document.createTextNode(value);
  const span = document.createElement("span");
  span.textContent = value;
  return span;
}

// Inline markdown is tokenized with DOM nodes only: no string of HTML is ever
// produced, so model output cannot inject elements or attributes.
function appendInline(parent, value) {
  const text = String(value ?? "");
  const token = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|__([^_\n]+)__|\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)|\*([^*\n]+)\*|_([^_\n]+)_/g;
  let last = 0;
  let match;
  while ((match = token.exec(text)) !== null) {
    if (match.index > last) parent.appendChild(textSpan(text.slice(last, match.index)));
    if (match[1] !== undefined) {
      const code = document.createElement("code");
      code.textContent = match[1];
      parent.appendChild(code);
    } else if (match[2] !== undefined || match[3] !== undefined) {
      const strong = document.createElement("strong");
      appendInline(strong, match[2] !== undefined ? match[2] : match[3]);
      parent.appendChild(strong);
    } else if (match[4] !== undefined) {
      // Only http(s) URLs reach this branch; javascript: stays literal text.
      const link = document.createElement("a");
      link.textContent = match[4];
      link.href = match[5];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      parent.appendChild(link);
    } else {
      const em = document.createElement("em");
      appendInline(em, match[6] !== undefined ? match[6] : match[7]);
      parent.appendChild(em);
    }
    last = token.lastIndex;
  }
  if (last < text.length) parent.appendChild(textSpan(text.slice(last)));
}

function isMarkdownBlock(line) {
  return /^\s*```/.test(line) || /^#{1,4}\s/.test(line) || /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line) || /^\s*>\s?/.test(line);
}

function renderMarkdown(container, text) {
  const lines = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }

    const fence = line.match(/^\s*```([\w+-]*)\s*$/);
    if (fence) {
      const body = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { body.push(lines[i]); i += 1; }
      if (i < lines.length) i += 1;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      if (fence[1]) code.className = `language-${fence[1]}`;
      code.textContent = body.join("\n");
      pre.appendChild(code);
      container.appendChild(pre);
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      const node = document.createElement(`h${heading[1].length}`);
      appendInline(node, heading[2]);
      container.appendChild(node);
      i += 1;
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const list = document.createElement("ul");
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        const item = document.createElement("li");
        appendInline(item, lines[i].replace(/^\s*[-*+]\s+/, ""));
        list.appendChild(item);
        i += 1;
      }
      container.appendChild(list);
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const list = document.createElement("ol");
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        const item = document.createElement("li");
        appendInline(item, lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        list.appendChild(item);
        i += 1;
      }
      container.appendChild(list);
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quote = document.createElement("blockquote");
      let first = true;
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        if (!first) quote.appendChild(document.createElement("br"));
        appendInline(quote, lines[i].replace(/^\s*>\s?/, ""));
        first = false;
        i += 1;
      }
      container.appendChild(quote);
      continue;
    }

    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !isMarkdownBlock(lines[i])) {
      paragraph.push(lines[i]);
      i += 1;
    }
    const p = document.createElement("p");
    paragraph.forEach((entry, index) => {
      if (index > 0) p.appendChild(document.createElement("br"));
      appendInline(p, entry);
    });
    container.appendChild(p);
  }
}

function copyMessageText(button, text) {
  const done = label => {
    button.textContent = label;
    const timer = setTimeout(() => { button.textContent = "Sao chép"; }, 1600);
    if (timer && typeof timer.unref === "function") timer.unref();
  };
  const clipboard = typeof navigator !== "undefined" ? navigator.clipboard : null;
  if (!clipboard || typeof clipboard.writeText !== "function") {
    done("Không hỗ trợ");
    return;
  }
  Promise.resolve(clipboard.writeText(text)).then(() => done("Đã sao chép"), () => done("Lỗi sao chép"));
}

let memoryLookupPromise = null;
async function ensureMemoryLookup() {
  if (allMemories.length) return allMemories;
  if (!memoryLookupPromise) {
    memoryLookupPromise = apiFetch("/v1/memories?include_inactive=false&limit=100")
      .then(items => { allMemories = Array.isArray(items) ? items : []; return allMemories; })
      .catch(() => [])
      .finally(() => { memoryLookupPromise = null; });
  }
  return memoryLookupPromise;
}

function buildUsedMemoryCard(ids) {
  const details = document.createElement("details");
  details.className = "memory-used-card";
  const summary = document.createElement("summary");
  summary.textContent = `Trí nhớ đã dùng (${ids.length})`;
  const list = document.createElement("ul");
  details.appendChild(summary);
  details.appendChild(list);
  const fill = (loaded = false) => {
    list.replaceChildren();
    const used = ids.map(id => allMemories.find(mem => mem.memory_id === id)).filter(Boolean);
    for (const mem of used) {
      const item = document.createElement("li");
      // SAFE: textContent — memory content is user-owned data, never HTML
      item.textContent = `${mem.info_type}: ${mem.content}`;
      list.appendChild(item);
    }
    if (!used.length) {
      const item = document.createElement("li");
      item.textContent = loaded ? "Không tìm thấy nội dung trí nhớ đã dùng." : "Đang tải nội dung trí nhớ…";
      list.appendChild(item);
    }
    return used.length;
  };
  if (fill() === 0) ensureMemoryLookup().then(() => fill(true)).catch(() => fill(true));
  return details;
}

function appendMessageBubble(role, content, meta = {}, append = true) {
  const list = el("messageList");
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "U" : "⬡";

  const col = document.createElement("div");

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "assistant") {
    renderMarkdown(bubble, content);
  } else {
    // SAFE: textContent — never innerHTML
    safeText(bubble, content);
  }

  const metaEl = document.createElement("div");
  metaEl.className = "message-meta";

  if (meta.created_at) {
    const time = document.createElement("span");
    time.textContent = formatDate(meta.created_at);
    metaEl.appendChild(time);
  }

  if (role === "assistant") {
    if (meta.runtime) {
      const tag = document.createElement("span");
      tag.className = "meta-tag";
      tag.textContent = meta.runtime === "trained_dusnx" ? "DUSN-X" : "bootstrap";
      metaEl.appendChild(tag);
    }
    if (meta.provider) {
      const tag = document.createElement("span");
      tag.className = "meta-tag" + (meta.provider_ok ? "" : " warn");
      tag.textContent = meta.provider_ok ? `✓ ${meta.provider}` : `✕ ${meta.provider}`;
      metaEl.appendChild(tag);
    }
    if (meta.response_source && meta.response_source !== "llm") {
      const tag = document.createElement("span");
      tag.className = "meta-tag";
      tag.textContent = meta.response_source === "grounded_template" ? "Trích trí nhớ đã lưu" :
        meta.response_source === "rag_extract" ? "Trích tài liệu nội bộ" :
        meta.response_source === "observance_calendar" ? "Lịch ngày lễ đã kiểm tra" :
        meta.response_source === "runtime_identity" ? "Thông tin runtime đã xác minh" :
        meta.response_source === "calculator" ? "Kết quả tính đã kiểm tra" :
        meta.response_source === "replay" ? "Phản hồi đã xác nhận trước đó" :
        meta.response_source === "clarification" ? "Cần làm rõ" :
        meta.response_source === "mock" ? "Phản hồi thử nghiệm" : "Thao tác ứng dụng";
      metaEl.appendChild(tag);
    }
    if (meta.rag_used) {
      const tag = document.createElement("span");
      tag.className = "meta-tag";
      tag.textContent = "📚 Có nguồn";
      metaEl.appendChild(tag);
    }
    if (meta.memory_ids_used && meta.memory_ids_used.length > 0) {
      const tag = document.createElement("span");
      tag.className = "meta-tag";
      tag.textContent = `🧠 ${meta.memory_ids_used.length} trí nhớ`;
      metaEl.appendChild(tag);
    }
    if (meta.inspector) {
      const details = document.createElement("details");
      details.className = "inspector-card";
      const summary = document.createElement("summary");
      summary.textContent = "DUSN-X Inspector";
      const pre = document.createElement("pre");
      safeText(pre, meta.inspector);
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "action-btn";
      copy.textContent = "Copy filtered JSON";
      copy.onclick = () => navigator.clipboard?.writeText(JSON.stringify(meta.inspector, null, 2));
      details.append(summary, pre, copy);
      col.appendChild(details);
    }
    if (String(content ?? "").trim()) {
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "copy-btn";
      copyBtn.textContent = "Sao chép";
      copyBtn.onclick = () => copyMessageText(copyBtn, String(content ?? ""));
      metaEl.appendChild(copyBtn);
    }
  }

  col.appendChild(bubble);
  col.appendChild(metaEl);
  if (role === "assistant" && Array.isArray(meta.sources) && meta.sources.length > 0) {
    col.appendChild(buildSourcesCard(meta.sources));
  }
  if (role === "assistant" && Array.isArray(meta.memory_ids_used) && meta.memory_ids_used.length > 0) {
    col.appendChild(buildUsedMemoryCard(meta.memory_ids_used));
  }
  wrapper.appendChild(avatar);
  wrapper.appendChild(col);
  if (append) list.appendChild(wrapper);
  return wrapper;
}

function buildSourcesCard(sources) {
  const details = document.createElement("details");
  details.className = "sources-card";
  const summary = document.createElement("summary");
  summary.textContent = `Nguồn tài liệu (${sources.length})`;
  details.appendChild(summary);

  const list = document.createElement("ul");
  for (const source of sources) {
    const item = document.createElement("li");
    // SAFE: textContent — source metadata comes from indexed files, never rendered as HTML
    const label = document.createElement("span");
    label.className = "source-id";
    const sourceId = String(source.id ?? "");
    label.textContent = sourceId.startsWith("S") ? `[${sourceId}]` : `[S${sourceId}]`;
    const where = document.createElement("span");
    where.className = "source-where";
    const path = source.path || "?";
    const heading = source.heading ? ` · ${source.heading}` : "";
    const lines = source.start_line ? ` (dòng ${source.start_line}–${source.end_line})` : "";
    where.textContent = `${path}${heading}${lines}`;
    item.append(label, where);
    if (source.title) {
      const title = document.createElement("div");
      title.className = "source-title";
      title.textContent = source.title;
      item.appendChild(title);
    }
    list.appendChild(item);
  }
  details.appendChild(list);
  return details;
}


function scrollToBottom() {
  const list = el("messageList");
  list.scrollTop = list.scrollHeight;
}

function showStatus(msg) {
  el("statusText").textContent = msg;
  el("statusIndicator").hidden = false;
}

function hideStatus() {
  el("statusIndicator").hidden = true;
}

function showError(msg) {
  const banner = el("errorBanner");
  banner.textContent = msg;  // textContent — safe
  banner.hidden = false;
}

function hideError() {
  el("errorBanner").hidden = true;
}

// ── Memory ─────────────────────────────────────────────────────────────────────

async function loadMemories(search = null) {
  try {
    const includeInactive = el("showInactive")?.checked ?? false;
    const params = new URLSearchParams({ include_inactive: String(includeInactive), limit: "100" });
    if (search) params.set("search", search);
    allMemories = await apiFetch(`/v1/memories?${params}`);
    renderMemoryList(allMemories);
  } catch (err) {
    showError(`Không tải được trí nhớ: ${err.message}`);
  }
}

function filterMemories() {
  const q = (el("memorySearch")?.value || "").toLowerCase().trim();
  loadMemories(q || null);
}

function renderMemoryList(memories) {
  const list = el("memoryList");
  list.replaceChildren();
  if (!memories.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "🧠";
    const msg = document.createElement("p");
    msg.textContent = "Chưa có trí nhớ nào. Hãy chat để tôi ghi nhớ thông tin của bạn!";
    empty.appendChild(icon);
    empty.appendChild(msg);
    list.appendChild(empty);
    return;
  }
  for (const mem of memories) {
    list.appendChild(renderMemoryCard(mem));
  }
}

function renderMemoryCard(mem) {
  const card = document.createElement("article");
  card.className = "card" + (!mem.is_active ? " inactive" : "");
  card.setAttribute("data-memory-id", mem.memory_id);
  card.setAttribute("role", "listitem");

  const header = document.createElement("div");
  header.className = "card-header";

  const typeTag = document.createElement("span");
  typeTag.className = "card-type";
  typeTag.textContent = mem.info_type;

  header.appendChild(typeTag);

  if (!mem.is_active) {
    const inactiveBadge = document.createElement("span");
    inactiveBadge.className = "card-inactive-badge";
    inactiveBadge.textContent = mem.superseded_by ? "Đã thay thế" : "Đã xóa";
    header.appendChild(inactiveBadge);
  }

  const content = document.createElement("p");
  content.className = "card-content";
  content.textContent = mem.content;  // textContent — safe

  const metaEl = document.createElement("div");
  metaEl.className = "card-meta";

  const v = document.createElement("span");
  v.textContent = `v${mem.version}`;
  metaEl.appendChild(v);

  if (mem.project_id) {
    const proj = allProjects.find(p => p.project_id === mem.project_id);
    const projEl = document.createElement("span");
    projEl.textContent = `📁 ${proj?.name || mem.project_id.slice(0, 8)}`;
    metaEl.appendChild(projEl);
  }

  const dateEl = document.createElement("span");
  dateEl.textContent = `cập nhật ${formatDate(mem.updated_at)}`;
  metaEl.appendChild(dateEl);

  card.appendChild(header);
  card.appendChild(content);
  card.appendChild(metaEl);

  if (mem.is_active) {
    const actions = document.createElement("div");
    actions.className = "card-actions";

    const editBtn = document.createElement("button");
    editBtn.className = "action-btn";
    editBtn.textContent = "Sửa";
    editBtn.onclick = () => showEditMemoryModal(mem);

    const delBtn = document.createElement("button");
    delBtn.className = "action-btn danger";
    delBtn.textContent = "Xóa";
    delBtn.onclick = () => deleteMemory(mem.memory_id);

    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    card.appendChild(actions);
  }

  return card;
}

function showAddMemoryModal() {
  el("modalTitle").textContent = "Thêm trí nhớ mới";
  const body = el("modalBody");
  body.replaceChildren();

  const typeLabel = document.createElement("label");
  typeLabel.className = "field-label";
  typeLabel.textContent = "Loại thông tin";
  const typeInput = document.createElement("input");
  typeInput.id = "modalMemType";
  typeLabel.htmlFor = typeInput.id;
  typeInput.className = "field-input";
  typeInput.placeholder = "preference, goal, decision, project_fact, …";
  typeInput.value = "decision";

  const contentLabel = document.createElement("label");
  contentLabel.className = "field-label";
  contentLabel.textContent = "Nội dung";
  const contentInput = document.createElement("textarea");
  contentInput.id = "modalMemContent";
  contentLabel.htmlFor = contentInput.id;
  contentInput.className = "field-input";
  contentInput.rows = 4;
  contentInput.placeholder = "Mô tả thông tin muốn ghi nhớ…";

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn-primary";
  saveBtn.textContent = "Lưu trí nhớ";
  saveBtn.onclick = async () => {
    if (saveBtn.disabled) return;
    const type = typeInput.value.trim() || "general";
    const content = contentInput.value.trim();
    if (!content) return;
    saveBtn.disabled = true;
    try {
      await apiFetch("/v1/memories", {
        method: "POST",
        body: JSON.stringify({ info_type: type, content }),
      });
      closeModal();
      await loadMemories();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    } finally {
      saveBtn.disabled = false;
    }
  };

  body.appendChild(typeLabel);
  body.appendChild(typeInput);
  body.appendChild(contentLabel);
  body.appendChild(contentInput);
  body.appendChild(saveBtn);

  el("modalOverlay").hidden = false;
  typeInput.focus();
}

function showEditMemoryModal(mem) {
  el("modalTitle").textContent = "Sửa trí nhớ";
  const body = el("modalBody");
  body.replaceChildren();

  const note = document.createElement("p");
  note.style.fontSize = "12px";
  note.style.color = "var(--text-muted)";
  note.textContent = "Sửa sẽ tạo phiên bản mới và đánh dấu phiên bản cũ là không còn hiệu lực.";

  const typeLabel = document.createElement("label");
  typeLabel.className = "field-label";
  typeLabel.textContent = "Loại thông tin";
  const typeInput = document.createElement("input");
  typeInput.id = "editMemType";
  typeLabel.htmlFor = typeInput.id;
  typeInput.className = "field-input";
  typeInput.value = mem.info_type;

  const contentLabel = document.createElement("label");
  contentLabel.className = "field-label";
  contentLabel.textContent = "Nội dung mới";
  const contentInput = document.createElement("textarea");
  contentInput.id = "editMemContent";
  contentLabel.htmlFor = contentInput.id;
  contentInput.className = "field-input";
  contentInput.rows = 4;
  contentInput.value = mem.content;

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn-primary";
  saveBtn.textContent = "Lưu phiên bản mới";
  saveBtn.onclick = async () => {
    if (saveBtn.disabled || !contentInput.value.trim()) return;
    saveBtn.disabled = true;
    try {
      await apiFetch(`/v1/memories/${mem.memory_id}`, {
        method: "PUT",
        body: JSON.stringify({
          content: contentInput.value.trim(),
          info_type: typeInput.value.trim(),
        }),
      });
      closeModal();
      await loadMemories();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    } finally {
      saveBtn.disabled = false;
    }
  };

  body.appendChild(note);
  body.appendChild(typeLabel);
  body.appendChild(typeInput);
  body.appendChild(contentLabel);
  body.appendChild(contentInput);
  body.appendChild(saveBtn);

  el("modalOverlay").hidden = false;
}

async function deleteMemory(memoryId) {
  if (!confirm("Xóa trí nhớ này? Hành động có thể được ghi lại trong lịch sử sự kiện.")) return;
  try {
    await apiFetch(`/v1/memories/${memoryId}`, { method: "DELETE" });
    await loadMemories();
  } catch (err) {
    alert(`Lỗi xóa: ${err.message}`);
  }
}

// ── Projects ───────────────────────────────────────────────────────────────────

async function loadProjects() {
  try {
    allProjects = await apiFetch("/v1/projects");
    updateProjectSelect();
  } catch (err) {
    console.error("Load projects failed:", err);
  }
}

function updateProjectSelect() {
  const select = el("projectSelect");
  const current = select.value;
  select.replaceChildren();
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "Không có dự án";
  select.appendChild(none);
  for (const proj of allProjects) {
    const opt = document.createElement("option");
    opt.value = proj.project_id;
    opt.textContent = proj.name;  // textContent — safe
    select.appendChild(opt);
  }
  select.value = current || "";
}

function renderProjectsView() {
  const list = el("projectList");
  el("projectDetail").hidden = true;
  list.style.display = "";
  list.replaceChildren();

  if (!allProjects.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "📁";
    const msg = document.createElement("p");
    msg.textContent = "Chưa có dự án nào. Tạo dự án để tổ chức quyết định và trí nhớ theo chủ đề.";
    empty.appendChild(icon);
    empty.appendChild(msg);
    list.appendChild(empty);
    return;
  }

  for (const proj of allProjects) {
    const card = document.createElement("article");
    card.className = "card";
    card.setAttribute("role", "listitem");

    const header = document.createElement("div");
    header.className = "card-header";
    const title = document.createElement("span");
    title.className = "card-title";
    title.textContent = proj.name;

    header.appendChild(title);
    card.appendChild(header);

    if (proj.description) {
      const desc = document.createElement("p");
      desc.className = "card-content";
      desc.textContent = proj.description;
      card.appendChild(desc);
    }

    const metaEl = document.createElement("div");
    metaEl.className = "card-meta";
    const dateEl = document.createElement("span");
    dateEl.textContent = `Tạo ${formatDate(proj.created_at)}`;
    metaEl.appendChild(dateEl);
    card.appendChild(metaEl);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const viewBtn = document.createElement("button");
    viewBtn.className = "action-btn";
    viewBtn.textContent = "Xem quyết định";
    viewBtn.onclick = () => openProjectDetail(proj);
    actions.appendChild(viewBtn);
    card.appendChild(actions);

    list.appendChild(card);
  }
}

async function openProjectDetail(proj) {
  el("projectList").style.display = "none";
  el("projectDetail").hidden = false;
  el("projectDetailName").textContent = proj.name;
  el("projectDetailDesc").textContent = proj.description || "";

  try {
    const active = await apiFetch(`/v1/projects/${proj.project_id}/decisions`);
    const all = await apiFetch(`/v1/projects/${proj.project_id}/decisions?include_inactive=true`);
    const inactive = all.filter(m => !m.is_active);

    renderDecisionList(el("projectDecisions"), active, "Chưa có quyết định hiệu lực nào.");
    renderDecisionList(el("projectHistory"), inactive, "Không có quyết định đã thay thế.");
  } catch (err) {
    console.error("Load project decisions failed:", err);
  }
}

function renderDecisionList(container, decisions, emptyMsg) {
  container.replaceChildren();
  if (!decisions.length) {
    const empty = document.createElement("p");
    empty.style.cssText = "padding:12px 0; color:var(--text-muted); font-size:13px;";
    empty.textContent = emptyMsg;
    container.appendChild(empty);
    return;
  }
  for (const mem of decisions) {
    container.appendChild(renderMemoryCard(mem));
  }
}

function closeProjectDetail() {
  el("projectDetail").hidden = true;
  el("projectList").style.display = "";
}

function showAddProjectModal() {
  el("modalTitle").textContent = "Tạo dự án mới";
  const body = el("modalBody");
  body.replaceChildren();

  const nameLabel = document.createElement("label");
  nameLabel.className = "field-label";
  nameLabel.textContent = "Tên dự án";
  const nameInput = document.createElement("input");
  nameInput.id = "projName";
  nameInput.className = "field-input";
  nameInput.placeholder = "Chatbot cá nhân hóa, DUSN-X, …";

  const descLabel = document.createElement("label");
  descLabel.className = "field-label";
  descLabel.textContent = "Mô tả (tùy chọn)";
  const descInput = document.createElement("textarea");
  descInput.id = "projDesc";
  descInput.className = "field-input";
  descInput.rows = 3;
  descInput.placeholder = "Mô tả ngắn về dự án…";

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn-primary";
  saveBtn.textContent = "Tạo dự án";
  saveBtn.onclick = async () => {
    const name = nameInput.value.trim();
    if (!name) return;
    try {
      await apiFetch("/v1/projects", {
        method: "POST",
        body: JSON.stringify({ name, description: descInput.value.trim() }),
      });
      closeModal();
      await loadProjects();
      renderProjectsView();
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    }
  };

  body.appendChild(nameLabel);
  body.appendChild(nameInput);
  body.appendChild(descLabel);
  body.appendChild(descInput);
  body.appendChild(saveBtn);

  el("modalOverlay").hidden = false;
  nameInput.focus();
}

// ── Modal ──────────────────────────────────────────────────────────────────────

function closeModal() {
  el("modalOverlay").hidden = true;
}

// ── Timeline (Authenticated User Events) ───────────────────────────────────────

async function loadTimeline() {
  const statusEl = el("timelineStatus");
  statusEl.textContent = "Đang tải timeline tài khoản…";
  const list = el("timelineList");
  list.replaceChildren();

  const filterEl = el("tlPlatformFilter");
  const platform = filterEl ? filterEl.value.trim() : "";
  let url = "/v1/me/events?limit=50";
  if (platform) {
    url += `&platform=${encodeURIComponent(platform)}`;
  }

  try {
    const data = await apiFetch(url);
    const events = data.events || [];
    for (const item of events) {
      list.appendChild(renderTimelineItem(item));
    }
    const count = list.childElementCount;
    statusEl.textContent = count === 0
      ? "Chưa có sự kiện nào cho tài khoản này."
      : `Hiển thị ${count} sự kiện của tài khoản, mới nhất trước.`;
  } catch (err) {
    statusEl.textContent = `Không tải được timeline: ${err.message}`;
  }
}

function renderTimelineItem(item) {
  const card = document.createElement("article");
  card.className = "timeline-item";

  const header = document.createElement("div");
  header.className = "timeline-header";

  const badge = document.createElement("span");
  badge.className = `platform-badge platform-${item.platform || "unknown"}`;
  badge.textContent = item.platform || "?";

  const time = document.createElement("time");
  time.textContent = formatDate(item.created_at || item.event_time_utc);

  header.appendChild(badge);
  header.appendChild(time);

  const contentEl = document.createElement("p");
  contentEl.className = "timeline-content";
  contentEl.textContent = item.content || "(không có nội dung)";  // textContent — safe

  const details = document.createElement("div");
  details.className = "timeline-details";

  const addField = (label, value) => {
    if (value === null || value === undefined || value === "") return;
    const f = document.createElement("span");
    f.className = "timeline-field";
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    const val = document.createElement("span");
    val.textContent = String(value);
    f.appendChild(strong);
    f.appendChild(val);
    details.appendChild(f);
  };

  if (item.event_type) addField("event", item.event_type);
  addField("intent", item.intent);
  addField("agent", item.selected_agent);
  addField("next action", item.next_action);
  addField("state v", item.state_version);
  if (item.confidence) addField("conf", typeof item.confidence === "number" ? item.confidence.toFixed(2) : item.confidence);
  if (item.runtime_mode) addField("runtime", item.runtime_mode);
  if (item.model_version) addField("model", item.model_version);
  if (item.state_reset !== null && item.state_reset !== undefined) {
    addField("reset", item.state_reset ? `có — ${item.reset_reason || ""}` : "không");
  }

  card.appendChild(header);
  card.appendChild(contentEl);
  card.appendChild(details);
  return card;
}


// ── Auto-login if token exists ─────────────────────────────────────────────────

(async function init() {
  if (authToken) {
    try {
      await enterApp();
    } catch (err) {
      if (err.name === "SessionChangedError") return;
      authToken = null;
      sessionStorage.removeItem("dusnx_token");
      showScreen("authScreen");
    }
  } else {
    showScreen("authScreen");
  }
})();

// ── Exports for testing ────────────────────────────────────────────────────────
if (typeof module !== "undefined") {
  module.exports = {
    renderTimelineItem,
    renderMemoryCard,
    appendMessageBubble,
    renderMarkdown,
    copyMessageText,
    safeText,
    formatDate,
    checkProviderHealth,
    apiFetch,
    sendMessage,
  };
}
