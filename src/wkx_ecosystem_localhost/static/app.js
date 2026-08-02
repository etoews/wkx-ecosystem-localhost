// Board behaviour. Every Section leads with a one-line summary and lays its facts
// out in a table beneath. Colour is reserved for the M6 Flag layer: sections stamp
// a data-flag-key host cell and the flag layer badges it; neutral facts are told
// apart by weight, a muted tone, and a label, never by hue.

// ---------- theme control ----------
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

// ---------- shared table helpers ----------
// One small toolkit every Section builds its table from, so the markup stays
// consistent and safe (DOM nodes and textContent only, never innerHTML).
window.wkxUI = (function () {
  "use strict";

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function append(node, content) {
    if (content == null) return;
    if (typeof content === "string") node.append(document.createTextNode(content));
    else if (Array.isArray(content)) {
      content.forEach(function (c) {
        append(node, c);
      });
    } else {
      node.append(content);
    }
  }

  // A scrollable table from column specs ({label, num}); returns the wrapper to
  // mount and the empty tbody to append rows to.
  function table(columns) {
    const wrap = el("div", "tbl-wrap");
    const t = el("table");
    const thead = el("thead");
    const headRow = el("tr");
    columns.forEach(function (col) {
      headRow.append(el("th", col.num ? "num" : null, col.label));
    });
    thead.append(headRow);
    const tbody = el("tbody");
    t.append(thead, tbody);
    wrap.append(t);
    return { wrap: wrap, tbody: tbody };
  }

  function td(content, className) {
    const cell = el("td", className || null);
    append(cell, content);
    return cell;
  }

  function tr(cells) {
    const row = el("tr");
    cells.forEach(function (cell) {
      row.append(cell);
    });
    return row;
  }

  function ok(text) {
    return el("span", "ok", text);
  }
  function quiet(text) {
    return el("span", "q", text);
  }
  function dash() {
    return el("span", "dash", "—");
  }
  function strong(text) {
    const node = el("span", "t-name", text);
    node.style.fontWeight = "600";
    return node;
  }
  // A decorative level marker for the summary (never touched by the flag layer,
  // which only manages the .flag badges it places on rows).
  function level(lvl, text) {
    return el("span", "lvl lvl--" + (lvl === "problem" ? "problem" : "attention"), text);
  }

  function summaryLine(nodes) {
    const p = el("p", "sec-summary");
    nodes.forEach(function (n) {
      append(p, n);
    });
    return p;
  }

  return {
    el: el,
    append: append,
    table: table,
    td: td,
    tr: tr,
    ok: ok,
    quiet: quiet,
    dash: dash,
    strong: strong,
    level: level,
    summaryLine: summaryLine,
  };
})();

