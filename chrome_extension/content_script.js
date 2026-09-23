(() => {
  "use strict";

  const ALLOWED_OPERATIONS = new Set(["snapshot", "click", "focus", "type", "submit"]);
  const MAX_TEXT_LENGTH = 10_000;
  const elementIds = new WeakMap();
  const elementsById = new Map();
  const pageNonce = crypto.randomUUID();
  let nextElementId = 1;

  function isSupportedPage() {
    return window.top === window && window.location.protocol === "https:";
  }

  function normalizedText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function associatedLabel(element) {
    if ("labels" in element && element.labels && element.labels.length > 0) {
      return normalizedText(Array.from(element.labels, (label) => label.innerText).join(" "));
    }
    return "";
  }

  function accessibleName(element) {
    return (
      normalizedText(element.getAttribute("aria-label")) ||
      associatedLabel(element) ||
      normalizedText(element.getAttribute("placeholder")) ||
      normalizedText(element.innerText) ||
      normalizedText(element.getAttribute("title"))
    );
  }

  function roleFor(element) {
    const explicitRole = element.getAttribute("role");
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
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      rect.width > 0 &&
      rect.height > 0 &&
      !element.hasAttribute("disabled") &&
      element.getAttribute("aria-hidden") !== "true"
    );
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
      "[role='checkbox']"
    ].join(",");
    const elements = [];
    for (const element of document.querySelectorAll(selector)) {
      const role = roleFor(element);
      const name = accessibleName(element);
      if (role && name && isVisible(element)) {
        elements.push({ id: idFor(element), role, name });
      }
    }
    return { url: window.location.href, title: document.title, elements };
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

  function setElementValue(element, text) {
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
    } else {
      throw new Error("Target does not accept text");
    }
    element.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function execute(request) {
    if (!isSupportedPage()) {
      throw new Error("Only top-level HTTPS pages are supported");
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
    const target = resolveTarget(request.target_id);
    if (request.operation === "click") {
      target.click();
      return {};
    }
    if (request.operation === "focus") {
      target.focus();
      return {};
    }
    if (request.operation === "type" || request.operation === "submit") {
      target.focus();
      setElementValue(target, request.text);
      if (request.operation === "submit") {
        const form = target.closest("form");
        if (!form) {
          throw new Error("Target is not inside a form");
        }
        form.requestSubmit();
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
})();
