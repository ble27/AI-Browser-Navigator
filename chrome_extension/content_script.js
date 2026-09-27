(() => {
  "use strict";

  const ALLOWED_OPERATIONS = new Set([
    "snapshot",
    "click",
    "focus",
    "type",
    "submit",
    "edit_focused_field"
  ]);
  const FIELD_ACTIONS = new Set(["unfocus", "delete_line", "clear_search", "delete_word"]);
  const MAX_TEXT_LENGTH = 10_000;
  const elementIds = new WeakMap();
  const elementsById = new Map();
  const pageNonce = crypto.randomUUID();
  let nextElementId = 1;
  // Retain the last page field operated on so follow-up edit commands still
  // work after a submitted search has blurred its field.
  let lastEditableField = null;

  function isSupportedPage() {
    if (window.top !== window) {
      return false;
    }
    if (window.location.protocol === "https:") {
      return true;
    }
    // Loopback HTTP is allowed only for local fixture testing.
    return (
      window.location.protocol === "http:" &&
      (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost")
    );
  }

  function normalizedText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function humanizeIdentifier(value) {
    return normalizedText(
      String(value || "")
        .replace(/[_\-]+/g, " ")
        .replace(/([a-z])([A-Z])/g, "$1 $2")
    );
  }

  function associatedLabel(element) {
    if ("labels" in element && element.labels && element.labels.length > 0) {
      return normalizedText(Array.from(element.labels, (label) => label.innerText).join(" "));
    }
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
      const owner = element.ownerDocument;
      const parts = labelledBy
        .split(/\s+/)
        .map((id) => owner.getElementById(id))
        .filter(Boolean)
        .map((node) => normalizedText(node.innerText));
      const joined = normalizedText(parts.join(" "));
      if (joined) {
        return joined;
      }
    }
    return "";
  }

  function nestedImageAlt(element) {
    if (!(element instanceof HTMLElement)) {
      return "";
    }
    const image = element.querySelector("img[alt]");
    if (!image) {
      return "";
    }
    return normalizedText(image.getAttribute("alt"));
  }

  function accessibleName(element) {
    const aria = normalizedText(element.getAttribute("aria-label"));
    if (aria) {
      return aria;
    }
    const label = associatedLabel(element);
    if (label) {
      return label;
    }
    const dataLabel = normalizedText(
      element.getAttribute("data-label") ||
        element.getAttribute("data-name") ||
        element.getAttribute("data-seo") ||
        element.getAttribute("data-analytics-name")
    );
    if (dataLabel) {
      return dataLabel;
    }
    const placeholder = normalizedText(element.getAttribute("placeholder"));
    if (placeholder) {
      return placeholder;
    }
    // WebAssign and other LMS pages often use <input type="submit" value="Submit Answer">.
    if (
      element instanceof HTMLInputElement &&
      ["button", "submit", "reset", "image"].includes(element.type)
    ) {
      const valueName = normalizedText(element.value || element.getAttribute("alt"));
      if (valueName) {
        return valueName;
      }
    }
    const imageAlt = nestedImageAlt(element);
    if (imageAlt) {
      return imageAlt;
    }
    const inner = normalizedText(element.innerText);
    if (inner) {
      return inner;
    }
    const title = normalizedText(element.getAttribute("title"));
    if (title) {
      return title;
    }
    const itemprop = humanizeIdentifier(element.getAttribute("itemprop"));
    if (itemprop) {
      return itemprop;
    }
    const nameAttr = humanizeIdentifier(element.getAttribute("name"));
    if (nameAttr) {
      return nameAttr;
    }
    const idAttr = humanizeIdentifier(element.id);
    if (idAttr) {
      return idAttr;
    }
    return "";
  }

  function metaContent(selector) {
    const node = document.querySelector(selector);
    if (!node) {
      return "";
    }
    return normalizedText(node.getAttribute("content"));
  }

  function collectSeoMeta() {
    // Capture common SEO / Open Graph tags so voice matching and --dump-page
    // can use the same page signals search engines and social previews use.
    const keywordsRaw = metaContent('meta[name="keywords" i]');
    const keywords = keywordsRaw
      ? keywordsRaw
          .split(",")
          .map((part) => normalizedText(part))
          .filter(Boolean)
          .slice(0, 32)
      : [];
    const canonical =
      normalizedText(document.querySelector('link[rel="canonical"]')?.getAttribute("href")) ||
      "";
    return {
      description:
        metaContent('meta[name="description" i]') ||
        metaContent('meta[property="og:description"]'),
      site_name:
        metaContent('meta[property="og:site_name"]') ||
        metaContent('meta[name="application-name" i]'),
      og_title: metaContent('meta[property="og:title"]'),
      keywords,
      canonical_url: canonical
    };
  }

  function roleFor(element) {
    const explicitRole = element.getAttribute("role");
    // Combobox is how many site-search fields expose themselves (Apple, etc.).
    if (explicitRole === "combobox") {
      return "textbox";
    }
    if (["button", "link", "textbox", "checkbox"].includes(explicitRole)) {
      return explicitRole;
    }
    if (element instanceof HTMLButtonElement) {
      return "button";
    }
    if (element instanceof HTMLAnchorElement && element.hasAttribute("href")) {
      return "link";
    }
    if (element instanceof HTMLTextAreaElement || element.isContentEditable) {
      return "textbox";
    }
    if (element instanceof HTMLInputElement) {
      if (element.type === "checkbox") {
        return "checkbox";
      }
      if (!["button", "submit", "reset", "image", "hidden", "radio", "file"].includes(element.type)) {
        return "textbox";
      }
      if (["button", "submit", "reset", "image"].includes(element.type)) {
        return "button";
      }
    }
    return null;
  }

  function isVisible(element) {
    if (element.hasAttribute("disabled") || element.getAttribute("aria-hidden") === "true") {
      return false;
    }
    // Prefer the browser's own visibility check when available (handles
    // content-visibility and some offscreen cases better than rect alone).
    if (typeof element.checkVisibility === "function") {
      try {
        return element.checkVisibility({
          checkOpacity: true,
          checkVisibilityCSS: true,
          contentVisibilityAuto: true
        });
      } catch (_error) {
        // Fall through to the manual heuristic below.
      }
    }
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      style.opacity !== "0" &&
      rect.width > 0 &&
      rect.height > 0
    );
  }

  function* iterDocuments(root) {
    yield root;
    if (typeof root.querySelectorAll !== "function") {
      return;
    }
    for (const element of root.querySelectorAll("*")) {
      if (element.shadowRoot) {
        // Open shadow roots only; closed ones are intentionally unreachable.
        yield* iterDocuments(element.shadowRoot);
      }
      if (element.tagName === "IFRAME") {
        try {
          const child = element.contentDocument;
          if (child) {
            yield* iterDocuments(child);
          }
        } catch (_error) {
          // Cross-origin iframes are intentionally skipped.
        }
      }
    }
  }

  function idFor(element) {
    let id = elementIds.get(element);
    if (!id) {
      id = `${pageNonce}:${nextElementId}`;
      nextElementId += 1;
      elementIds.set(element, id);
    }
    elementsById.set(id, element);
    return id;
  }

  function snapshot() {
    elementsById.clear();
    const selector = [
      "button",
      "a[href]",
      "input",
      "textarea",
      "[contenteditable='true']",
      "[role='button']",
      "[role='link']",
      "[role='textbox']",
      "[role='combobox']",
      "[role='checkbox']",
      "[role='searchbox']"
    ].join(",");
    const elements = [];
    const seen = new Set();
    for (const root of iterDocuments(document)) {
      if (!root.querySelectorAll) {
        continue;
      }
      for (const element of root.querySelectorAll(selector)) {
        if (seen.has(element)) {
          continue;
        }
        seen.add(element);
        let role = roleFor(element);
        if (element.getAttribute("role") === "searchbox") {
          role = "textbox";
        }
        const name = accessibleName(element);
        if (role && name && isVisible(element)) {
          elements.push({ id: idFor(element), role, name });
        }
      }
    }
    return {
      url: window.location.href,
      title: document.title,
      seo: collectSeoMeta(),
      elements
    };
  }

  function resolveTarget(targetId) {
    if (typeof targetId !== "string" || targetId.length === 0 || targetId.length > 200) {
      throw new Error("target_id must be a non-empty string");
    }
    let target = elementsById.get(targetId);
    if (!target || !target.isConnected) {
      snapshot();
      target = elementsById.get(targetId);
    }
    if (!target || !target.isConnected || !isVisible(target)) {
      throw new Error("Target is no longer available; request a fresh snapshot");
    }
    return target;
  }

  function setElementValue(element, text, inputType = "insertText") {
    if (typeof text !== "string" || text.length > MAX_TEXT_LENGTH) {
      throw new Error(`text must be a string of at most ${MAX_TEXT_LENGTH} characters`);
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const prototype =
        element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
      setter.call(element, text);
    } else if (element.isContentEditable || element.getAttribute("role") === "textbox") {
      element.textContent = text;
      placeCaretAtEnd(element);
    } else {
      throw new Error("Target does not accept text");
    }
    element.dispatchEvent(
      new InputEvent("input", { bubbles: true, inputType, data: text || null })
    );
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function placeCaretAtEnd(element) {
    const selection = window.getSelection();
    if (!selection) {
      return;
    }
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function isSearchField(element) {
    const name = accessibleName(element).toLocaleLowerCase();
    return (
      (element instanceof HTMLInputElement && element.type === "search") ||
      element.getAttribute("role") === "searchbox" ||
      /(^|\W)search(\W|$)/.test(name)
    );
  }

  function isComposer(element) {
    const name = accessibleName(element).toLocaleLowerCase();
    const textControl =
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      element.isContentEditable ||
      element.getAttribute("role") === "textbox";
    return textControl && /(^|\W)(ask|chat|compose|composer|message|prompt|reply)(\W|$)/.test(name);
  }

  function focusedEditableField(action) {
    const active = document.activeElement;
    const activeIsEditable = active instanceof HTMLElement &&
      (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement ||
        active.isContentEditable || active.getAttribute("role") === "textbox");
    let candidate = activeIsEditable ? active : lastEditableField;
    if (action === "clear_search" &&
        (!(candidate instanceof HTMLElement) || !candidate.isConnected || !isSearchField(candidate))) {
      const visibleSearchFields = Array.from(
        document.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']")
      ).filter((field) => isVisible(field) && isSearchField(field));
      candidate = visibleSearchFields.length === 1 ? visibleSearchFields[0] : candidate;
    }
    if (!(candidate instanceof HTMLElement) || !candidate.isConnected) {
      throw new Error("No supported page field is focused");
    }
    const container =
      candidate instanceof HTMLInputElement || candidate instanceof HTMLTextAreaElement
        ? candidate
        : candidate.closest("[contenteditable='true'], [role='textbox']");
    const element = container || candidate;
    const editable =
      element instanceof HTMLTextAreaElement ||
      element.isContentEditable ||
      element.getAttribute("role") === "textbox" ||
      (element instanceof HTMLInputElement &&
        !["button", "submit", "reset", "image", "hidden", "radio", "file"].includes(element.type));
    if (
      !editable ||
      element.hasAttribute("disabled") ||
      element.hasAttribute("readonly") ||
      element.getAttribute("aria-disabled") === "true" ||
      !isVisible(element)
    ) {
      throw new Error("No supported page field is focused");
    }
    const search = isSearchField(element);
    const composer = isComposer(element);
    if (action === "clear_search" ? !search : !search && !composer) {
      throw new Error("Focus a page search field or composer before using this command");
    }
    element.focus();
    lastEditableField = element;
    return element;
  }

  function deletePreviousWord(element) {
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      const value = element.value;
      // Always operate at the end: speech entry can leave a stale caret or
      // selection in the middle of a search field.
      let start = value.length;
      let end = value.length;
      while (start > 0 && /\s/.test(value[start - 1])) {
        start -= 1;
      }
      while (start > 0 && !/\s/.test(value[start - 1])) {
        start -= 1;
      }
      if (start === end) {
        return;
      }
      const nextValue = value.slice(0, start) + value.slice(end);
      const prototype =
        element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, "value").set.call(element, nextValue);
      element.setSelectionRange(start, start);
      element.dispatchEvent(
        new InputEvent("input", { bubbles: true, inputType: "deleteWordBackward", data: null })
      );
      element.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }

    const selection = window.getSelection();
    if (!selection) {
      throw new Error("The page composer does not expose a text selection");
    }
    placeCaretAtEnd(element);
    if (selection.isCollapsed && typeof selection.modify === "function") {
      selection.modify("extend", "backward", "word");
    }
    if (selection.isCollapsed) {
      return;
    }
    if (!document.execCommand("delete")) {
      selection.getRangeAt(0).deleteContents();
      element.dispatchEvent(
        new InputEvent("input", { bubbles: true, inputType: "deleteWordBackward", data: null })
      );
    }
  }

  function editFocusedField(action) {
    if (!FIELD_ACTIONS.has(action)) {
      throw new Error("Unsupported focused-field action");
    }
    const element = focusedEditableField(action);
    if (action === "unfocus") {
      element.blur();
      return;
    }
    if (action === "delete_word") {
      deletePreviousWord(element);
      return;
    }
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      element.setSelectionRange(0, element.value.length);
      setElementValue(element, "", "deleteContent");
    } else {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(element);
      selection.removeAllRanges();
      selection.addRange(range);
      if (!document.execCommand("delete")) {
        element.textContent = "";
        element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContent" }));
      }
    }
  }

  function pressEnter(element) {
    for (const type of ["keydown", "keypress", "keyup"]) {
      element.dispatchEvent(
        new KeyboardEvent(type, {
          key: "Enter",
          code: "Enter",
          keyCode: 13,
          which: 13,
          bubbles: true,
          cancelable: true
        })
      );
    }
  }

  function submitThroughField(element) {
    const form = element.closest("form");
    if (form) {
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
      }
      return;
    }
    // LMS widgets (WebAssign-style) often listen for Enter outside a <form>.
    pressEnter(element);
  }

  function execute(request) {
    if (!isSupportedPage()) {
      throw new Error("Only top-level HTTPS pages (or http://127.0.0.1/localhost) are supported");
    }
    if (!request || typeof request !== "object" || Array.isArray(request)) {
      throw new Error("Request must be an object");
    }
    if (!ALLOWED_OPERATIONS.has(request.operation)) {
      throw new Error("Unsupported operation");
    }
    if (request.operation === "snapshot") {
      return snapshot();
    }
    if (request.operation === "edit_focused_field") {
      editFocusedField(request.action);
      return {};
    }
    const target = resolveTarget(request.target_id);
    if (request.operation === "click") {
      target.click();
      return {};
    }
    if (request.operation === "focus") {
      target.focus();
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ||
          target.isContentEditable || target.getAttribute("role") === "textbox") {
        lastEditableField = target;
      }
      return {};
    }
    if (request.operation === "type" || request.operation === "submit") {
      target.focus();
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ||
          target.isContentEditable || target.getAttribute("role") === "textbox") {
        lastEditableField = target;
      }
      setElementValue(target, request.text);
      if (request.operation === "submit") {
        submitThroughField(target);
        target.blur();
      }
      return {};
    }
    throw new Error("Unsupported operation");
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    try {
      sendResponse({ ok: true, result: execute(request) });
    } catch (error) {
      sendResponse({ ok: false, error: error instanceof Error ? error.message : "Page operation failed" });
    }
    return false;
  });

  // Wake the MV3 service worker after every supported page load. The worker
  // owns Native Messaging and may have been suspended since the app started.
  chrome.runtime.sendMessage({ type: "page_bridge_ready" }).catch(() => {});
})();