// ---------- Flag layer (M6) + needs-attention summary ----------
// The cross-cutting anomaly layer. It gathers no facts of its own — the server
// derives the at-rest Flags over /api/flags — but it owns the two places a Flag
// shows: an inline amber (attention) or red (problem) badge on the row carrying
// the fact, and the needs-attention summary that groups every open Flag by
// category. Every flaggable row stamps a data-flag-key of "<section>:<target>",
// so a Flag settles onto its row without this layer knowing how the row is drawn;
// a MutationObserver re-decorates as panels and SSE updates land. The summary
// reads the same registry, so at-rest and SSE-raised Flags share one source of
// truth and the summary updates the moment a background probe lands.
(function () {
  "use strict";

  const U = window.wkxUI;
  const board = document.querySelector(".board");
  const tally = document.getElementById("flag-tally");
  const summaryMount = document.getElementById("summary");
  if (!board || !tally) return;

  // The category each Flag code rolls up to in the summary.
  const CATEGORY = {
    "dirty-tree": "Dirty working trees",
    "detached-head": "Detached HEAD",
    "no-upstream": "No upstream",
    "behind-remote": "Behind remote",
    "brew-outdated": "Homebrew updates",
    "python-pin-drift": "Python pin drift",
    "tool-version-drift": "TypeScript version drift",
    "submodule-tags-behind": "Submodules behind",
    "docker-unreachable": "Docker daemon down",
    "tool-missing": "Missing tool",
    "skill-disabled": "Disabled skill",
    "plugin-disabled": "Disabled plugin",
    "skill-shadow": "Skill name shadowing",
    "mcp-needs-auth": "MCP needs auth",
    "mcp-two-scopes": "MCP in two scopes",
  };
  const TARGET_PREFIX = /^(formula|cask|pin|ts|skill|plugin|mcp):/;

  // Open Flags keyed by section|target|code, so a repeated add or an SSE re-fire
  // stays idempotent and the size is the true open count.
  const registry = new Map();
  let decorating = false;

  function el(tag, className, text) {
    return U.el(tag, className, text);
  }

  function keyOf(flag) {
    return flag.section + "|" + flag.target + "|" + flag.code;
  }

  function rowKey(flag) {
    return flag.section + ":" + flag.target;
  }

  function badge(flag) {
    const lvl = flag.level === "problem" ? "problem" : "attention";
    const node = el("span", "flag flag--" + lvl, flag.message);
    node.dataset.flagCode = flag.code;
    node.title = flag.message;
    // The level is spoken as well as coloured, so it never rests on hue alone.
    node.setAttribute("aria-label", lvl + ": " + flag.message);
    return node;
  }

  function updateTally() {
    let problems = 0;
    registry.forEach(function (flag) {
      if (flag.level === "problem") problems++;
    });
    const n = registry.size;
    tally.classList.toggle("tally--clear", n === 0);
    tally.classList.toggle("tally--problem", problems > 0);
    tally.classList.toggle("tally--attention", n > 0 && problems === 0);
    if (n === 0) {
      tally.textContent = "all clear";
    } else {
      tally.replaceChildren(
        el("span", "num", String(n)),
        document.createTextNode(" " + (n === 1 ? "wants attention" : "want attention")),
      );
    }
    tally.hidden = false;
  }

  function cleanTarget(target) {
    let value = String(target).replace(TARGET_PREFIX, "");
    if (value.indexOf("/") >= 0) value = value.split("/").pop();
    return value;
  }

  function tile(n, label, kind) {
    const cell = el("div", "tile" + (kind ? " tile--" + kind : ""));
    cell.append(el("div", "n", String(n)), el("div", "l", label));
    return cell;
  }

  // Render the needs-attention summary from the registry: three stat tiles over a
  // table of categories, each with a magnitude bar and a level marker. Called on
  // every registry change (the at-rest load and each SSE add/clear), never from
  // decorate(), so rebuilding the summary can't feed the observer a loop.
  function renderSummary() {
    if (!summaryMount) return;
    const flags = Array.from(registry.values());
    if (flags.length === 0) {
      summaryMount.replaceChildren(
        U.summaryLine(["Every Section is clear — nothing wants attention right now."]),
      );
      return;
    }

    const order = [];
    const groups = new Map();
    flags.forEach(function (flag) {
      const label = CATEGORY[flag.code] || flag.code;
      if (!groups.has(label)) {
        groups.set(label, { label: label, level: "attention", count: 0, targets: [] });
        order.push(label);
      }
      const group = groups.get(label);
      group.count++;
      if (flag.level === "problem") group.level = "problem";
      const clean = cleanTarget(flag.target);
      if (group.targets.indexOf(clean) < 0) group.targets.push(clean);
    });

    const cats = order.map(function (label) {
      return groups.get(label);
    });
    // Problems first, then by magnitude, so the sharpest items lead.
    cats.sort(function (a, b) {
      if (a.level !== b.level) return a.level === "problem" ? -1 : 1;
      return b.count - a.count;
    });

    const problems = flags.filter(function (f) {
      return f.level === "problem";
    }).length;
    const attention = flags.length - problems;
    const max = cats.reduce(function (m, c) {
      return Math.max(m, c.count);
    }, 1);

    const tiles = el("div", "tiles");
    tiles.append(
      tile(flags.length, "Total flags"),
      tile(attention, "Attention", "attention"),
      tile(problems, "Problems", "problem"),
    );

    const built = U.table([
      { label: "Category" },
      { label: "Level" },
      { label: "Count" },
      { label: "What wants attention" },
    ]);
    cats.forEach(function (cat) {
      const pct = Math.max(6, Math.round((cat.count / max) * 100));
      const bar = el("div", "cat-bar cat-bar--" + cat.level);
      const fill = el("span");
      fill.style.width = pct + "%";
      bar.append(fill);
      const barCell = el("div", "cat-bar-cell");
      barCell.append(el("span", "cat-count", String(cat.count)), bar);

      const shown =
        cat.targets.slice(0, 5).join(", ") +
        (cat.targets.length > 5 ? ", +" + (cat.targets.length - 5) + " more" : "");

      built.tbody.append(
        U.tr([
          U.td(el("span", "t-name", cat.label)),
          U.td(U.level(cat.level, cat.level)),
          U.td(barCell),
          U.td(shown, "q"),
        ]),
      );
    });

    const lead = U.summaryLine([
      "Every open flag, at rest and from the background probes, grouped by category. Level reads by shape and word first, colour second: a round dot is ",
      el("b", null, "attention"),
      ", a square is a ",
      el("b", null, "problem"),
      ".",
    ]);
    summaryMount.replaceChildren(lead, tiles, built.wrap);
  }

  function decorate() {
    // Guard re-entry: decorate mutates the board (adding/removing badges), which
    // the observer notices; because every pass is idempotent, the follow-up pass
    // finds nothing to change and the cycle settles at once.
    if (decorating) return;
    decorating = true;
    try {
      registry.forEach(function (flag) {
        const hosts = board.querySelectorAll('[data-flag-key="' + rowKey(flag) + '"]');
        hosts.forEach(function (host) {
          if (host.querySelector(':scope > .flag[data-flag-code="' + flag.code + '"]')) return;
          host.appendChild(badge(flag));
        });
      });
      board.querySelectorAll(".flag").forEach(function (node) {
        const host = node.closest("[data-flag-key]");
        if (!host) {
          node.remove();
          return;
        }
        const key = host.getAttribute("data-flag-key");
        const code = node.dataset.flagCode;
        let live = false;
        registry.forEach(function (flag) {
          if (rowKey(flag) === key && flag.code === code) live = true;
        });
        if (!live) node.remove();
      });
    } finally {
      decorating = false;
    }
    updateTally();
  }

  // Public API for the SSE-delivered Flags the server cannot know at rest.
  window.wkxFlags = {
    add: function (flag) {
      registry.set(keyOf(flag), flag);
      decorate();
      renderSummary();
    },
    clear: function (section, target, code) {
      registry.delete(section + "|" + target + "|" + code);
      decorate();
      renderSummary();
    },
  };

  // Re-decorate whenever a panel renders or an SSE update reshapes a row.
  new MutationObserver(decorate).observe(board, { childList: true, subtree: true });

  fetch("/api/flags")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      (data.flags || []).forEach(function (flag) {
        registry.set(keyOf(flag), flag);
      });
      decorate();
      renderSummary();
    })
    .catch(function () {
      if (summaryMount) {
        summaryMount.replaceChildren(
          U.summaryLine(["Could not derive the flags. Check that the board is still running."]),
        );
      }
    });
})();

