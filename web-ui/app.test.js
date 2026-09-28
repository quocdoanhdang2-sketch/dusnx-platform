/**
 * DUSN-X Web UI Tests
 * Tests that user-facing content is rendered safely (never via innerHTML)
 * and that the app module exports work correctly.
 *
 * Run with: node --test web-ui/app.test.js
 */
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");

// ── Minimal DOM mock for Node.js ───────────────────────────────────────────────

function makeEl(tag) {
  return {
    tag,
    _text: "",
    _children: [],
    _attrs: {},
    _classes: new Set(),
    get textContent() { return this._text; },
    set textContent(v) { this._text = v; this._html = undefined; },
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      // If innerHTML is ever called with untrusted data this test will catch it
      this._html = v;
      this._html_set = true;
    },
    appendChild(child) { this._children.push(child); return child; },
    replaceChildren() { this._children = []; },
    className: "",
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    classList: {
      _set: new Set(),
      add(...c) { c.forEach(x => this._set.add(x)); },
      remove(...c) { c.forEach(x => this._set.delete(x)); },
      toggle(c, force) {
        if (force !== undefined) { force ? this._set.add(c) : this._set.delete(c); }
        else { this._set.has(c) ? this._set.delete(c) : this._set.add(c); }
        return this._set.has(c);
      },
      contains(c) { return this._set.has(c); },
    },
    hidden: false,
    style: {},
    onclick: null,
  };
}

const elements = {};
global.document = {
  getElementById: (id) => { if (!elements[id]) elements[id] = makeEl("div"); return elements[id]; },
  createElement: (tag) => makeEl(tag),
  querySelectorAll: () => [],
};
global.window = { DUSNX_AI_API: "http://localhost:8000", DUSNX_GATEWAY: "http://localhost:8080" };
global.sessionStorage = {
  _data: {},
  getItem(k) { return this._data[k] ?? null; },
  setItem(k, v) { this._data[k] = v; },
  removeItem(k) { delete this._data[k]; },
};
global.fetch = async () => ({ ok: false, status: 401, json: async () => ({}) });

const app = require("./app.js");

describe("Provider health through Gateway", () => {
  it("reads AI health rather than Gateway liveness", async () => {
    const previousFetch = global.fetch;
    let requested;
    global.fetch = async (url) => {
      requested = url;
      return { ok: true, json: async () => ({ model_loaded: true, runtime_mode: "trained_dusnx",
        model_version: "checkpoint-test", provider_ok: true,
        provider: { provider: "ollama", configured_model: "test-model" } }) };
    };
    try {
      await app.checkProviderHealth();
      assert.ok(requested.endsWith("/v1/health"));
      assert.match(elements.modelStatus.textContent, /Trained/);
      assert.match(elements.providerStatus.textContent, /sẵn sàng/);
    } finally {
      global.fetch = previousFetch;
    }
  });
});

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("renderTimelineItem — XSS safety", () => {
  it("renders content via textContent, not innerHTML", () => {
    const xssPayload = "<img src=x onerror=alert(1)>";
    const item = {
      platform: "web",
      event_time_utc: "2024-01-01T00:00:00Z",
      content: xssPayload,
      intent: "chat",
      selected_agent: "conversation",
      next_action: "reply",
      runtime_mode: "bootstrap_rules",
      model_version: "v0.2",
      state_version: 1,
      state_reset: false,
      reset_reason: null,
    };
    const card = app.renderTimelineItem(item);
    // Content should be in textContent, not innerHTML
    const contentEl = card._children.find(c => c._text === xssPayload);
    assert.ok(contentEl, "Content should appear as textContent");
    // innerHTML should NOT be set on any child with XSS content
    function checkNoInnerHTML(el) {
      if (el._html && el._html.includes("<img")) {
        throw new Error(`innerHTML was used with XSS payload in <${el.tag}>`);
      }
      (el._children || []).forEach(checkNoInnerHTML);
    }
    checkNoInnerHTML(card);
  });

  it("handles null/undefined fields gracefully", () => {
    const item = {
      platform: null,
      event_time_utc: null,
      content: null,
      intent: undefined,
      selected_agent: undefined,
      next_action: undefined,
    };
    // Should not throw
    assert.doesNotThrow(() => app.renderTimelineItem(item));
  });
});

describe("renderMemoryCard — XSS safety", () => {
  it("renders content via textContent, not innerHTML", () => {
    const xss = '<script>alert("xss")</script>';
    const mem = {
      memory_id: "abc123",
      info_type: "decision",
      content: xss,
      version: 2,
      is_active: true,
      superseded_by: null,
      project_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-02T00:00:00Z",
    };
    const card = app.renderMemoryCard(mem);
    function checkNoInnerHTML(el) {
      if (el._html && el._html.includes("<script")) {
        throw new Error(`innerHTML used with XSS in <${el.tag}>`);
      }
      (el._children || []).forEach(checkNoInnerHTML);
    }
    checkNoInnerHTML(card);
  });

  it("inactive memory shows badge", () => {
    const mem = {
      memory_id: "xyz",
      info_type: "goal",
      content: "Old goal",
      version: 1,
      is_active: false,
      superseded_by: "new_id",
      project_id: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    };
    const card = app.renderMemoryCard(mem);
    assert.ok(card.className.includes("inactive"), "Inactive card should have inactive class");
  });
});

describe("appendMessageBubble — XSS safety", () => {
  it("renders user content via textContent", () => {
    const xss = '<img src=x onerror=alert(2)>';
    // Pre-create list el
    elements["messageList"] = makeEl("div");
    elements["messageList"].appendChild = function(child) {
      this._children.push(child);
      return child;
    };
    elements["welcomeState"] = makeEl("div");
    elements["welcomeState"].style = {};

    app.appendMessageBubble("user", xss, { created_at: new Date().toISOString() });
    function checkNoInnerHTML(el) {
      if (el._html && (el._html.includes("<img") || el._html.includes("onerror"))) {
        throw new Error("innerHTML used with XSS payload in user message");
      }
      (el._children || []).forEach(checkNoInnerHTML);
    }
    elements["messageList"]._children.forEach(checkNoInnerHTML);
  });
});

describe("safeText", () => {
  it("always uses textContent", () => {
    const el = makeEl("div");
    app.safeText(el, "<b>bold</b>");
    assert.equal(el.textContent, "<b>bold</b>");
    assert.ok(!el._html_set, "innerHTML should not have been set");
  });

  it("serializes non-strings as JSON", () => {
    const el = makeEl("div");
    app.safeText(el, { a: 1 });
    assert.ok(el.textContent.includes('"a"'));
  });
});

describe("formatDate", () => {
  it("handles valid ISO string", () => {
    const result = app.formatDate("2024-01-15T10:30:00Z");
    assert.ok(typeof result === "string" && result.length > 0);
  });

  it("handles null gracefully", () => {
    assert.equal(app.formatDate(null), "—");
  });
});
