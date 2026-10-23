"use strict";

/**
 * Delete the line containing the caret, or every line a selection touches.
 *
 * The caret is a point between characters. A trailing newline is removed with
 * the line so the following line moves up; the last line takes the newline
 * that precedes it instead.
 *
 * @param {string} value
 * @param {number} selectionStart
 * @param {number} selectionEnd
 * @returns {{value: string, caret: number}}
 */
function deleteCurrentLine(value, selectionStart, selectionEnd) {
  const text = String(value ?? "");
  const clamp = (index) => {
    if (!Number.isFinite(index)) {
      return text.length;
    }
    return Math.max(0, Math.min(text.length, Math.trunc(index)));
  };
  const from = Math.min(clamp(selectionStart), clamp(selectionEnd));
  const to = Math.max(clamp(selectionStart), clamp(selectionEnd));
  const lineStart = (index) => text.lastIndexOf("\n", Math.max(0, index - 1)) + 1;
  const lineEnd = (index) => {
    const found = text.indexOf("\n", index);
    return found === -1 ? text.length : found;
  };
  let cutStart = lineStart(from);
  let cutEnd = lineEnd(to);
  if (cutEnd < text.length && text[cutEnd] === "\n") {
    cutEnd += 1;
  } else if (cutStart > 0 && text[cutStart - 1] === "\n") {
    cutStart -= 1;
  }
  return { value: text.slice(0, cutStart) + text.slice(cutEnd), caret: cutStart };
}

/**
 * Decide whether a focused field may receive one edit action.
 *
 * `delete_line` follows the blinking cursor in any editable field. Clearing
 * search and deleting a word stay limited to search fields and composers.
 *
 * @param {string} action
 * @param {{editable: boolean, search: boolean, composer: boolean}} field
 * @returns {boolean}
 */
function fieldAllowsAction(action, field) {
  if (!field || !field.editable) {
    return false;
  }
  if (action === "delete_line") {
    return true;
  }
  if (action === "unfocus" || action === "delete_word") {
    return Boolean(field.search || field.composer);
  }
  if (action === "clear_search") {
    return Boolean(field.search);
  }
  return false;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { deleteCurrentLine, fieldAllowsAction };
}