// ---------- workspace (with submodules nested under their repo) ----------
// Fetch /api/workspace and /api/submodules, render the repos as a table with each
// submodule nested beneath its parent repo, then open the two SSE streams that
// fill ahead/behind and each submodule's latest release in as their background
// probes land. Values arrive already redacted and home-relative.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("workspace");
  if (!mount) return;

  const abCells = new Map(); // repo path -> {ahead, behind} cells filled over SSE
  const smRows = new Map(); // submodule path -> {latest, behind} cells filled over SSE

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function countChip(n, label) {
    const chip = U.el("span", "chip");
    chip.append(U.el("span", "num", String(n)), " ", U.el("span", "lbl", label));
    return chip;
  }

  function branchCell(repo) {
    if (repo.branch) return U.td(repo.branch);
    if (repo.detached_sha) return U.td([U.quiet("detached "), repo.detached_sha]);
    return U.td(U.quiet("no head"));
  }

  function workingTree(repo) {
    if (!repo.dirty) return U.quiet("clean");
    const chips = [];
    [
      [repo.staged, "staged"],
      [repo.unstaged, "unstaged"],
      [repo.untracked, "untracked"],
      [repo.unmerged, "unmerged"],
    ].forEach(function (pair) {
      if (pair[0] > 0) chips.push(countChip(pair[0], pair[1]));
    });
    return chips;
  }

  function repoRow(repo) {
    const flags = U.td("", "flags-cell");
    flags.dataset.flagKey = "workspace:" + repo.path;
    const ahead = U.td(U.quiet("···"), "num");
    const behind = U.td(U.quiet("···"), "num");
    abCells.set(repo.path, { ahead: ahead, behind: behind });
    return U.tr([
      U.td(U.el("span", "t-name", repo.name)),
      branchCell(repo),
      U.td(repo.upstream ? U.el("span", "q", repo.upstream) : U.dash()),
      ahead,
      behind,
      U.td(workingTree(repo)),
      U.td(repo.stashes > 0 ? String(repo.stashes) : U.quiet("0"), "num"),
      flags,
    ]);
  }

  function subRow(sub) {
    const name = U.td("", "sub-lead");
    name.textContent = sub.name;

    const pin = U.el("td");
    pin.colSpan = 2;
    pin.append(U.el("span", "q", "submodule · pinned "), U.el("span", "ver", sub.pinned || "—"));

    const latest = U.el("td");
    latest.colSpan = 2;
    latest.append(U.el("span", "q", "latest "), U.quiet("listing…"));

    const behind = U.el("td");
    behind.colSpan = 2;
    behind.append(U.dash());

    const flags = U.el("td", "flags-cell");
    flags.dataset.flagKey = "submodules:" + sub.path;

    smRows.set(sub.path, { latest: latest, behind: behind });

    const row = U.el("tr", "subrow");
    row.append(name, pin, latest, behind, flags);
    return row;
  }

  // ---- ahead/behind stream ----
  function raiseBehind(repo, behind) {
    if (!window.wkxFlags) return;
    if (behind > 0) {
      window.wkxFlags.add({
        section: "workspace",
        target: repo,
        level: "attention",
        code: "behind-remote",
        message: behind === 1 ? "1 commit behind remote" : behind + " commits behind remote",
      });
    } else {
      window.wkxFlags.clear("workspace", repo, "behind-remote");
    }
  }

  function fillAheadBehind(event) {
    const cells = abCells.get(event.repo);
    if (!cells) return;
    cells.ahead.classList.add("filled");
    cells.behind.classList.add("filled");
    if (event.unknown) {
      cells.ahead.replaceChildren(U.dash());
      cells.behind.replaceChildren(U.quiet("unknown"));
      cells.behind.title = "The background fetch could not reach the remote; it may need credentials.";
      raiseBehind(event.repo, 0);
      return;
    }
    if (event.ahead == null && event.behind == null) {
      cells.ahead.replaceChildren(U.dash());
      cells.behind.replaceChildren(U.dash());
      cells.behind.title = "This branch has no upstream to compare against.";
      raiseBehind(event.repo, 0);
      return;
    }
    raiseBehind(event.repo, event.behind);
    cells.ahead.replaceChildren(document.createTextNode(String(event.ahead)));
    if (event.behind > 0) {
      const strong = U.el("span");
      strong.style.fontWeight = "600";
      strong.textContent = String(event.behind);
      cells.behind.replaceChildren(strong);
    } else {
      cells.behind.replaceChildren(document.createTextNode("0"));
    }
    cells.behind.title = "Commits behind the upstream, since the last background fetch.";
  }

  // ---- submodule probe stream ----
  function raiseSubBehind(path, behind) {
    if (!window.wkxFlags) return;
    if (behind > 0) {
      window.wkxFlags.add({
        section: "submodules",
        target: path,
        level: "attention",
        code: "submodule-tags-behind",
        message: behind === 1 ? "1 release behind" : behind + " releases behind",
      });
    } else {
      window.wkxFlags.clear("submodules", path, "submodule-tags-behind");
    }
  }

  function setLatest(cell, value, muted, title) {
    cell.replaceChildren(U.el("span", "q", "latest "), muted ? U.quiet(value) : U.el("span", "ver", value));
    if (title) cell.title = title;
  }

  function fillSubmodule(event) {
    const row = smRows.get(event.submodule);
    if (!row) return;
    row.latest.classList.add("filled");
    if (event.unknown) {
      setLatest(row.latest, "listing unknown", true, "The remote tags could not be listed; it may need credentials.");
      row.behind.replaceChildren(U.dash());
      raiseSubBehind(event.submodule, 0);
      return;
    }
    if (event.latest == null) {
      setLatest(row.latest, "no releases", true, "The remote lists no version tags.");
      row.behind.replaceChildren(U.dash());
      raiseSubBehind(event.submodule, 0);
      return;
    }
    setLatest(row.latest, event.latest, false, "The highest stable release the remote lists.");
    if (event.behind == null) {
      row.behind.replaceChildren(U.quiet("untagged pin"));
      raiseSubBehind(event.submodule, 0);
      return;
    }
    raiseSubBehind(event.submodule, event.behind);
    if (event.behind === 0) {
      row.behind.replaceChildren(U.quiet("on latest"));
    } else {
      const strong = U.el("span");
      strong.style.fontWeight = "600";
      strong.textContent = event.behind === 1 ? "1 release behind" : event.behind + " releases behind";
      row.behind.replaceChildren(strong);
    }
  }

  function startStream(url, onMessage) {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(url);
    source.addEventListener("message", function (message) {
      try {
        onMessage(JSON.parse(message.data));
      } catch (_err) {
        // Ignore a stray or malformed frame rather than tearing down the stream.
      }
    });
    source.addEventListener("done", function () {
      source.close();
    });
    source.addEventListener("error", function () {
      source.close();
    });
  }

  function render(workspace, submodules) {
    const roots = workspace.roots.join(", ");
    if (workspace.repos.length === 0) {
      note("No git repositories found under " + roots + ".");
      return;
    }
    abCells.clear();
    smRows.clear();

    const subsByRepo = new Map();
    (submodules.submodules || []).forEach(function (sub) {
      if (!subsByRepo.has(sub.repo)) subsByRepo.set(sub.repo, []);
      subsByRepo.get(sub.repo).push(sub);
    });

    const dirty = workspace.repos.filter(function (r) {
      return r.dirty;
    }).length;
    const noUpstream = workspace.repos.filter(function (r) {
      return r.branch && !r.upstream;
    }).length;
    const subCount = (submodules.submodules || []).length;

    const summary = U.summaryLine([
      "Every git repo discovered under ",
      U.el("b", null, roots),
      ", with working-tree state and ahead/behind since the last background fetch. ",
      U.el("b", null, String(dirty)),
      dirty === 1 ? " dirty, " : " dirty, ",
      U.el("b", null, String(noUpstream)),
      " without an upstream. Submodules (",
      U.el("b", null, String(subCount)),
      ") sit nested beneath their repo, versioned as pinned · latest · releases-behind.",
    ]);

    const built = U.table([
      { label: "Repo" },
      { label: "Branch" },
      { label: "Upstream" },
      { label: "Ahead", num: true },
      { label: "Behind", num: true },
      { label: "Working tree" },
      { label: "Stash", num: true },
      { label: "Flags" },
    ]);
    workspace.repos.forEach(function (repo) {
      built.tbody.append(repoRow(repo));
      (subsByRepo.get(repo.path) || []).forEach(function (sub) {
        built.tbody.append(subRow(sub));
      });
    });

    mount.replaceChildren(summary, built.wrap);
    startStream("/api/workspace/fetch", fillAheadBehind);
    startStream("/api/submodules/probe", fillSubmodule);
  }

  Promise.all([
    fetch("/api/workspace").then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    fetch("/api/submodules")
      .then(function (r) {
        return r.ok ? r.json() : { submodules: [] };
      })
      .catch(function () {
        return { submodules: [] };
      }),
  ])
    .then(function (results) {
      render(results[0], results[1]);
    })
    .catch(function () {
      note("Could not load the workspace. Check that the board is still running.");
    });
})();

