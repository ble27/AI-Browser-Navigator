"use strict";

const NATIVE_HOST_NAME = "com.ai_gestures.page_bridge";
const OPERATIONS = new Set(["snapshot", "click", "focus", "type", "submit"]);
const MAX_REQUEST_ID_LENGTH = 128;
const MAX_TARGET_ID_LENGTH = 200;
const MAX_TEXT_LENGTH = 10_000;
let nativePort = null;
let reconnectTimer = null;

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validateRequest(message) {
  if (!isPlainObject(message)) {
    throw new Error("Request must be an object");
  }
  const { request_id: requestId, operation } = message;
  if (typeof requestId !== "string" || requestId.length === 0 || requestId.length > MAX_REQUEST_ID_LENGTH) {
    throw new Error("request_id must be a non-empty bounded string");
  }
  if (typeof operation !== "string" || !OPERATIONS.has(operation)) {
    throw new Error("Unsupported operation");
  }
  const expectedKeys = new Set(["request_id", "operation"]);
  if (operation !== "snapshot") {
    expectedKeys.add("target_id");
    if (
      typeof message.target_id !== "string" ||
      message.target_id.length === 0 ||
      message.target_id.length > MAX_TARGET_ID_LENGTH
    ) {
      throw new Error("target_id must be a non-empty bounded string");
    }
  }
  if (operation === "type" || operation === "submit") {
    expectedKeys.add("text");
    if (typeof message.text !== "string" || message.text.length > MAX_TEXT_LENGTH) {
      throw new Error("text must be a bounded string");
    }
  }
  if (Object.keys(message).some((key) => !expectedKeys.has(key))) {
    throw new Error("Request contains unsupported fields");
  }
  return {
    request_id: requestId,
    operation,
    ...(message.target_id === undefined ? {} : { target_id: message.target_id }),
    ...(message.text === undefined ? {} : { text: message.text })
  };
}

function validatePageResponse(response) {
  if (!isPlainObject(response) || typeof response.ok !== "boolean") {
    throw new Error("Page returned an invalid response");
  }
  if (!response.ok) {
    if (typeof response.error !== "string" || response.error.length === 0 || response.error.length > 1000) {
      throw new Error("Page returned an invalid error");
    }
    return { ok: false, error: response.error };
  }
  if (!isPlainObject(response.result)) {
    throw new Error("Page returned an invalid result");
  }
  return { ok: true, result: response.result };
}

async function activeHttpsTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const tab = tabs[0];
  if (!tab || typeof tab.id !== "number") {
    throw new Error("No active Chrome tab is available");
  }
  if (typeof tab.url !== "string" || !tab.url.startsWith("https://")) {
    throw new Error("The active tab must be an HTTPS page");
  }
  return tab;
}

async function handleNativeMessage(rawMessage) {
  let requestId = "invalid-request";
  try {
    if (isPlainObject(rawMessage) && typeof rawMessage.request_id === "string") {
      requestId = rawMessage.request_id.slice(0, MAX_REQUEST_ID_LENGTH) || requestId;
    }
    const request = validateRequest(rawMessage);
    requestId = request.request_id;
    const tab = await activeHttpsTab();
    const pageResponse = await chrome.tabs.sendMessage(tab.id, request);
    return { request_id: requestId, ...validatePageResponse(pageResponse) };
  } catch (error) {
    return {
      request_id: requestId,
      ok: false,
      error: error instanceof Error ? error.message : "Page bridge request failed"
    };
  }
}

function connectNativeHost() {
  if (nativePort) {
    return;
  }
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST_NAME);
    nativePort.onMessage.addListener((message) => {
      handleNativeMessage(message).then((response) => {
        if (nativePort) {
          nativePort.postMessage(response);
        }
      });
    });
    nativePort.onDisconnect.addListener(() => {
      nativePort = null;
      if (reconnectTimer === null) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null;
          connectNativeHost();
        }, 2000);
      }
    });
  } catch (_error) {
    nativePort = null;
  }
}

connectNativeHost();
