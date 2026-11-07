"use strict";
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");

const MAX_BODY = 64 * 1024;
const ASSETS = new Map([
  ["/", { file: "word-taskpane.html", type: "text/html; charset=utf-8" }],
  ["/word-taskpane.html", { file: "word-taskpane.html", type: "text/html; charset=utf-8" }],
  ["/word-taskpane.js", { file: "word-taskpane.js", type: "text/javascript; charset=utf-8" }],
]);
const CSP = [
  "default-src 'self' https://appsforoffice.microsoft.com",
  "script-src 'self' https://appsforoffice.microsoft.com",
  "style-src 'self' 'unsafe-inline'",
  "connect-src 'self'",
  "img-src 'self' data:",
  "frame-ancestors 'self' https://*.officeapps.live.com https://*.office.com https://*.microsoft365.com https://*.sharepoint.com https://*.cloud.microsoft https://*.office.net",
  "base-uri 'none'",
  "form-action 'none'",
].join("; ");

function gatewayUrl(raw) {
  let url;
  try { url = new URL(String(raw || "http://127.0.0.1:8080")); }
  catch { throw new Error("WORD_ADDIN_GATEWAY is not a valid URL"); }
  if (!/^https?:$/.test(url.protocol)) throw new Error("WORD_ADDIN_GATEWAY must use http or https");
  if (url.username || url.password) throw new Error("WORD_ADDIN_GATEWAY must not contain credentials");
  if (url.pathname !== "/" || url.search || url.hash) throw new Error("WORD_ADDIN_GATEWAY must be an origin without path, query or fragment");
  if (!["localhost", "127.0.0.1", "[::1]"].includes(url.hostname.toLowerCase())) throw new Error("WORD_ADDIN_GATEWAY must be a loopback address");
  return url.origin;
}

function isAssetPath(pathname) { return ASSETS.has(pathname); }

function requestHeaders(headers) {
  const out = {};
  for (const name of ["authorization", "content-type", "accept"]) if (headers[name]) out[name] = headers[name];
  return out;
}

function responseHeaders(upstream) {
  const out = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
  if (upstream["content-type"]) out["content-type"] = upstream["content-type"];
  return out;
}

function assetHeaders(asset) {
  return {
    "content-type": asset.type,
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "content-security-policy": CSP,
  };
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "cache-control": "no-store", "x-content-type-options": "nosniff", ...headers });
  res.end(body);
}

function serveAsset(req, res, asset) {
  const file = path.join(__dirname, asset.file);
  const stat = fs.statSync(file);
  res.writeHead(200, { ...assetHeaders(asset), "content-length": String(stat.size) });
  if (req.method === "HEAD") return res.end();
  fs.createReadStream(file).pipe(res);
}

function proxy(req, res, target) {
  if (!["GET", "POST"].includes(req.method)) return send(res, 405, "Method not allowed\n", { "content-type": "text/plain; charset=utf-8" });
  let size = 0;
  const chunks = [];
  req.on("data", chunk => {
    size += chunk.length;
    if (size > MAX_BODY) { req.destroy(); if (!res.headersSent) send(res, 413, "Request body too large\n", { "content-type": "text/plain; charset=utf-8" }); return; }
    chunks.push(chunk);
  });
  req.on("end", () => {
    if (res.headersSent) return;
    const body = Buffer.concat(chunks);
    const headers = { ...requestHeaders(req.headers), "content-length": String(body.length) };
    const transport = target.startsWith("https:") ? https : http;
    const upstream = transport.request(new URL(target + req.url), { method: req.method, headers, timeout: 120000 }, response => {
      res.writeHead(response.statusCode || 502, responseHeaders(response.headers));
      response.pipe(res);
    });
    upstream.on("timeout", () => upstream.destroy(new Error("gateway timeout")));
    upstream.on("error", () => { if (!res.headersSent) send(res, 502, JSON.stringify({ detail: "Gateway unavailable" }), { "content-type": "application/json; charset=utf-8" }); });
    upstream.end(body.length ? body : undefined);
  });
  req.on("error", () => { if (!res.headersSent) send(res, 400, "Bad request\n", { "content-type": "text/plain; charset=utf-8" }); });
}

function createServer({ cert, key, gateway }) {
  const target = gatewayUrl(gateway);
  return https.createServer({ cert, key }, (req, res) => {
    const { pathname } = new URL(req.url, "https://localhost");
    if (ASSETS.has(pathname)) {
      if (!["GET", "HEAD"].includes(req.method)) return send(res, 405, "Method not allowed\n", { "content-type": "text/plain; charset=utf-8" });
      return serveAsset(req, res, ASSETS.get(pathname));
    }
    if (pathname.startsWith("/v1/")) return proxy(req, res, target);
    send(res, 404, "Not found\n", { "content-type": "text/plain; charset=utf-8" });
  });
}

function main() {
  const certPath = process.env.WORD_ADDIN_TLS_CERT;
  const keyPath = process.env.WORD_ADDIN_TLS_KEY;
  if (!certPath || !keyPath) {
    console.error("Set WORD_ADDIN_TLS_CERT and WORD_ADDIN_TLS_KEY to PEM files; refusing to run without TLS.");
    process.exit(1);
  }
  const gateway = gatewayUrl(process.env.WORD_ADDIN_GATEWAY);
  const port = Number(process.env.WORD_ADDIN_PORT || 3001);
  if (!Number.isInteger(port) || port < 1 || port > 65535) { console.error("WORD_ADDIN_PORT must be a TCP port."); process.exit(1); }
  const server = createServer({ cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath), gateway });
  const host = process.env.WORD_ADDIN_HOST || "127.0.0.1";
  server.listen(port, host, () => console.log(`Word task pane: https://${host}:${port}/word-taskpane.html (gateway ${gateway})`));
  for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.close(() => process.exit(0)));
}

if (require.main === module) main();
module.exports = { MAX_BODY, gatewayUrl, isAssetPath, requestHeaders, responseHeaders, assetHeaders, createServer };