// ---------- toolchains ----------
// Fetch /api/toolchains and render the Python and Node/TypeScript facts as a set
// of small tables. Facts only: drift reads by weight, and an absent tool reads as
// a plain "absent" fact. The pin and TypeScript rows stamp a flag host so the M6
// drift badges land on them.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("toolchains");
  if (!mount) return;

  function base(path) {
    return String(path).split("/").pop();
  }

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function toolState(tool) {
    return tool.present ? U.ok(tool.version || "present") : U.quiet("absent");
  }

  function subHead(text) {
    return U.el("p", "sub-head", text);
  }

  function interpreterTable(python) {
    const built = U.table([{ label: "Version" }, { label: "Implementation" }, { label: "State" }]);
    python.interpreters.forEach(function (interp) {
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name ver", interp.version)),
          U.td(interp.implementation, "q"),
          U.td(interp.installed ? U.ok("installed") : U.quiet("available")),
        ]),
      );
    });
    return built.wrap;
  }

  function pinTable(python) {
    const built = U.table([{ label: "Repo" }, { label: "Pin" }, { label: "Against global" }, { label: "Flags" }]);
    python.repo_pins.forEach(function (pin) {
      const flags = U.td("", "flags-cell");
      flags.dataset.flagKey = "toolchains:pin:" + pin.repo;
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", base(pin.repo))),
          U.td(U.el("span", "ver", pin.version)),
          U.td(pin.version === python.global_pin ? U.quiet("matches global") : U.quiet("differs")),
          flags,
        ]),
      );
    });
    return built.wrap;
  }

  function nodeToolTable(node) {
    const built = U.table([{ label: "Tool" }, { label: "Version" }, { label: "State" }]);
    const rows = [
      ["node", node.node],
      ["npm", node.npm],
      ["tsc", node.tsc],
    ].concat(
      node.package_managers.map(function (pm) {
        return [pm.name, pm];
      }),
    );
    rows.forEach(function (pair) {
      const tool = pair[1];
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", pair[0])),
          U.td(tool.version ? U.el("span", "ver", tool.version) : U.dash()),
          U.td(toolState(tool)),
        ]),
      );
    });
    return built.wrap;
  }

  function tsTable(node) {
    const built = U.table([{ label: "Repo" }, { label: "Declared" }, { label: "Installed" }, { label: "Flags" }]);
    node.repos.forEach(function (repo) {
      const flags = U.td("", "flags-cell");
      flags.dataset.flagKey = "toolchains:ts:" + repo.repo;
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", base(repo.repo))),
          U.td(repo.declared ? U.el("span", "ver", repo.declared) : U.dash()),
          U.td(repo.installed ? U.el("span", "ver", repo.installed) : U.quiet("not installed")),
          flags,
        ]),
      );
    });
    return built.wrap;
  }

  function render(data) {
    const py = data.python;
    const node = data.node;
    const nodes = [
      U.summaryLine([
        "The language story in one place. uv manages ",
        U.el("b", null, String(py.interpreters.length)),
        " interpreters; the global pin is ",
        U.el("b", null, py.global_pin || "unset"),
        " and system python3 is ",
        U.el("b", null, py.system.version || "absent"),
        ". Node is ",
        U.el("b", null, node.node.present ? node.node.version : "absent"),
        "; global tsc is ",
        U.el("b", null, node.tsc.present ? node.tsc.version : "absent"),
        ".",
      ]),
      subHead("Python · interpreters (uv-managed)"),
      interpreterTable(py),
    ];
    if (py.repo_pins.length > 0) {
      nodes.push(subHead("Python · per-repo pins (global " + (py.global_pin || "unset") + ")"), pinTable(py));
    }
    nodes.push(subHead("Node · global tools"), nodeToolTable(node));
    if (node.repos.length > 0) {
      nodes.push(subHead("TypeScript · per repo (declared vs installed)"), tsTable(node));
    }
    mount.replaceChildren.apply(mount, nodes);
  }

  fetch("/api/toolchains")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load toolchains. Check that the board is still running.");
    });
})();

