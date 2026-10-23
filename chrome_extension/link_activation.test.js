"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { decideLinkActivation } = require("./link_activation");

test("same-tab https links are assigned", () => {
  assert.equal(
    decideLinkActivation({ href: "https://example.com/docs", target: null, download: false }),
    "assign",
  );
});

test("blank targets open a new tab", () => {
  assert.equal(
    decideLinkActivation({ href: "https://example.com/docs", target: "_blank", download: false }),
    "blank",
  );
});

test("javascript, download, and empty links are not followed", () => {
  assert.equal(decideLinkActivation({ href: "javascript:alert(1)", target: null }), "skip");
  assert.equal(
    decideLinkActivation({ href: "https://example.com/file", target: null, download: true }),
    "skip",
  );
  assert.equal(decideLinkActivation({ href: "", target: null }), "skip");
  assert.equal(decideLinkActivation(null), "skip");
});
