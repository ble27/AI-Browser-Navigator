"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { deleteCurrentLine, fieldAllowsAction } = require("./text_edit");

test("deletes only the line that contains the caret", () => {
  assert.deepEqual(deleteCurrentLine("alpha\nbeta\ngamma", 8, 8), {
    value: "alpha\ngamma",
    caret: 6,
  });
});

test("deletes the first line including its newline", () => {
  assert.deepEqual(deleteCurrentLine("alpha\nbeta", 1, 1), {
    value: "beta",
    caret: 0,
  });
});

test("deletes the last line including the newline before it", () => {
  assert.deepEqual(deleteCurrentLine("alpha\nbeta", 7, 7), {
    value: "alpha",
    caret: 5,
  });
});

test("clears a single-line input and parks the caret at the start", () => {
  assert.deepEqual(deleteCurrentLine("hello", 2, 2), { value: "", caret: 0 });
});

test("deletes every line a selection touches", () => {
  assert.deepEqual(deleteCurrentLine("a\nbb\nccc\nd", 3, 6), {
    value: "a\nd",
    caret: 2,
  });
});

test("delete line works in any focused editable, not only search or composer", () => {
  const plain = { editable: true, search: false, composer: false };
  assert.equal(fieldAllowsAction("delete_line", plain), true);
  assert.equal(fieldAllowsAction("clear_search", plain), false);
  assert.equal(fieldAllowsAction("delete_word", plain), false);
  assert.equal(fieldAllowsAction("delete_line", { editable: false, search: true, composer: true }), false);
});
