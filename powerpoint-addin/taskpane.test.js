const test = require("node:test"); const assert = require("node:assert/strict");
global.fetch = async () => ({ ok:true, headers:{get:()=>"application/json"}, json:async()=>({}) });
const app = require("./taskpane.js");
test("sanitizes and bounds Office context", () => { assert.equal(app.safe("a\u0000b"), "a b"); assert.equal(app.safe("x".repeat(5000)).length, 4000); });
test("logout clears in-memory token", () => { app.state.token = "secret"; app.state.proposal = {text:"x"}; app.logout(); assert.equal(app.state.token, null); assert.equal(app.state.proposal, null); });