// ---------- claude ----------
// Fetch /api/claude and render three tables: plugins with the skills they ship
// nested beneath each one; the independent (user- or project-authored) skills
// standing alone; and the MCP servers. Every plugin is shown, enabled or not.
// Values carry no secrets: an MCP server is a name, an Origin, a transport, and an
// auth flag only.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("claude");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function subHead(text) {
    return U.el("p", "sub-head", text);
  }

  function isIndependent(skill) {
    return skill.origin.indexOf("@") < 0; // user or project, never a <plugin>@<market> pair
  }

  function pluginTable(plugins, skillsByOrigin) {
    const built = U.table([
      { label: "Plugin" },
      { label: "Marketplace" },
      { label: "Repo" },
      { label: "Version" },
      { label: "State" },
      { label: "Skills", num: true },
    ]);
    plugins.forEach(function (plugin) {
      const key = plugin.name + "@" + plugin.marketplace;
      const skills = skillsByOrigin.get(key) || [];

      const state = U.td("", "flags-cell");
      state.dataset.flagKey = "claude:plugin:" + plugin.name;
      state.append(U.quiet(plugin.enabled ? "enabled" : "disabled"));

      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", plugin.name)),
          U.td(plugin.marketplace, "q"),
          U.td(plugin.repo ? plugin.repo : U.dash(), "q"),
          U.td(plugin.version === "unknown" ? U.quiet("unknown") : U.el("span", "ver", plugin.version)),
          state,
          U.td(skills.length > 0 ? String(skills.length) : U.quiet("—"), "num"),
        ]),
      );

      if (skills.length > 0) {
        const wrap = U.el("div", "skill-wrap");
        wrap.append(U.el("span", "k-lead", skills.length + " skills"));
        skills.forEach(function (skill) {
          const chip = U.el("span", "chip", skill.name);
          // A skill can still be flagged (disabled, or shadowing another origin).
          chip.dataset.flagKey = "claude:skill:" + skill.name;
          if (skill.description) chip.title = skill.description;
          wrap.append(chip);
        });
        const cell = U.el("td");
        cell.colSpan = 6;
        cell.append(wrap);
        const row = U.el("tr", "skillrow");
        row.append(cell);
        built.tbody.append(row);
      }
    });
    return built.wrap;
  }

  function skillTable(skills) {
    const built = U.table([
      { label: "Skill" },
      { label: "Origin" },
      { label: "State" },
      { label: "Source" },
      { label: "Description" },
    ]);
    skills.forEach(function (skill) {
      const state = U.td("", "flags-cell");
      state.dataset.flagKey = "claude:skill:" + skill.name;
      state.append(U.quiet(skill.enabled ? "enabled" : "disabled"));

      const desc = skill.description ? U.el("div", "clamp2", skill.description) : U.dash();
      if (skill.description) desc.title = skill.description;

      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", skill.name)),
          U.td(skill.origin, "q"),
          state,
          U.td(skill.origin === "user" ? "~/.claude/skills" : skill.origin, "q"),
          U.td(desc),
        ]),
      );
    });
    return built.wrap;
  }

  function mcpTable(servers) {
    const built = U.table([{ label: "Server" }, { label: "Origin" }, { label: "Transport" }, { label: "Auth" }]);
    servers.forEach(function (server) {
      const auth = U.td("", "flags-cell");
      auth.dataset.flagKey = "claude:mcp:" + server.name;
      auth.append(U.quiet(server.needs_auth ? "needs auth" : "ready"));
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", server.name)),
          U.td(server.origin, "q"),
          U.td(server.transport, "q"),
          auth,
        ]),
      );
    });
    return built.wrap;
  }

  function render(data) {
    const skills = data.skills || [];
    const plugins = data.plugins || [];
    const servers = data.mcp_servers || [];
    if (skills.length === 0 && plugins.length === 0 && servers.length === 0) {
      note("No Claude skills, plugins, or MCP servers found.");
      return;
    }

    const skillsByOrigin = new Map();
    skills.forEach(function (skill) {
      if (!skillsByOrigin.has(skill.origin)) skillsByOrigin.set(skill.origin, []);
      skillsByOrigin.get(skill.origin).push(skill);
    });
    const independent = skills.filter(isIndependent);
    const pluginSkillCount = skills.length - independent.length;

    const nodes = [
      U.summaryLine([
        "Skills that ship with a plugin belong to it, so they are nested beneath it (",
        U.el("b", null, String(pluginSkillCount)),
        " across ",
        U.el("b", null, String(plugins.length)),
        " plugins). Only ",
        U.el("b", null, "independent"),
        " skills, your own, stand alone in their own table. Origin answers where each asset came from.",
      ]),
      subHead("Plugins (with their skills nested)"),
      pluginTable(plugins, skillsByOrigin),
    ];
    if (independent.length > 0) {
      nodes.push(subHead("Independent skills (" + independent.length + ", your own)"), skillTable(independent));
    } else {
      nodes.push(subHead("Independent skills"), U.summaryLine(["No standalone user or project skills."]));
    }
    nodes.push(subHead("MCP servers (" + servers.length + ")"));
    nodes.push(servers.length > 0 ? mcpTable(servers) : U.summaryLine(["No MCP servers configured."]));

    mount.replaceChildren.apply(mount, nodes);
  }

  fetch("/api/claude")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load the Claude environment. Check that the board is still running.");
    });
})();

