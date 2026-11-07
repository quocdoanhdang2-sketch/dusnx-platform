const test = require("node:test"); const assert = require("node:assert/strict");
global.fetch = async () => ({ ok:true, headers:{get:()=>"application/json"}, json:async()=>({}) });
const app = require("./taskpane.js");
test("sanitizes and bounds Office context", () => { assert.equal(app.safe("a\u0000b"), "a b"); assert.equal(app.safe("x".repeat(5000)).length, 4000); });
test("logout clears in-memory token", () => { app.state.token = "secret"; app.state.proposal = {text:"x"}; app.logout(); assert.equal(app.state.token, null); assert.equal(app.state.proposal, null); });

function officeFixture() {
  const fixture = { slideId: "slide-a", shapeId: "shape-a", text: "Original heading", writes: 0 };
  const elements = {};
  global.document = { getElementById(id) { return elements[id] ||= { value: "Rewrite the heading", textContent: "", disabled: false }; } };
  global.PowerPoint = { run: async fn => {
    const range = { load() {}, get text() { return fixture.text; }, set text(value) { fixture.text = value; fixture.writes++; } };
    return fn({ sync: async () => {}, presentation: {
      getSelectedSlides: () => ({ load() {}, items: [{ id: fixture.slideId }] }),
      getSelectedShapes: () => ({ load() {}, items: [{ id: fixture.shapeId, textFrame: { hasText: true, load() {}, textRange: range } }] }),
    } });
  } };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false;
  fixture.result = { reply: "Rewritten heading", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm" };
  global.fetch = async () => ({ ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result });
  return fixture;
}

test("proposal is reviewed before one explicit Apply to the selected shape", async () => {
  const fixture = officeFixture();
  await app.ask(); assert.equal(fixture.writes, 0); assert.equal(app.state.proposal.target.shapeId, "shape-a");
  await app.applyProposal(); assert.equal(fixture.writes, 1); assert.equal(fixture.text, "Rewritten heading");
  await assert.rejects(app.applyProposal(), /No proposal/); assert.equal(fixture.writes, 1);
});

for (const field of ["slideId", "shapeId", "text"]) {
  test(`Apply refuses a changed ${field}`, async () => {
    const fixture = officeFixture(); await app.ask(); fixture[field] = "Changed after review";
    await assert.rejects(app.applyProposal(), /Selection or text changed/);
    assert.equal(fixture.writes, 0); assert.equal(app.state.proposal, null);
  });
}

test("blank, unchanged, metadata and missing provenance never become proposals", async () => {
  for (const override of [{ reply: " " }, { reply: "Original heading" }, { reply: '{"intent":"chat"}' },
    { provider_called: false }, { response_source: "application_rule" }, { model_used: null }]) {
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

test("api calls stay same-origin by default and honor DUSNX_GATEWAY", async () => {
  const urls = [];
  global.fetch = async url => { urls.push(url); return { ok: true, headers: { get: () => "application/json" }, json: async () => ({}) }; };
  app.state.token = "synthetic-token";
  await app.api("/v1/ping");
  globalThis.DUSNX_GATEWAY = "https://gateway.example/";
  try { await app.api("/v1/ping"); } finally { delete globalThis.DUSNX_GATEWAY; }
  assert.deepEqual(urls, ["/v1/ping", "https://gateway.example/v1/ping"]);
});

test("outline parser accepts strict headings and safe plain bullets", () => {
  assert.deepEqual(app.parseOutline("# Mở đầu\n- Ý một\n- Ý hai\n\n## Kết luận\n- Ý ba"), [
    { title: "Mở đầu", bullets: ["Ý một", "Ý hai"] },
    { title: "Kết luận", bullets: ["Ý ba"] },
  ]);
  assert.deepEqual(app.parseOutline("# Mở đầu\n- Ý một\n---\nÝ hai"), [{ title: "Mở đầu", bullets: ["Ý một", "Ý hai"] }]);
  for (const reply of ["", "Mở đầu\n- Ý một", "- bullet first\n# Title", "#Title\n- bullet",
    "# T\n```\n- x\n```", '{"slides":[]}', "#\n- bullet"]) {
    assert.throws(() => app.parseOutline(reply));
  }
});

test("outline parser tolerates a short preamble and model slide labels", () => {
  assert.deepEqual(app.parseOutline("Để tạo ra các slide theo yêu cầu của bạn:\n\n# Slide 1 - Dữ liệu\n- Đã khóa\n# Slide 2: Huấn luyện\n- LoRA\n## Slide 3 - Đánh giá\n- Có regression"), [
    { title: "Dữ liệu", bullets: ["Đã khóa"] },
    { title: "Huấn luyện", bullets: ["LoRA"] },
    { title: "Đánh giá", bullets: ["Có regression"] },
  ]);
  assert.deepEqual(app.parseOutline("Slide 1 - Mở đầu\n- Ý một"), [{ title: "Mở đầu", bullets: ["Ý một"] }]);
  assert.deepEqual(app.parseOutline("# Mở đầu\n- Ý một\nSlide 2 - Kết luận\n- Ý hai"), [
    { title: "Mở đầu", bullets: ["Ý một"] },
    { title: "Kết luận", bullets: ["Ý hai"] },
  ]);
  assert.deepEqual(app.parseOutline("# Mở đầu\n- Ý một\nSlide 2\n- Ý hai"), [{ title: "Mở đầu", bullets: ["Ý một", "Ý hai"] }]);
  assert.deepEqual(app.parseOutline("# Slide 1 - Title: Dữ liệu\n- Bullet text: Đã khóa\n# Title: Vận hành\nBullet text: Same-origin"), [
    { title: "Dữ liệu", bullets: ["Đã khóa"] },
    { title: "Vận hành", bullets: ["Same-origin"] },
  ]);
  assert.throws(() => app.parseOutline("a\nb\nc\nd\n# Muộn"), /Unexpected outline line/);
});

test("plan validation enforces slide, bullet and length limits", () => {
  assert.deepEqual(app.validatePlan([{ title: " T ", bullets: [" b "] }], 1), [{ title: "T", bullets: ["b"] }]);
  for (const [plan, count] of [[[], 0], [[{ title: "T", bullets: ["b"] }], 2],
    [[{ title: "", bullets: ["b"] }], 1], [[{ title: "T", bullets: [] }], 1],
    [[{ title: "T", bullets: Array.from({ length: 6 }, (_, i) => `b${i}`) }], 1],
    [[{ title: "T", bullets: ["b".repeat(181)] }], 1], [[{ title: "T".repeat(121), bullets: ["b"] }], 1],
    [Array.from({ length: 7 }, (_, i) => ({ title: `T${i}`, bullets: ["b"] })), 7]]) {
    assert.throws(() => app.validatePlan(plan, count));
  }
});

function planFixture({ missingTitle = false } = {}) {
  const elements = {}; let created = 0;
  global.document = { getElementById(id) { return elements[id] ||= { value: "", textContent: "", disabled: false, style: {} }; } };
  const slideFactory = fresh => {
    const shapes = [
      { name: "DUSN-X Accent" },
      ...(fresh && missingTitle ? [] : [{ name: "DUSN-X Title", textFrame: { textRange: { text: "" } } }]),
      { name: "DUSN-X Body", textFrame: { textRange: { text: "" } } },
      { name: "DUSN-X Footer", textFrame: { textRange: { text: "DUSN-X" } } },
    ];
    const slide = { id: fresh ? `new-${++created}` : "existing", shapes: { load() {}, get items() { return shapes; } },
      delete() { const index = slides.indexOf(slide); if (index >= 0) slides.splice(index, 1); } };
    return slide;
  };
  const slides = [slideFactory(false)];
  global.PowerPoint = { run: async fn => fn({ sync: async () => {}, presentation: {
    slides: { load() {}, get items() { return slides; } },
    insertSlidesFromBase64(_base64, options = {}) {
      const fresh = slideFactory(true);
      if (options.targetSlideId) {
        const id = String(options.targetSlideId).replace(/#.*$/, "");
        const index = slides.findIndex(slide => slide.id === id);
        slides.splice(index + 1, 0, fresh);
      } else slides.unshift(fresh);
    },
  } }) };
  elements.mode = { value: "generate", disabled: false, style: {} };
  elements.count = { value: "2", disabled: false, style: {} };
  elements.prompt = { value: "Tạo 2 slide tóm tắt kế hoạch", disabled: false, style: {} };
  const result = { reply: "# Mở đầu\n- Ý một\n- Ý hai\n# Kết luận\n- Ý ba", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm" };
  global.fetch = async url => String(url) === "deck-template.pptx"
    ? { ok: true, arrayBuffer: async () => new Uint8Array(2048).buffer }
    : { ok: true, headers: { get: () => "application/json" }, json: async () => result };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false;
  return { slides, elements, result };
}

test("generate mode previews an outline and appends template slides only on Apply", async () => {
  const fixture = planFixture();
  await app.ask();
  assert.equal(fixture.slides.length, 1);
  assert.equal(app.state.proposal.kind, "plan");
  assert.match(fixture.elements.proposal.textContent, /1\. Mở đầu/);
  await app.applyProposal();
  assert.equal(fixture.slides.length, 3);
  const added = fixture.slides.slice(1);
  const text = slide => Object.fromEntries(slide.shapes.items.filter(s => s.name !== "DUSN-X Accent").map(s => [s.name, s.textFrame.textRange.text]));
  assert.deepEqual(text(added[0]), { "DUSN-X Title": "Mở đầu", "DUSN-X Body": "• Ý một\r• Ý hai", "DUSN-X Footer": "DUSN-X · 2" });
  assert.deepEqual(text(added[1]), { "DUSN-X Title": "Kết luận", "DUSN-X Body": "• Ý ba", "DUSN-X Footer": "DUSN-X · 3" });
  assert.equal(app.state.proposal, null);
});

test("generate Apply refuses a changed session before inserting slides", async () => {
  const fixture = planFixture();
  await app.ask(); app.state.sessionId = "session-b";
  await assert.rejects(app.applyProposal(), /Session changed/);
  assert.equal(fixture.slides.length, 1); assert.equal(app.state.proposal, null);
});

test("generate Apply rolls back inserted slides when a template shape is missing", async () => {
  const fixture = planFixture({ missingTitle: true });
  await app.ask();
  await assert.rejects(app.applyProposal(), /missing its named title or body shape/);
  assert.equal(fixture.slides.length, 1); assert.equal(app.state.proposal, null);
});

test("generate mode rejects non-outline model replies before any proposal", async () => {
  const fixture = planFixture();
  fixture.result.reply = "Xin chào\nTôi có thể giúp gì\nBạn muốn tạo slide nào";
  await assert.rejects(app.ask(), /empty slide outline|outline is empty/);
  assert.equal(app.state.proposal, null); assert.equal(fixture.slides.length, 1);
});
