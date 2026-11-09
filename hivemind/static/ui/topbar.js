/* HiveMind top bar controller.
 *
 * Public API (window.HiveMindTopBar):
 *   init(root)                   - wire up one bar, or every .hm-topbar if
 *                                  called with no argument. Safe to call again
 *                                  after injecting markup; it never double-binds.
 *   setState("idle" | "active")  - switch the animation state
 *   activity(ms)                 - go active, then fall back to idle after ms
 *                                  (default 1400); repeated calls extend it
 *   getState()                   - current state
 *   setMotion(boolean)           - user-facing animation toggle; persisted
 *   getMotion()                  - whether motion is currently allowed
 *
 * The backend work can drive this without knowing anything about the art:
 * call activity() when a poll returns new reports, or setState("active")
 * around a longer running request.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "hivemind.motion";
  var bars = [];
  var state = "idle";
  var motion = true;
  var timer = null;

  function prefersReduced() {
    return !!(window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  function storedMotion() {
    try {
      var v = window.localStorage.getItem(STORAGE_KEY);
      if (v === "off") return false;
      if (v === "on") return true;
    } catch (e) { /* storage unavailable; fall back to the OS setting */ }
    return null;
  }

  function applyMotion() {
    bars.forEach(function (bar) {
      bar.classList.toggle("hm-still", !motion);
      bar.classList.toggle("hm-motion-on", motion);
      var toggle = bar.querySelector("[data-hm-motion]");
      if (toggle) {
        toggle.setAttribute("aria-pressed", motion ? "true" : "false");
        toggle.textContent = motion ? "Turn off animation" : "Turn on animation";
      }
    });
  }

  function applyState() {
    bars.forEach(function (bar) {
      bar.setAttribute("data-state", state);
      var status = bar.querySelector("[data-hm-status]");
      // Stated in words, so the state does not depend on colour or motion.
      if (status) {
        status.textContent = state === "active"
          ? "HiveMind is working"
          : "HiveMind is idle";
      }
    });
  }

  function setState(next) {
    if (next !== "idle" && next !== "active") return;
    // An explicit setState outranks a fallback scheduled by an earlier
    // activity() call: without this, a poll's pending timer could drop the bar
    // back to idle in the middle of a request that is still running.
    if (timer) { window.clearTimeout(timer); timer = null; }
    state = next;
    applyState();
  }

  function activity(ms) {
    setState("active");            // clears any fallback still pending
    timer = window.setTimeout(function () {
      timer = null;
      setState("idle");
    }, typeof ms === "number" ? ms : 1400);
  }

  /* --------------------------------------------------------- menu, per bar */
  function wireMenu(bar) {
    var button = bar.querySelector(".hm-menu-button");
    var menu = bar.querySelector(".hm-menu");
    if (!button || !menu) return;

    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");

    function items() {
      return Array.prototype.slice.call(
        menu.querySelectorAll("button:not([disabled]), a[href]"));
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
        return;
      }
      if (!menu.contains(document.activeElement)) return;
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      var list = items();
      if (!list.length) return;
      event.preventDefault();
      var i = list.indexOf(document.activeElement);
      var step = event.key === "ArrowDown" ? 1 : -1;
      list[(i + step + list.length) % list.length].focus();
    }

    function onPointerDown(event) {
      if (!menu.contains(event.target) && !button.contains(event.target)) close(false);
    }

    function open() {
      menu.hidden = false;
      button.setAttribute("aria-expanded", "true");
      var list = items();
      if (list.length) list[0].focus();
      document.addEventListener("keydown", onKeydown, true);
      document.addEventListener("pointerdown", onPointerDown, true);
    }

    function close(refocus) {
      if (menu.hidden) return;
      menu.hidden = true;
      button.setAttribute("aria-expanded", "false");
      document.removeEventListener("keydown", onKeydown, true);
      document.removeEventListener("pointerdown", onPointerDown, true);
      if (refocus) button.focus();
    }

    button.addEventListener("click", function () {
      if (menu.hidden) { open(); } else { close(true); }
    });

    bar.querySelector(".hm-menu-wrap").addEventListener("focusout", function (event) {
      if (event.relatedTarget && !menu.contains(event.relatedTarget) && !button.contains(event.relatedTarget)) {
        close(false);
      }
    });

    menu.addEventListener("click", function (event) {
      if (event.target.closest("[data-hm-motion]")) {
        api.setMotion(!motion);
        return;
      }
      if (event.target.closest("button, a[href]")) close(true);
    });
  }

  /* ------------------------------------------------------------- startup */
  function init(root) {
    var found = root
      ? (root.classList && root.classList.contains("hm-topbar")
          ? [root]
          : Array.prototype.slice.call(root.querySelectorAll(".hm-topbar")))
      : Array.prototype.slice.call(document.querySelectorAll(".hm-topbar"));

    found.forEach(function (bar) {
      if (bar.hmBound) return;          // never bind the same bar twice
      bar.hmBound = true;
      bars.push(bar);
      wireMenu(bar);
    });

    var stored = storedMotion();
    motion = stored === null ? !prefersReduced() : stored;
    applyMotion();
    applyState();
  }

  var api = {
    init: init,
    setState: setState,
    activity: activity,
    getState: function () { return state; },
    getMotion: function () { return motion; },
    setMotion: function (on) {
      motion = !!on;
      try {
        window.localStorage.setItem(STORAGE_KEY, motion ? "on" : "off");
      } catch (e) { /* non-fatal: the choice just will not persist */ }
      applyMotion();
    }
  };

  window.HiveMindTopBar = api;

  // Follow the OS setting while the user has not made an explicit choice.
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    var onChange = function () {
      if (storedMotion() === null) { motion = !mq.matches; applyMotion(); }
    };
    if (mq.addEventListener) { mq.addEventListener("change", onChange); }
    else if (mq.addListener) { mq.addListener(onChange); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { init(); });
  } else {
    init();
  }
})();