// ---------- system ----------
// Fetch /api/system and render each configured developer CLI as present-with-
// version or missing. A missing tool reads as "—" plus the M6 "not installed"
// badge in its flag host; a present one shows its version.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("system");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function render(data) {
    const tools = data.tools || [];
    if (tools.length === 0) {
      note("No developer tools are configured to probe.");
      return;
    }
    const present = tools.filter(function (tool) {
      return tool.present && tool.version;
    }).length;

    const summary = U.summaryLine([
      "The configured developer CLIs, each a bare present-or-missing fact with its version. ",
      U.el("b", null, String(present)),
      " of ",
      U.el("b", null, String(tools.length)),
      " present.",
    ]);

    const built = U.table([{ label: "Tool" }, { label: "Version" }, { label: "Flags" }]);
    tools.forEach(function (tool) {
      const flags = U.td("", "flags-cell");
      flags.dataset.flagKey = "system:" + tool.name;
      const version = tool.present && tool.version ? U.el("span", "ver", tool.version) : U.dash();
      built.tbody.append(U.tr([U.td(U.el("span", "t-name", tool.name)), U.td(version), flags]));
    });

    mount.replaceChildren(summary, built.wrap);
  }

  fetch("/api/system")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load system tools. Check that the board is still running.");
    });
})();

