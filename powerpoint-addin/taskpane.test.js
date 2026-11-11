const test = require("node:test"); const assert = require("node:assert/strict");
global.fetch = async () => ({ ok:true, headers:{get:()=>"application/json"}, json:async()=>({}) });
const app = require("./taskpane.js");
test("sanitizes and bounds Office context", () => { assert.equal(app.safe("a\u0000b"), "a b"); assert.equal(app.safe("x".repeat(5000)).length, 4000); });
test("logout clears in-memory token", () => { app.state.token = "secret"; app.state.proposal = {text:"x"}; app.logout(); assert.equal(app.state.token, null); assert.equal(app.state.proposal, null); });

function officeFixture() {
  const fixture = { slideId: "slide-a", shapeId: "shape-a", text: "Original heading", writes: 0, requests: [] };
  const elements = {};
  global.document = { getElementById(id) { return elements[id] ||= { value: "Rewrite the heading", textContent: "", disabled: false }; } };
  global.PowerPoint = { run: async fn => {
    const range = { load() {}, get text() { return fixture.text; }, set text(value) { fixture.text = value; fixture.writes++; } };
    return fn({ sync: async () => {}, presentation: {
      getSelectedSlides: () => ({ load() {}, items: [{ id: fixture.slideId }] }),
      getSelectedShapes: () => ({ load() {}, items: [{ id: fixture.shapeId, textFrame: { hasText: true, load() {}, textRange: range } }] }),
    } });
  } };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false; app.state.lastApply = null;
  fixture.result = { reply: "Rewritten heading", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm" };
  global.fetch = async (url, options = {}) => { fixture.requests.push({ url: String(url), body: options.body ? JSON.parse(options.body) : null });
    return { ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result }; };
  fixture.elements = elements;
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

function planFixture({ missingTitle = false, existing = 1, numericIds = false, compositeIds = false, supported = true } = {}) {
  const elements = {}; let created = 0;
  const fixture = { slides: null, selected: [], elements, requests: [], result: null, tableSupported: supported, insertedBase64: [] };
  global.document = { getElementById(id) { return elements[id] ||= { value: "", textContent: "", disabled: false, style: {} }; } };
  global.Office = { context: { requirements: { isSetSupported: () => fixture.tableSupported } } };
  const slideFactory = fresh => {
    const shapes = [
      { name: "DUSN-X Accent" },
      ...(fresh && missingTitle ? [] : [{ name: "DUSN-X Title", textFrame: { textRange: { text: "" } } }]),
    ];
    const body = { name: "DUSN-X Body", textFrame: { textRange: { text: "" } },
      delete() { const index = shapes.indexOf(body); if (index >= 0) shapes.splice(index, 1); } };
    shapes.push(body, { name: "DUSN-X Footer", textFrame: { textRange: { text: "DUSN-X" } } });
    const id = compositeIds ? `${++created}#${3520995159 + created}` : numericIds ? ++created : (fresh ? `new-${++created}` : `existing-${++created}`);
    const tables = [];
    const slide = { id, tables,
      shapes: {
        load() {},
        get items() { return shapes; },
        addTable(rowCount, columnCount, options) {
          const cells = Array.from({ length: rowCount }, () => Array.from({ length: columnCount }, () => {
            const cell = { text: "", loaded: false, load() { cell.loaded = true; } };
            Object.defineProperty(cell, "isNullObject", { get() {
              if (!cell.loaded) throw new Error("isNullObject requires load() and context.sync()");
              return false;
            } });
            return cell;
          }));
          tables.push({ rowCount, columnCount, options, cells });
          const shape = { name: `Table ${tables.length}`, getTable: () => ({ load() {}, rowCount, columnCount,
            getCellOrNullObject: (row, column) => cells[row]?.[column] || { load() {}, isNullObject: true } }) };
          shapes.push(shape);
          return shape;
        },
      },
      delete() { const index = fixture.slides.indexOf(slide); if (index >= 0) fixture.slides.splice(index, 1); } };
    return slide;
  };
  fixture.slides = Array.from({ length: existing }, () => slideFactory(false));
  global.PowerPoint = { run: async fn => fn({ sync: async () => {}, presentation: {
    slides: { load() {}, get items() { return fixture.slides; } },
    getSelectedSlides() { return { load() {}, get items() { return fixture.selected; } }; },
    insertSlidesFromBase64(_base64, options = {}) {
      fixture.insertedBase64.push(_base64);
      const fresh = slideFactory(true);
      if (options.targetSlideId) {
        const index = fixture.slides.findIndex(slide => String(slide.id) === String(options.targetSlideId));
        fixture.slides.splice(index + 1, 0, fresh);
      } else fixture.slides.unshift(fresh);
    },
  } }) };
  elements.mode = { value: "generate", disabled: false, style: {} };
  elements.count = { value: "2", disabled: false, style: {} };
  elements.afterSelected = { checked: false, disabled: false, style: {} };
  elements.layout = { value: "bullets", disabled: false, style: {} };
  elements.prompt = { value: "Tạo 2 slide tóm tắt kế hoạch", disabled: false, style: {} };
  fixture.result = { reply: "# Mở đầu\n- Ý một\n- Ý hai\n# Kết luận\n- Ý ba", provider_ok: true, provider_called: true,
    provider_used: "ollama", model_used: "synthetic-harness-model", response_source: "llm" };
  global.fetch = async (url, options = {}) => {
    fixture.requests.push({ url: String(url), body: options.body ? JSON.parse(options.body) : null });
    return String(url) === "deck-template.pptx"
      ? { ok: true, arrayBuffer: async () => new Uint8Array(2048).buffer }
      : { ok: true, headers: { get: () => "application/json" }, json: async () => fixture.result };
  };
  app.state.token = "synthetic-harness-token"; app.state.sessionId = "session-a"; app.state.proposal = null; app.state.busy = false; app.state.lastApply = null;
  return fixture;
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

test("generate mode can insert new slides after the selected slide", async () => {
  const fixture = planFixture({ existing: 3 });
  fixture.selected.push(fixture.slides[1]);
  fixture.elements.afterSelected.checked = true;
  await app.ask();
  assert.equal(app.state.proposal.targetLabel, "after slide 2");
  assert.equal(app.state.proposal.targetId, String(fixture.slides[1].id));
  await app.applyProposal();
  assert.equal(fixture.slides.length, 5);
  assert.equal(fixture.slides[0].id, "existing-1");
  assert.equal(fixture.slides[1].id, "existing-2");
  assert.deepEqual(fixture.slides.slice(2, 4).map(slide => slide.shapes.items.find(s => s.name === "DUSN-X Title").textFrame.textRange.text),
    ["Mở đầu", "Kết luận"]);
  assert.deepEqual(fixture.slides.slice(2, 4).map(slide => slide.shapes.items.find(s => s.name === "DUSN-X Footer").textFrame.textRange.text),
    ["DUSN-X · 3", "DUSN-X · 4"]);
  assert.equal(fixture.slides[4].id, "existing-3");
});

test("generate Apply matches host slide ids that contain # from the real host", async () => {
  const fixture = planFixture({ existing: 3, compositeIds: true });
  fixture.selected.push(fixture.slides[1]);
  fixture.elements.afterSelected.checked = true;
  assert.match(String(fixture.slides[1].id), /^2#\d+$/);
  await app.ask();
  assert.equal(app.state.proposal.targetId, String(fixture.slides[1].id));
  assert.equal(app.state.proposal.targetLabel, "after slide 2");
  await app.applyProposal();
  assert.equal(fixture.slides.length, 5);
  assert.deepEqual(fixture.slides.slice(2, 4).map(slide => slide.shapes.items.find(s => s.name === "DUSN-X Footer").textFrame.textRange.text),
    ["DUSN-X · 3", "DUSN-X · 4"]);
});

test("generate Apply matches numeric slide ids from the real host", async () => {
  const fixture = planFixture({ existing: 3, numericIds: true });
  fixture.selected.push(fixture.slides[1]);
  fixture.elements.afterSelected.checked = true;
  assert.equal(typeof fixture.slides[1].id, "number");
  await app.ask();
  assert.equal(app.state.proposal.targetLabel, "after slide 2");
  await app.applyProposal();
  assert.equal(fixture.slides.length, 5);
});

test("generate Apply refuses when the reviewed target slide was deleted", async () => {
  const fixture = planFixture({ existing: 2 });
  fixture.selected.push(fixture.slides[1]);
  fixture.elements.afterSelected.checked = true;
  await app.ask();
  fixture.slides.splice(1, 1);
  await assert.rejects(app.applyProposal(), /target slide no longer exists/);
  assert.equal(fixture.slides.length, 1);
  assert.equal(app.state.proposal, null);
});

test("generate mode rejects non-outline model replies before any proposal", async () => {
  const fixture = planFixture();
  fixture.result.reply = "Xin chào\nTôi có thể giúp gì\nBạn muốn tạo slide nào";
  await assert.rejects(app.ask(), /empty slide outline|outline is empty/);
  assert.equal(app.state.proposal, null); assert.equal(fixture.slides.length, 1);
});

const TABLE_OUTLINE = "# Bảng kế hoạch\n| Hạng mục | Trạng thái |\n| --- | --- |\n| Dữ liệu | Đã khóa |\n| Huấn luyện | LoRA |";

test("generate mode builds a native table slide from a reviewed outline", async () => {
  const fixture = planFixture();
  fixture.elements.layout.value = "table";
  fixture.elements.count.value = "1";
  fixture.result.reply = TABLE_OUTLINE;
  await app.ask();
  assert.equal(fixture.slides.length, 1);
  assert.equal(app.state.proposal.kind, "table");
  assert.match(fixture.elements.proposal.textContent, /Hạng mục \| Trạng thái/);
  assert.match(fixture.elements.proposal.textContent, /Dữ liệu \| Đã khóa/);
  await app.applyProposal();
  assert.equal(fixture.slides.length, 2);
  const added = fixture.slides[1];
  assert.equal(added.tables.length, 1);
  assert.deepEqual(added.tables[0].cells.map(row => row.map(cell => cell.text)),
    [["Hạng mục", "Trạng thái"], ["Dữ liệu", "Đã khóa"], ["Huấn luyện", "LoRA"]]);
  assert.equal(added.shapes.items.some(shape => shape.name === "DUSN-X Body"), false);
  assert.equal(added.shapes.items.find(shape => shape.name === "DUSN-X Title").textFrame.textRange.text, "Bảng kế hoạch");
  assert.match(added.shapes.items.find(shape => shape.name === "DUSN-X Footer").textFrame.textRange.text, /^DUSN-X · \d+$/);
});

test("table mode refuses hosts without PowerPointApi 1.8 before calling the provider", async () => {
  const fixture = planFixture({ supported: false });
  fixture.elements.layout.value = "table";
  await assert.rejects(app.ask(), /PowerPointApi 1\.8/);
  assert.equal(fixture.requests.filter(request => request.url.endsWith("/v1/chat")).length, 0);
  assert.equal(fixture.slides.length, 1);
});

test("table Apply refuses a host that lost PowerPointApi 1.8 after review", async () => {
  const fixture = planFixture();
  fixture.elements.layout.value = "table";
  fixture.elements.count.value = "1";
  fixture.result.reply = TABLE_OUTLINE;
  await app.ask();
  fixture.tableSupported = false;
  await assert.rejects(app.applyProposal(), /PowerPointApi 1\.8/);
  assert.equal(fixture.slides.length, 1);
});

test("Undo removes only the slides inserted by the last Apply", async () => {
  const fixture = planFixture();
  await app.ask(); await app.applyProposal();
  assert.equal(fixture.slides.length, 3);
  const inserted = fixture.slides.slice(1).map(slide => slide.id);
  assert.deepEqual(app.state.lastApply.ids, inserted);
  await app.undoLastApply();
  assert.equal(fixture.slides.length, 1);
  assert.equal(fixture.slides[0].id, "existing-1");
  assert.equal(app.state.lastApply, null);
  await assert.rejects(app.undoLastApply(), /No slide insertion/);
});

test("Apply and Undo record content-free telemetry events", async () => {
  const fixture = planFixture();
  await app.ask(); await app.applyProposal(); await app.undoLastApply();
  const events = fixture.requests.filter(request => request.url.endsWith("/v1/me/events"));
  assert.deepEqual(events.map(event => event.body.event_type), ["apply", "undo"]);
  assert.equal(events[0].body.platform, "powerpoint");
  assert.equal(events[0].body.content, "bullets slides=2");
  assert.equal(events[1].body.content, "removed 2 slide(s)");
  assert.ok(!events[0].body.content.includes("Mở đầu"));
  assert.ok(!events[1].body.content.includes("Kết luận"));
});

test("table outline parser validates titles, dimensions and markdown shape", () => {
  assert.deepEqual(app.parseTablePlan(TABLE_OUTLINE),
    [{ title: "Bảng kế hoạch", table: [["Hạng mục", "Trạng thái"], ["Dữ liệu", "Đã khóa"], ["Huấn luyện", "LoRA"]] }]);
  for (const reply of ["", "| A |\n| --- |\n| 1 |", "# T\n```\n| A |\n| --- |\n| 1 |\n```", '{"slides":[]}',
    "# T\nnot a row", "| A |\n| --- |\n| 1 |\n# T", "# T\n| A | B |\n| --- | --- |\n| only |", "# T\n# U\n| A |\n| --- |\n| 1 |"])
    assert.throws(() => app.parseTablePlan(reply));
  assert.throws(() => app.validateTable([["H"], []]), /does not have/);
  const tooManyColumns = ["H1", "H2", "H3", "H4", "H5", "H6", "H7"];
  assert.throws(() => app.validateTable([tooManyColumns, Array(7).fill("x")]), /1-6 columns/);
});

test("secrets in the selected shape or instruction never reach the provider", async () => {
  const selection = officeFixture();
  selection.text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEexample";
  await assert.rejects(app.ask(), /private key/);
  assert.equal(selection.requests.filter(request => request.url.endsWith("/v1/chat")).length, 0);
  assert.equal(app.state.proposal, null);

  const instruction = officeFixture();
  global.document.getElementById("prompt").value = "Dùng sk-abcdefghijklmnopqrstuvwx để gọi API";
  await assert.rejects(app.ask(), /API key/);
  assert.equal(instruction.requests.filter(request => request.url.endsWith("/v1/chat")).length, 0);
  assert.equal(app.findSensitive("slide-management"), null);
});

function chartFixture(options = {}) {
  const fixture = planFixture(options);
  fixture.elements.chartTitle = { value: "Doanh thu theo quý", disabled: false, style: {} };
  fixture.elements.chartType = { value: "bar", disabled: false, style: {} };
  fixture.elements.chartData = { value: "Q1\t12.5\nQ2\t18\nQ3\t9,75", disabled: false, style: {} };
  fixture.elements.chartAfterSelected = { checked: false, disabled: false, style: {} };
  fixture.result = { file_base64: "A".repeat(2048), slide_count: 1, bytes: 1536, chart_type: "bar", categories: 3 };
  fixture.requests.length = 0;
  return fixture;
}

test("chart data parser accepts tab or pipe rows and rejects unsafe input", () => {
  assert.deepEqual(app.parseChartData("Q1\t12.5\nQ2\t18\nQ3\t9,75"),
    { labels: ["Q1", "Q2", "Q3"], values: [12.5, 18, 9.75] });
  assert.deepEqual(app.parseChartData("A | -2\nB | 3.5"), { labels: ["A", "B"], values: [-2, 3.5] });
  for (const raw of ["", "Q1\t1", "Q1\tx\nQ2\t2", "Q1\t1\nQ2\t2\nQ3\t3\nQ4\t4\nQ5\t5\nQ6\t6\nQ7\t7\nQ8\t8\nQ9\t9\nQ10\t10\nQ11\t11\nQ12\t12\nQ13\t13",
    "A\t1\textra\nB\t2", "A\t1e5\nB\t2", "A\tInfinite\nB\t2", `A\t1\n${"x".repeat(61)}\t2`, "A\t1\n\u0000\t2"]) {
    assert.throws(() => app.parseChartData(raw));
  }
});

test("chart insertion posts user rows and inserts exactly one native slide", async () => {
  const fixture = chartFixture();
  await app.insertChart();
  assert.equal(fixture.slides.length, 2);
  const post = fixture.requests.find(request => request.url.endsWith("/v1/office/chart-slide"));
  assert.deepEqual(post.body, { title: "Doanh thu theo quý", chart_type: "bar", labels: ["Q1", "Q2", "Q3"], values: [12.5, 18, 9.75] });
  assert.deepEqual(fixture.insertedBase64, ["A".repeat(2048)]);
  assert.equal(app.state.lastApply.ids.length, 1);
  assert.equal(fixture.elements.status.textContent, "Inserted one native chart slide after slide 1.");
  await new Promise(resolve => setImmediate(resolve));
  const event = fixture.requests.find(request => request.url.endsWith("/v1/me/events"));
  assert.equal(event.body.event_type, "insert_chart");
  assert.equal(event.body.content, "3 data points from user input (bar)");
  assert.ok(!event.body.content.includes("12.5"));
});

test("chart insertion never calls the model and refuses secrets before the network", async () => {
  const fixture = chartFixture();
  fixture.elements.chartData.value = "Q1\t-----BEGIN RSA PRIVATE KEY-----";
  await assert.rejects(app.insertChart(), /private key/);
  assert.equal(fixture.requests.length, 0);
  assert.equal(fixture.slides.length, 1);

  const unsupported = chartFixture({ supported: false });
  await assert.rejects(app.insertChart(), /PowerPointApi 1\.5/);
  assert.equal(unsupported.requests.length, 0);
  assert.equal(unsupported.slides.length, 1);
});

test("chart insertion can target the selected slide and invalid responses add nothing", async () => {
  const fixture = chartFixture({ existing: 3 });
  fixture.selected.push(fixture.slides[1]);
  fixture.elements.chartAfterSelected.checked = true;
  await app.insertChart();
  assert.equal(fixture.slides.length, 4);
  assert.equal(fixture.slides[2].id, app.state.lastApply.ids[0]);
  assert.equal(app.state.lastApply.label, "after slide 2");

  const invalid = chartFixture();
  invalid.result = { file_base64: "short" };
  await assert.rejects(app.insertChart(), /invalid/);
  assert.equal(invalid.slides.length, 1);
  assert.equal(invalid.insertedBase64.length, 0);
});
