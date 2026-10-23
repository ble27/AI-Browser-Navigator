"use strict";

/**
 * Search-result detection for "click the first link" on a results page.
 *
 * The first anchor on Google, Bing, or DuckDuckGo is a header or "skip" link,
 * so an ordinal over every link picks the wrong page. Organic results are the
 * headed links inside the results container, outside navigation and ads.
 */

const RESULT_CONTAINERS =
  "#search, #rso, #res, #center_col, #b_results, #links, [data-testid='mainline']";
const NOT_ORGANIC =
  "nav, header, footer, aside, #tads, #tadsb, [data-text-ad], [data-initq], g-accordion-expander, .b_ad, .result--ad";

/**
 * Return whether an href points back to a search-engine results or hash URL.
 *
 * @param {string | undefined} href Candidate anchor URL.
 * @returns {boolean} True when the link is internal search navigation.
 */
function isInternalSearchUrl(href) {
  if (typeof href !== "string" || href.length === 0) {
    return false;
  }
  if (href.startsWith("#")) {
    return true;
  }
  try {
    const parsed = new URL(href);
    const host = parsed.hostname.toLowerCase();
    if (
      (host === "google.com" ||
        host.endsWith(".google.com") ||
        host === "bing.com" ||
        host.endsWith(".bing.com")) &&
      parsed.pathname.startsWith("/search")
    ) {
      return true;
    }
  } catch (_error) {
    return false;
  }
  return false;
}

/**
 * Report whether an anchor is an organic search result.
 *
 * @param {{closest: Function, querySelector: Function, href?: string}} anchor Link element.
 * @returns {boolean} True for a headed link in the results area that is not an ad.
 */
function isSearchResultLink(anchor) {
  if (!anchor.closest(RESULT_CONTAINERS) || anchor.closest(NOT_ORGANIC)) {
    return false;
  }
  if (isInternalSearchUrl(anchor.href)) {
    return false;
  }
  return Boolean(anchor.querySelector("h2, h3") || anchor.closest("h2, h3"));
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { isSearchResultLink };
}
