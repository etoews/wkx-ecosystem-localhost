// Board behaviour. M0: theme control only; Section fetches arrive with M1.

(function () {
  "use strict";

  const KEY = "wkx-theme";
  const MODES = ["auto", "light", "dark"];
  const button = document.getElementById("theme-toggle");

  function current() {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "auto";
  }

  function apply(mode) {
    if (mode === "auto") {
      delete document.documentElement.dataset.theme;
      localStorage.removeItem(KEY);
    } else {
      document.documentElement.dataset.theme = mode;
      localStorage.setItem(KEY, mode);
    }
    button.textContent = "theme: " + mode;
  }

  button.addEventListener("click", function () {
    const next = MODES[(MODES.indexOf(current()) + 1) % MODES.length];
    apply(next);
  });

  button.textContent = "theme: " + current();
})();