// ---------- homebrew ----------
// Fetch /api/homebrew and render the outdated formulae (and casks, when any) as a
// table of installed → current bumps. Each row stamps a flag host so the M6
// "update available" badge lands on it; Homebrew's absence is a plain fact.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("homebrew");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function bump(pkg) {
    const span = U.el("span", "bump");
    span.append(
      U.el("span", "from", pkg.installed || "—"),
      U.el("span", "arr", "→"),
      U.el("span", "to", pkg.current || "—"),
    );
    return span;
  }

  function pkgTable(kind, packages) {
    const built = U.table([{ label: "Package" }, { label: "Installed → current" }, { label: "Flags" }]);
    packages.forEach(function (pkg) {
      const flags = U.td("", "flags-cell");
      flags.dataset.flagKey = "homebrew:" + kind + ":" + pkg.name;
      built.tbody.append(U.tr([U.td(U.el("span", "t-name", pkg.name)), U.td(bump(pkg)), flags]));
    });
    return built.wrap;
  }

  function render(data) {
    if (!data.present) {
      note("Homebrew is not installed on this machine.");
      return;
    }
    const formulae = data.formulae || [];
    const casks = data.casks || [];
    const total = formulae.length + casks.length;
    if (total === 0) {
      note("Every formula and cask is current.");
      return;
    }
    const summary = U.summaryLine([
      "Packages a brew upgrade would move forward: ",
      U.el("b", null, String(formulae.length)),
      " formulae, ",
      U.el("b", null, String(casks.length)),
      " casks. The version it would land on is bold, the one installed now recessive.",
    ]);
    const nodes = [summary];
    if (formulae.length > 0) {
      nodes.push(U.el("p", "sub-head", "Formulae (" + formulae.length + ")"), pkgTable("formula", formulae));
    }
    if (casks.length > 0) {
      nodes.push(U.el("p", "sub-head", "Casks (" + casks.length + ")"), pkgTable("cask", casks));
    }
    mount.replaceChildren.apply(mount, nodes);
  }

  fetch("/api/homebrew")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load Homebrew. Check that the board is still running.");
    });
})();

