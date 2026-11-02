const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}

function app(fetch) {
  const elements = new Map();
  const context = vm.createContext({
    window: {}, console, fetch,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    document: {
      querySelectorAll: () => [],
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {
          value: 'synthetic', hidden: false, disabled: false, style: {},
          textContent: '', classList: { add() {}, remove() {}, toggle() {} },
          replaceChildren() {}, focus() {},
        });
        return elements.get(id);
      },
    },
  });
  vm.runInContext(fs.readFileSync(require.resolve('./app.js'), 'utf8'), context);
  return expression => vm.runInContext(expression, context);
}

const ok = data => ({ ok: true, status: 200, json: async () => data });

test('logout invalidates local auth before the server responds', async () => {
  const pending = deferred();
  let sentToken;
  const run = app((_, options) => { sentToken = options.headers.Authorization; return pending.promise; });
  run('authToken = "old-token"; currentUser = {user_id: "old-user"};');
  const logout = run('handleLogout()');
  const observed = run('({token: authToken, user: currentUser, session: currentSessionId})');
  pending.resolve(ok({}));
  await logout;
  assert.equal(observed.token, null);
  assert.equal(observed.user, null);
  assert.equal(observed.session, null);
  assert.equal(sentToken, 'Bearer old-token');
});

test('a login response arriving after logout cannot restore auth', async () => {
  const pending = deferred();
  const run = app(path => path.endsWith('/auth/login') ? pending.promise : Promise.resolve(ok([])));
  const login = run('handleLogin({preventDefault() {}})');
  await run('handleLogout()');
  pending.resolve(ok({ token: 'late-token' }));
  await login;
  assert.equal(run('authToken'), null);
});

test('an old 401 cannot log out a newer session', async () => {
  const pending = deferred();
  const run = app(() => pending.promise);
  run('authToken = "old-token"');
  const request = run('apiFetch("/v1/memories")');
  run('authToken = "new-token"');
  pending.resolve({ ok: false, status: 401, headers: { get: () => 'application/json' }, json: async () => ({}) });
  await assert.rejects(request);
  assert.equal(run('authToken'), 'new-token');
});

test('a response body decoded after session change is discarded', async () => {
  const body = deferred();
  const reading = deferred();
  const run = app(async () => ({ ok: true, status: 200, json: () => { reading.resolve(); return body.promise; } }));
  run('authToken = "old-token"');
  const request = run('apiFetch("/v1/memories")');
  await reading.promise;
  run('authToken = "new-token"');
  body.resolve([{ content: 'old-user-private-memory' }]);
  await assert.rejects(request);
});

test('an old chat reply cannot render or unlock a new users submission', async () => {
  const pending = deferred();
  const run = app(() => pending.promise);
  run(`authToken = 'old-token'; currentSessionId = 'old-session';
    window.rendered = [];
    appendMessageBubble = (...args) => window.rendered.push(args);
    appendProviderErrorCard = (...args) => window.rendered.push(args);`);
  const request = run('sendMessage("old-private-message")');
  run(`clearAuthentication(); authToken = 'new-token'; currentSessionId = 'new-session';
    isSending = true; el('sendBtn').disabled = true; window.rendered = [];`);
  pending.resolve(ok({ provider_ok: true, reply: 'old-private-reply' }));
  await request;
  assert.equal(run('window.rendered.length'), 0);
  assert.equal(run('isSending'), true);
  assert.equal(run('el("sendBtn").disabled'), true);
});
