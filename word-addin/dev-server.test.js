const test = require("node:test"); const assert = require("node:assert/strict");
const server = require("./dev-server.js");

test("gateway defaults to loopback and normalizes an origin", () => {
  assert.equal(server.gatewayUrl(), "http://127.0.0.1:8080");
  assert.equal(server.gatewayUrl("http://localhost:8181/"), "http://localhost:8181");
  assert.equal(server.gatewayUrl("https://127.0.0.1:8443"), "https://127.0.0.1:8443");
  assert.equal(server.gatewayUrl("http://[::1]:8181"), "http://[::1]:8181");
});

test("gateway rejects non-loopback, credentials, paths and non-http schemes", () => {
  for (const value of ["ftp://localhost:8080", "http://example.com:8080", "http://user:pass@localhost:8080", "http://localhost:8080/api", "http://localhost:8080/?x=1", "not a url"]) {
    assert.throws(() => server.gatewayUrl(value));
  }
});

test("only the task pane assets are served", () => {
  for (const value of ["/", "/word-taskpane.html", "/word-taskpane.js", "/taskpane.html", "/taskpane.js", "/deck-template.pptx"]) assert.equal(server.isAssetPath(value), true);
  for (const value of ["/manifest.xml", "/../word-taskpane.js", "/v1/chat", "/word-taskpane.html/..", "//word-taskpane.js", "/powerpoint-addin/taskpane.js", "/powerpoint-addin/deck-template.pptx"]) assert.equal(server.isAssetPath(value), false);
});

test("proxy forwards only auth/content headers and never cookies", () => {
  const headers = server.requestHeaders({ authorization: "Bearer synthetic", "content-type": "application/json", accept: "application/json", cookie: "session=secret", host: "localhost", connection: "keep-alive" });
  assert.deepEqual(headers, { authorization: "Bearer synthetic", "content-type": "application/json", accept: "application/json" });
});

test("proxy responses are not cacheable and do not leak set-cookie", () => {
  const headers = server.responseHeaders({ "content-type": "application/json", "set-cookie": "x=1", "cache-control": "public" });
  assert.deepEqual(headers, { "cache-control": "no-store", "x-content-type-options": "nosniff", "content-type": "application/json" });
});

test("static assets carry no-store, nosniff and a frame-ancestors policy", () => {
  const headers = server.assetHeaders({ type: "text/html; charset=utf-8" });
  assert.equal(headers["cache-control"], "no-store");
  assert.equal(headers["x-content-type-options"], "nosniff");
  assert.match(headers["content-security-policy"], /frame-ancestors/);
  assert.match(headers["content-security-policy"], /connect-src 'self'/);
});

test("request body limit is bounded", () => { assert.equal(server.MAX_BODY, 64 * 1024); });
