const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");

class FakeElement {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.className = "";
  }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  get childElementCount() { return this.children.length; }
}

const elements = new Map();
for (const id of ["platform", "user", "linked", "content", "feedback", "send", "output",
  "timeline", "timelineStatus", "reloadTimeline", "loadOlder", "generateSlides", "jobOutput",
  "slidePrompt", "slideCount"])
  elements.set(id, new FakeElement());
elements.get("platform").value = "web";
elements.get("user").value = "user/id";
elements.get("linked").value = "shared key";

global.window = {};
global.document = {
  getElementById: (id) => elements.get(id),
  createElement: (tag) => new FakeElement(tag)
};

const {renderTimelineItem, timelineUrl} = require("./app.js");

test("timeline renders untrusted event content as text", () => {
  const payload = '<img src=x onerror="globalThis.compromised=true">';
  const card = renderTimelineItem({platform: "web", content: payload});
  assert.equal(card.children[1].textContent, payload);
  assert.equal(globalThis.compromised, undefined);
  assert.equal(fs.readFileSync(require.resolve("./app.js"), "utf8").includes("innerHTML"), false);
});

test("timeline lookup safely encodes identity inputs", () => {
  const url = timelineUrl(null);
  assert.match(url, /user%2Fid/);
  assert.match(url, /linkedUserId=shared\+key/);
});
