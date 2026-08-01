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

// Workspace Section: fetch /api/workspace and render the discovered repos.
// Values arrive already redacted and home-relative; the only sensitive value
// on the page is each email's raw form, revealed on demand from repo.config.
(function () {
  "use strict";

  const mount = document.getElementById("workspace");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    const p = el("p", "ws-note", message);
    mount.replaceChildren(p);
  }

  function countChip(n, label) {
    // Stat-tile idiom (dataviz skill): the magnitude is the loud element, the
    // label stays recessive. No colour — that channel is reserved for M6 Flags.
    const chip = el("span", "ws-chip");
    chip.append(el("span", "num", String(n)), " ", el("span", "lbl", label));
    return chip;
  }

  function chips(repo) {
    const row = el("div", "ws-chips");
    if (repo.dirty) {
      const counts = [
        [repo.staged, "staged"],
        [repo.unstaged, "unstaged"],
        [repo.untracked, "untracked"],
        [repo.unmerged, "unmerged"],
      ];
      counts.forEach(function (pair) {
        if (pair[0] > 0) row.append(countChip(pair[0], pair[1]));
      });
    } else {
      row.append(el("span", "ws-chip ws-chip--muted", "clean"));
    }
    if (repo.stashes > 0) row.append(countChip(repo.stashes, "stash"));

    const pending = el("span", "ws-chip ws-chip--pending", "↕ ahead/behind pending");
    pending.title = "Computed after a background fetch, arriving over SSE in M2.";
    row.append(pending);
    return row;
  }

  function refLine(repo) {
    // The normal case (on a branch) is unadorned; the eyebrow is reserved to
    // mark the abnormal states so an odd HEAD reads at a glance.
    const line = el("div", "ws-ref");
    if (repo.branch) {
      line.append(el("span", "branch", repo.branch));
    } else if (repo.detached_sha) {
      line.append(el("span", "ws-eyebrow", "detached"), el("span", "branch", repo.detached_sha));
    } else {
      line.append(el("span", "ws-eyebrow", "no head"));
    }
    if (repo.upstream) line.append(el("span", "up", "→ " + repo.upstream));
    return line;
  }

  function configRow(entry) {
    const row = el("div", "ws-cfg-row");
    row.append(el("span", "ws-cfg-key", entry.key), el("span", "ws-cfg-scope", entry.scope));
    const value = el("span", "ws-cfg-val", entry.value);
    row.append(value);
    if (entry.raw) {
      const reveal = el("button", "ws-reveal", "reveal");
      reveal.type = "button";
      reveal.setAttribute("aria-label", "Reveal the full " + entry.key);
      let shown = false;
      reveal.addEventListener("click", function () {
        shown = !shown;
        value.textContent = shown ? entry.raw : entry.value;
        reveal.textContent = shown ? "hide" : "reveal";
      });
      row.append(reveal);
    }
    return row;
  }

  function configBlock(repo) {
    const details = el("details", "ws-config");
    details.append(el("summary", null, "git config"));
    const body = el("div", "ws-cfg");
    repo.config.forEach(function (entry) {
      body.append(configRow(entry));
    });
    details.append(body);
    return details;
  }

  function repoCard(repo) {
    const card = el("div", "ws-card");
    const head = el("div", "ws-head");
    head.append(
      el("span", "ws-dot " + (repo.dirty ? "ws-dot--dirty" : "ws-dot--clean")),
      el("span", "ws-name", repo.name),
      el("span", "ws-path", repo.path),
    );
    card.append(head, refLine(repo), chips(repo));
    if (repo.config.length > 0) card.append(configBlock(repo));
    return card;
  }

  function render(data) {
    const roots = data.roots.join(", ");
    if (data.repos.length === 0) {
      note("No git repositories found under " + roots + ".");
      return;
    }
    const summary = el("p", "ws-note");
    summary.append(
      el("span", "ws-count", String(data.repos.length)),
      data.repos.length === 1 ? " repository under " : " repositories under ",
      roots,
    );
    const grid = el("div", "ws-grid");
    data.repos.forEach(function (repo) {
      grid.append(repoCard(repo));
    });
    mount.replaceChildren(summary, grid);
  }

  fetch("/api/workspace")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load the workspace. Check that the board is still running.");
    });
})();
