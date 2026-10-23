"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { isSearchResultLink } = require("./result_links");

// Minimal anchor stand-in: `inside` lists selectors the anchor sits within and
// `heading` says whether it contains or sits in a heading.
const anchor = ({ inside = [], heading = false }) => ({
  closest: (selector) => {
    const wanted = selector.split(",").map((part) => part.trim());
    return wanted.some((part) => inside.includes(part)) ? {} : null;
  },
  querySelector: (selector) => (heading && /h[23]/.test(selector) ? {} : null),
});

test("a headed link inside the results container is a result", () => {
  assert.equal(isSearchResultLink(anchor({ inside: ["#search"], heading: true })), true);
  assert.equal(isSearchResultLink(anchor({ inside: ["#b_results"], heading: true })), true);
});

test("header, footer, and unheaded links are not results", () => {
  assert.equal(isSearchResultLink(anchor({ inside: ["#search"], heading: false })), false);
  assert.equal(isSearchResultLink(anchor({ inside: [], heading: true })), false);
  assert.equal(isSearchResultLink(anchor({ inside: ["#search", "nav"], heading: true })), false);
});

test("sponsored results are excluded", () => {
  assert.equal(
    isSearchResultLink(anchor({ inside: ["#search", "#tads"], heading: true })),
    false,
  );
});
