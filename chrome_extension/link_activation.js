"use strict";

/**
 * Decide how to follow an anchor after its click listeners run.
 *
 * A content-script click is not a trusted user gesture, so Chrome will not
 * navigate the link on its own. The caller should navigate only when the page
 * did not cancel the click. javascript: and download links are left alone.
 *
 * @param {{href?: string, target?: string | null, download?: boolean} | null} link
 * @returns {"assign" | "blank" | "skip"}
 */
function decideLinkActivation(link) {
  if (!link || typeof link.href !== "string" || link.href.length === 0) {
    return "skip";
  }
  let url;
  try {
    url = new URL(link.href);
  } catch (_error) {
    return "skip";
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return "skip";
  }
  if (link.download) {
    return "skip";
  }
  if (String(link.target || "").toLowerCase() === "_blank") {
    return "blank";
  }
  return "assign";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { decideLinkActivation };
}