// ---------- docker ----------
// Fetch /api/docker and render the daemon state with its container, image, and
// reclaimable-disk facts in one row. A daemon that cannot be reached is a fact,
// not an error: the daemon cell hosts the M6 "daemon unreachable" badge and the
// counts are withheld rather than shown as meaningless zeros.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("docker");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function render(data) {
    const reachable = data.daemon_reachable;
    const summary = U.summaryLine([
      "The Docker daemon and a few read-only disk-and-container facts. A daemon that cannot be reached renders as a fact, never an error.",
    ]);

    const built = U.table([
      { label: "Daemon" },
      { label: "Containers", num: true },
      { label: "Images", num: true },
      { label: "Reclaimable", num: true },
    ]);
    const daemon = U.td("", "flags-cell");
    daemon.dataset.flagKey = "docker:daemon";
    daemon.append(U.quiet(reachable ? "reachable" : "unreachable"));

    if (reachable) {
      built.tbody.append(
        U.tr([
          daemon,
          U.td(data.containers_running + " / " + data.containers_total, "num"),
          U.td(String(data.images), "num"),
          U.td(data.reclaimable != null ? data.reclaimable : U.quiet("unknown"), "num"),
        ]),
      );
    } else {
      built.tbody.append(U.tr([daemon, U.td(U.dash(), "num"), U.td(U.dash(), "num"), U.td(U.dash(), "num")]));
    }

    mount.replaceChildren(summary, built.wrap);
  }

  fetch("/api/docker")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load Docker. Check that the board is still running.");
    });
})();
