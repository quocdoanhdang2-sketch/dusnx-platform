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
