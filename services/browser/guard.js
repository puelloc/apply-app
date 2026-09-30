/* Submit guard: injected into every page (as a Playwright init script) to block all form
 * submissions at the page level. Blocks submit events, Enter-key submits, and
 * form.submit()/requestSubmit(). The agent reads window.__submitGuard to detect a blocked attempt
 * and log `submit_guard_blocked`. Covers adapters and workflow replays because it is injected per
 * context, before any page script runs.
 */
(function () {
  "use strict";
  if (window.__submitGuard) return;
  var state = window.__submitGuard = { blocked: 0, reasons: [] };

  function record(reason) {
    state.blocked += 1;
    state.reasons.push(reason);
    document.documentElement.setAttribute("data-submit-guard-blocked", String(state.blocked));
  }

  // 1. submit events (click on a submit button, requestSubmit, Enter in a single-input form)
  document.addEventListener("submit", function (e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    record("submit-event");
  }, true);

  // 2. Enter key inside a form input
  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target && e.target.form) {
      e.preventDefault();
      record("enter-key");
    }
  }, true);

  // 3. form.submit() / form.requestSubmit() — neutralize the prototype so JS submits no-op
  function neutralize(proto, name) {
    proto[name] = function () { record(name); };
  }
  neutralize(HTMLFormElement.prototype, "submit");
  if (HTMLFormElement.prototype.requestSubmit) {
    neutralize(HTMLFormElement.prototype, "requestSubmit");
  }
})();
