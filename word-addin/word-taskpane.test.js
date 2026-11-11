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
  const fixture = { text: ORIGINAL, start: 12, end: 12 + ORIGINAL.length, writes: 0, request: null, requests: [],
    tracking: "Off", trackingSupported: false };
  const elements = {};
  global.document = { getElementById(id) { return elements[id] ||= { value: id === "prompt" ? "Viết lại đoạn đang chọn" : "", textContent: "", disabled: false }; } };
  elements.contentMode = { value: "text", disabled: false };
  global.Office = { context: { requirements: { isSetSupported: () => fixture.trackingSupported } } };
  global.Word = { InsertLocation: { replace: "Replace", after: "After" }, run: async fn => {
    const selection = {
      load() {},
      get text() { return fixture.text; },
      get start() { return fixture.start; },
      get end() { return fixture.end; },
      insertText(value, location) { assert.equal(location, "Replace"); fixture.text = value; fixture.end = fixture.start + value.length; fixture.writes += 1; },
      insertParagraph(value, location) { assert.equal(location, "After"); fixture.inserted = value; fixture.writes += 1; },
      insertHtml(html, location) { fixture.insertedHtml = { html, location }; fixture.writes += 1; },
    };
    const contextDocument = {
      getSelection: () => selection,
      load() {},
      get changeTrackingMode() { return fixture.tracking; },
    };
    return fn({ sync: async () => {}, document: contextDocument });
  } };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false; app.state.applyMode = "replace";
  fixture.result = { reply: "Báo cáo DUSN-X LLM v3 — bản rút gọn", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm", intent: "chat", routing_source: "model" };
  global.fetch = async (url, options) => { const body = JSON.parse(options.body || "{}"); fixture.requests.push({ url, body });
    if (String(url).endsWith("/v1/chat")) fixture.request = { url, body };
    return { ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result }; };
  fixture.elements = elements;
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

test("empty selection writes new content at the cursor after review", async () => {
  const fixture = officeFixture(); fixture.text = ""; fixture.start = 0; fixture.end = 0;
  fixture.result.reply = "Đoạn mở đầu mới.";
  await app.ask();
  assert.match(fixture.request.body.message, /\[Word cursor/);
  assert.equal(app.state.proposal.mode, "insert");
  assert.equal(fixture.writes, 0);
  await app.applyProposal();
  assert.equal(fixture.writes, 1);
  assert.equal(fixture.text, "Đoạn mở đầu mới.");
});

test("insert at cursor refuses a cursor that moved after review", async () => {
  const fixture = officeFixture(); fixture.text = ""; fixture.start = 0; fixture.end = 0;
  await app.ask(); fixture.start = 5; fixture.end = 5;
  await assert.rejects(app.applyProposal(), /Selection or text changed/);
  assert.equal(fixture.writes, 0); assert.equal(app.state.proposal, null);
});

test("oversized selections never reach the provider", async () => {
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

test("Apply is blocked while Track Changes is on and the draft is discarded", async () => {
  for (const mode of ["TrackAll", "TrackMineOnly"]) {
    const fixture = officeFixture(); await app.ask();
    fixture.trackingSupported = true; fixture.tracking = mode;
    await assert.rejects(app.applyProposal(), /Track Changes is on/);
    assert.equal(fixture.writes, 0);
    assert.equal(app.state.proposal, null);
  }
});

test("Apply proceeds when the tracking guard is supported and Track Changes is off", async () => {
  const fixture = officeFixture(); await app.ask();
  fixture.trackingSupported = true; fixture.tracking = "Off";
  await app.applyProposal();
  assert.equal(fixture.writes, 1);
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

const TABLE = "| Hạng mục | Trạng thái |\n| --- | --- |\n| Dữ liệu | Đã khóa |\n| Huấn luyện | LoRA |";

test("table mode inserts a native Word table only after review", async () => {
  const fixture = officeFixture();
  fixture.elements.contentMode.value = "table"; fixture.result.reply = TABLE;
  await app.ask();
  assert.equal(fixture.writes, 0);
  assert.equal(app.state.proposal.kind, "table");
  assert.match(fixture.request.body.message, /\[Word table\]/);
  assert.ok(fixture.request.body.message.includes(ORIGINAL));
  await app.applyProposal();
  assert.deepEqual(app.parseMarkdownTable(TABLE),
    [["Hạng mục", "Trạng thái"], ["Dữ liệu", "Đã khóa"], ["Huấn luyện", "LoRA"]]);
  assert.equal(fixture.insertedHtml.html, app.tableHtml([["Hạng mục", "Trạng thái"], ["Dữ liệu", "Đã khóa"], ["Huấn luyện", "LoRA"]]));
  assert.match(fixture.insertedHtml.html, /^<table[^>]*><tr><td>Hạng mục<\/td><td>Trạng thái<\/td><\/tr>/);
  assert.match(fixture.insertedHtml.html, /<td>Dữ liệu<\/td>/);
  assert.equal(fixture.insertedHtml.location, "Replace");
  assert.equal(fixture.text, ORIGINAL);
  assert.equal(fixture.elements.status.textContent, "Table inserted at the selection.");
});

test("table mode can insert after the selection", async () => {
  const fixture = officeFixture();
  fixture.elements.contentMode.value = "table"; fixture.result.reply = TABLE;
  app.state.applyMode = "insertAfter";
  await app.ask(); await app.applyProposal();
  assert.equal(fixture.insertedHtml.location, "After");
  assert.equal(fixture.text, ORIGINAL);
});

test("table Apply refuses a changed selection", async () => {
  const fixture = officeFixture();
  fixture.elements.contentMode.value = "table"; fixture.result.reply = TABLE;
  await app.ask(); fixture.text = "Changed after review";
  await assert.rejects(app.applyProposal(), /Selection or text changed/);
  assert.equal(fixture.insertedHtml, undefined); assert.equal(app.state.proposal, null);
});

test("markdown table parser rejects fences, metadata, ragged rows and oversized tables", () => {
  assert.deepEqual(app.parseMarkdownTable(TABLE),
    [["Hạng mục", "Trạng thái"], ["Dữ liệu", "Đã khóa"], ["Huấn luyện", "LoRA"]]);
  assert.deepEqual(app.parseMarkdownTable("| A |\n| --- |\n| 1 |"), [["A"], ["1"]]);
  for (const reply of ["", "```\n| a |\n| --- |\n| b |\n```", '{"rows":[]}', "| a | b |\n| --- | --- |\n| c |", "| a |\n- b"])
    assert.throws(() => app.parseMarkdownTable(reply));
  const tooMany = "| H |\n| --- |\n" + Array.from({ length: 21 }, (_, index) => `| r${index} |`).join("\n");
  assert.throws(() => app.parseMarkdownTable(tooMany), /At most 21/);
});

test("table HTML escapes cell text before Word parses it", () => {
  assert.equal(app.tableHtml([["<b>", "a&b"], ['"q"', "1"]]),
    '<table border="1" cellspacing="0" cellpadding="4"><tr><td>&lt;b&gt;</td><td>a&amp;b</td></tr><tr><td>&quot;q&quot;</td><td>1</td></tr></table>');
});

test("secrets in the selection or instruction never reach the provider", async () => {
  const selection = officeFixture();
  selection.text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEexample"; selection.end = selection.start + selection.text.length;
  await assert.rejects(app.ask(), /private key/);
  assert.equal(selection.request, null); assert.equal(app.state.proposal, null);

  const instruction = officeFixture();
  global.document.getElementById("prompt").value = "Dùng sk-abcdefghijklmnopqrstuvwx để gọi API";
  await assert.rejects(app.ask(), /API key/);
  assert.equal(instruction.request, null); assert.equal(app.state.proposal, null);
  assert.equal(app.findSensitive("task-management"), null);
  assert.equal(app.findSensitive("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"), "bearer token");
});

test("Apply records a content-free telemetry event", async () => {
  const fixture = officeFixture(); await app.ask(); await app.applyProposal();
  const events = fixture.requests.filter(request => String(request.url).endsWith("/v1/me/events"));
  assert.equal(events.length, 1);
  assert.equal(events[0].body.platform, "word");
  assert.equal(events[0].body.event_type, "apply");
  assert.match(events[0].body.content, /^Applied rewrite text \(\d+ characters\)$/);
  assert.ok(!events[0].body.content.includes("bản rút gọn"));
  assert.ok(!events[0].body.content.includes(ORIGINAL));
});
