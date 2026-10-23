"use strict";

/**
 * Search-result detection for "click the first link" on a results page.
 *
 * The first anchor on Google, Bing, or DuckDuckGo is a header or "skip" link,
 * so an ordinal over every link picks the wrong page. Organic results are the
 * headed links inside the results container, outside navigation and ads.
 */

const RESULT_CONTAINERS = "#search, #rso, #b_results, #links, [data-testid='mainline']";
const NOT_ORGANIC = "nav, header, footer, aside, #tads, #tadsb, [data-text-ad], .b_ad, .result--ad";

/**
 * Report whether an anchor is an organic search result.
 *
 * @param {{closest: Function, querySelector: Function}} anchor Link element.
 * @returns {boolean} True for a headed link in the results area that is not an ad.
 */
function isSearchResultLink(anchor) {
  if (!anchor.closest(RESULT_CONTAINERS) || anchor.closest(NOT_ORGANIC)) {
    return false;
  }
  return Boolean(anchor.querySelector("h2, h3") || anchor.closest("h2, h3"));
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { isSearchResultLink };
}
