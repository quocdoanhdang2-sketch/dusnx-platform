const test = require("node:test"); const assert = require("node:assert/strict");
global.fetch = async () => ({ ok:true, headers:{get:()=>"application/json"}, json:async()=>({}) });
const app = require("./word-taskpane.js");
test("sanitizes instruction/status text and keeps paragraph breaks in document text", () => {
  assert.equal(app.safe("a\u0000b"), "a b");
  assert.equal(app.safe("x".repeat(5000)).length, 4000);
  assert.equal(app.cleanText("line 1\r\nline 2\u0001"), "line 1\r\nline 2 ");
});
test("logout clears in-memory token and proposal", () => { app.state.token = "secret"; app.state.proposal = {text:"x"}; app.logout(); assert.equal(app.state.token, null); assert.equal(app.state.proposal, null); });

const ORIGINAL = "Báo cáo kết thúc giai đoạn DUSN-X LLM v3";
function officeFixture() {
  const fixture = { text: ORIGINAL, start: 12, end: 12 + ORIGINAL.length, writes: 0, request: null };
  const elements = {};
  global.document = { getElementById(id) { return elements[id] ||= { value: id === "prompt" ? "Viết lại đoạn đang chọn" : "", textContent: "", disabled: false }; } };
  global.Word = { InsertLocation: { replace: "Replace" }, run: async fn => {
    const selection = {
      load() {},
      get text() { return fixture.text; },
      get start() { return fixture.start; },
      get end() { return fixture.end; },
      insertText(value, location) { assert.equal(location, "Replace"); fixture.text = value; fixture.end = fixture.start + value.length; fixture.writes += 1; },
      insertParagraph(value, location) { assert.equal(location, "After"); fixture.inserted = value; fixture.writes += 1; },
    };
    return fn({ sync: async () => {}, document: { getSelection: () => selection } });
  } };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false; app.state.applyMode = "replace";
  fixture.result = { reply: "Báo cáo DUSN-X LLM v3 — bản rút gọn", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm", intent: "chat", routing_source: "model" };
  global.fetch = async (url, options) => { fixture.request = { url, body: JSON.parse(options.body) }; return { ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result }; };
  return fixture;
}

test("proposal is reviewed before one explicit Apply to the selected range", async () => {
  const fixture = officeFixture();
  await app.ask();
  assert.equal(fixture.writes, 0);
  assert.equal(app.state.proposal.target.start, 12);
  assert.match(fixture.request.body.message, /\[Word selected text/);
  assert.ok(fixture.request.body.message.includes(ORIGINAL));
  await app.applyProposal();
  assert.equal(fixture.writes, 1);
  assert.equal(fixture.text, "Báo cáo DUSN-X LLM v3 — bản rút gọn");
  await assert.rejects(app.applyProposal(), /No proposal/);
  assert.equal(fixture.writes, 1);
});

test("Apply preserves a trailing paragraph break from the selection", async () => {
  const fixture = officeFixture(); fixture.text = "Đoạn gốc.\r"; fixture.end = 12 + fixture.text.length; fixture.result.reply = "Đoạn mới.";
  await app.ask(); await app.applyProposal();
  assert.equal(fixture.writes, 1); assert.equal(fixture.text, "Đoạn mới.\r");
});

test("insert-after mode adds a new paragraph and keeps the selection unchanged", async () => {
  const fixture = officeFixture();
  app.state.applyMode = "insertAfter";
  await app.ask();
  assert.equal(fixture.writes, 0);
  assert.equal(app.state.proposal.applyMode, "insertAfter");
  await app.applyProposal();
  assert.equal(fixture.writes, 1);
  assert.equal(fixture.inserted, "Báo cáo DUSN-X LLM v3 — bản rút gọn");
  assert.equal(fixture.text, ORIGINAL);
  assert.equal(app.state.proposal, null);
});

test("insert-after apply still refuses a changed selection", async () => {
  const fixture = officeFixture();
  app.state.applyMode = "insertAfter";
  await app.ask();
  fixture.text = "Changed after review";
  await assert.rejects(app.applyProposal(), /Selection or text changed/);
  assert.equal(fixture.writes, 0);
  assert.equal(fixture.inserted, undefined);
});

for (const field of ["text", "start", "end"]) {
  test(`Apply refuses a changed selection ${field}`, async () => {
    const fixture = officeFixture(); await app.ask(); fixture[field] = field === "text" ? "Changed after review" : 999;
    await assert.rejects(app.applyProposal(), /Selection or text changed/);
    assert.equal(fixture.writes, 0); assert.equal(app.state.proposal, null);
  });
}

test("Apply refuses a changed session and a logged-out task pane", async () => {
  const fixture = officeFixture(); await app.ask(); app.state.sessionId = "session-b";
  await assert.rejects(app.applyProposal(), /Selection or text changed/); assert.equal(fixture.writes, 0);
  const fixture2 = officeFixture(); await app.ask(); app.logout();
  await assert.rejects(app.applyProposal(), /No proposal/); assert.equal(fixture2.writes, 0);
});

test("empty or oversized selections never reach the provider", async () => {
  const empty = officeFixture(); empty.text = "   "; empty.end = empty.start + 3;
  await assert.rejects(app.ask(), /Select text/); assert.equal(empty.request, null);
  const oversized = officeFixture(); oversized.text = "x".repeat(4001); oversized.end = oversized.start + 4001;
  await assert.rejects(app.ask(), /exceeds 4000/); assert.equal(oversized.request, null);
});

test("blank, unchanged, metadata, control and missing provenance never become proposals", async () => {
  for (const override of [{ reply: " " }, { reply: ORIGINAL }, { reply: '{"intent":"chat"}' }, { reply: "x".repeat(4001) },
    { reply: "bad\u0001text" }, { provider_called: false }, { response_source: "application_rule" }, { model_used: null }]) {
    const fixture = officeFixture(); Object.assign(fixture.result, override);
    await assert.rejects(app.ask()); assert.equal(fixture.writes, 0); assert.equal(app.state.proposal, null);
  }
});

test("logout discards a provider response already in flight", async () => {
  const fixture = officeFixture(); let complete;
  global.fetch = async url => {
    if (url.endsWith("/v1/chat")) return new Promise(resolve => { complete = resolve; });
    return { ok: true, headers: { get: () => "application/json" }, json: async () => ({}) };
  };
  const pending = app.ask();
  while (!complete) await new Promise(resolve => setImmediate(resolve));
  app.logout(); complete({ ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result });
  await pending; assert.equal(app.state.proposal, null); assert.equal(fixture.writes, 0);
});

test("logout during login does not restore an authenticated state", async () => {
  officeFixture(); app.state.token = null; let complete;
  global.fetch = async () => new Promise(resolve => { complete = resolve; });
  const pending = app.login();
  app.logout();
  complete({ ok: true, headers: { get: () => "application/json" }, json: async () => ({ token: "synthetic-late-token" }) });
  await pending; assert.equal(app.state.token, null); assert.equal(app.state.proposal, null);
});

test("requests are same-origin by default and honor DUSNX_GATEWAY", async () => {
  const fixture = officeFixture();
  await app.ask();
  assert.equal(fixture.request.url, "/v1/chat");
  globalThis.DUSNX_GATEWAY = "https://gateway.example/";
  try {
    const configured = officeFixture();
    await app.ask();
    assert.equal(configured.request.url, "https://gateway.example/v1/chat");
  } finally { delete globalThis.DUSNX_GATEWAY; }
});

test("logout aborts an in-flight provider request", async () => {
  const fixture = officeFixture(); let signal;
  global.fetch = (url, options) => {
    if (!/\/v1\/chat$/.test(url)) return Promise.resolve({ ok: true, headers: { get: () => "application/json" }, json: async () => ({}) });
    signal = options.signal;
    return new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
  };
  const pending = app.ask();
  while (!signal) await new Promise(resolve => setImmediate(resolve));
  app.logout();
  assert.equal(signal.aborted, true);
  await assert.rejects(pending, /aborted/);
  assert.equal(app.state.proposal, null); assert.equal(fixture.writes, 0);
});

test("cancelInFlight aborts the active request once and clears it", async () => {
  officeFixture(); let signal;
  global.fetch = (url, options) => {
    if (!/\/v1\/chat$/.test(url)) return Promise.resolve({ ok: true, headers: { get: () => "application/json" }, json: async () => ({}) });
    signal = options.signal;
    return new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }))));
  };
  const pending = app.ask();
  while (!signal) await new Promise(resolve => setImmediate(resolve));
  app.cancelInFlight();
  assert.equal(signal.aborted, true); assert.equal(app.state.controller, null);
  app.cancelInFlight();
  await assert.rejects(pending, /aborted/);
  assert.equal(app.state.proposal, null);
});
