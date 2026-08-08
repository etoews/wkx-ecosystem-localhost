// Board behaviour. Every Section leads with a one-line summary and lays its facts
// out in a sortable table beneath. Colour is reserved for the M6 Flag layer:
// sections stamp a data-flag-key host element and the flag layer badges it; neutral
// facts are told apart by weight, a muted tone, and a label, never by hue.

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
// consistent and safe (DOM nodes and textContent only, never innerHTML). Every
// table is sortable: clicking a header (or Enter/Space) sorts by that column,
// toggling ascending/descending. Sorting is group-aware, so a nested sub-row
// (a submodule beneath its repo) travels with its parent.
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

  function isChildRow(row) {
    return row.classList.contains("subrow") || row.classList.contains("skillrow");
  }

  // Group the tbody into [parent, ...children] runs so a sort keeps children
  // attached to the parent row they belong to.
  function groupsOf(tbody) {
    const groups = [];
    Array.prototype.forEach.call(tbody.rows, function (row) {
      if (isChildRow(row) && groups.length) {
        groups[groups.length - 1].push(row);
      } else {
        groups.push([row]);
      }
    });
    return groups;
  }

  function sortValue(group, index) {
    const cell = group[0].cells[index];
    if (!cell) return "";
    return (cell.getAttribute("data-sort") || cell.textContent || "").trim();
  }

  const NON_NUMERIC = /^(—|···|…|)$/;

  function sortTable(table, index, th) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const groups = groupsOf(tbody);
    const values = groups.map(function (g) {
      return sortValue(g, index);
    });
    const numeric =
      values.some(function (v) {
        return !NON_NUMERIC.test(v) && !isNaN(parseFloat(v));
      }) &&
      values.every(function (v) {
        return NON_NUMERIC.test(v) || !isNaN(parseFloat(v));
      });

    const dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (head) {
      head.removeAttribute("aria-sort");
      head.classList.remove("sort-asc", "sort-desc");
    });
    th.setAttribute("aria-sort", dir);
    th.classList.add(dir === "ascending" ? "sort-asc" : "sort-desc");
    const sign = dir === "ascending" ? 1 : -1;

    groups.sort(function (a, b) {
      const va = sortValue(a, index);
      const vb = sortValue(b, index);
      let cmp;
      if (numeric) {
        // Blanks and placeholders sort to the end regardless of direction.
        const na = NON_NUMERIC.test(va) ? null : parseFloat(va);
        const nb = NON_NUMERIC.test(vb) ? null : parseFloat(vb);
        if (na === null && nb === null) cmp = 0;
        else if (na === null) return 1;
        else if (nb === null) return -1;
        else cmp = na - nb;
      } else {
        cmp = va.localeCompare(vb, undefined, { numeric: true, sensitivity: "base" });
      }
      return cmp * sign;
    });

    const frag = document.createDocumentFragment();
    groups.forEach(function (group) {
      group.forEach(function (row) {
        frag.appendChild(row);
      });
    });
    tbody.appendChild(frag);
  }

  function makeSortable(table) {
    const headRow = table.tHead && table.tHead.rows[0];
    if (!headRow) return;
    Array.prototype.forEach.call(headRow.cells, function (th, index) {
      th.classList.add("sortable");
      th.setAttribute("role", "button");
      th.tabIndex = 0;
      th.title = "Sort by " + (th.textContent || "column").trim();
      th.addEventListener("click", function () {
        sortTable(table, index, th);
      });
      th.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          sortTable(table, index, th);
        }
      });
    });
  }

  // Build a scrollable, sortable table from column specs ({label, num, width}).
  // When any column carries a width, the table lays out fixed with a colgroup so
  // sibling tables that share the same spec align column-for-column.
  function table(columns) {
    const wrap = el("div", "tbl-wrap");
    const t = el("table");
    if (columns.some(function (c) { return c.width; })) {
      t.style.tableLayout = "fixed";
      const colgroup = document.createElement("colgroup");
      columns.forEach(function (c) {
        const col = document.createElement("col");
        if (c.width) col.style.width = c.width;
        colgroup.appendChild(col);
      });
      t.appendChild(colgroup);
    }
    const thead = el("thead");
    const headRow = el("tr");
    columns.forEach(function (col) {
      headRow.append(el("th", col.num ? "num" : null, col.label));
    });
    thead.append(headRow);
    const tbody = el("tbody");
    t.append(thead, tbody);
    wrap.append(t);
    makeSortable(t);
    return { wrap: wrap, tbody: tbody };
  }

  function td(content, className) {
    const cell = el("td", className || null);
    append(cell, content);
    return cell;
  }

  // The in-cell flex line: chips or badges laid out with a shared gap INSIDE a
  // cell. The flex lives on this inner span, never on the td itself — a td
  // displayed as anything but table-cell falls out of the table model: its row
  // border floats at content height, colSpan is ignored, and its content
  // pollutes column sizing (tests/test_static_assets.py holds this line).
  function cellFlex(content) {
    const line = el("span", "cell-flex");
    append(line, content);
    return line;
  }

  // A td that hosts M6 flag badges. The flag key rides on the inner flex line,
  // so a landing badge joins the cell's content with the shared gap and the td
  // stays a plain table cell.
  function flagsTd(content, flagKey, className) {
    const host = cellFlex(content);
    host.dataset.flagKey = flagKey;
    return td(host, className);
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

  // A stat tile: a big value over a small label. opts.kind tints the value
  // (attention/problem); opts.flagKey makes the tile a flag host.
  function tile(value, label, opts) {
    opts = opts || {};
    const cell = el("div", "tile" + (opts.kind ? " tile--" + opts.kind : ""));
    const n = el("div", "n");
    append(n, value);
    cell.append(n, el("div", "l", label));
    if (opts.flagKey) cell.dataset.flagKey = opts.flagKey;
    return cell;
  }

  // A Section's summary: a wrapping row of tiles from [{value, label, kind?, flagKey?}].
  function tiles(specs) {
    const wrap = el("div", "tiles");
    specs.forEach(function (spec) {
      wrap.append(tile(spec.value, spec.label, spec));
    });
    return wrap;
  }

  return {
    el: el,
    append: append,
    table: table,
    td: td,
    cellFlex: cellFlex,
    flagsTd: flagsTd,
    tr: tr,
    ok: ok,
    quiet: quiet,
    dash: dash,
    level: level,
    summaryLine: summaryLine,
    tile: tile,
    tiles: tiles,
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
window.wkxFlags = (function () {
  "use strict";

  const U = window.wkxUI;
  const board = document.querySelector(".board");
  const summaryMount = document.getElementById("summary");
  if (!board) return { add: function () {}, clear: function () {} };

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
    "git-config-conflict": "Conflicting git config",
    "git-include-broken": "Broken git include",
    "git-config-credentials": "Credentials in git config",
    "git-no-identity": "No git identity",
  };
  // How to resolve each anomaly — the tooltip a badge carries, so hovering tells
  // you what to do about it rather than restating what it already says.
  const RESOLUTION = {
    "dirty-tree": "Commit or stash the changes: git add -A && git commit, or git stash.",
    "detached-head": "Get back on a branch: git switch <branch>, or git switch -c <new> to keep this work.",
    "no-upstream": "Publish and track the branch: git push -u origin <branch>.",
    "behind-remote": "Catch up to the remote: git pull --ff-only (or git pull --rebase).",
    "brew-outdated": "Upgrade it: brew upgrade <name>, or brew upgrade to update everything.",
    "python-pin-drift": "Align the repos on one interpreter, or set each repo's intended one with uv python pin <X>.",
    "tool-version-drift": "Reinstall TypeScript to the intended version (npm install) so it matches across the repos.",
    "submodule-tags-behind": "Bump it: git -C <path> fetch --tags, check out the latest tag, then commit the pointer.",
    "docker-unreachable": "Start Docker (Docker Desktop, or colima start / systemctl start docker), then reload.",
    "tool-missing": "Install it: brew install <tool>, or uv tool install <tool> for a Python CLI.",
    "mcp-needs-auth": "Authenticate it from Claude Code: run /mcp and complete the server's auth flow.",
    "mcp-two-scopes": "Configure the server in a single scope (user or project) to avoid an ambiguous resolution.",
    "skill-disabled": "Enable it in Claude settings (enabledPlugins) if you want it active.",
    "plugin-disabled": "Enable the plugin in Claude settings (enabledPlugins) to bring it and its skills back.",
    "skill-shadow": "Two origins ship this name — rename or disable one so the reference is unambiguous.",
    "git-config-conflict": "One key is set to two different values in the chain; git takes the last, so reconcile or remove the duplicate.",
    "git-include-broken": "The include points at a file that does not exist. Create it, or drop the include directive.",
    "git-config-credentials": "A credential is embedded in a config value. Move it to a credential helper and remove it from gitconfig.",
    "git-no-identity": "No global user.email is set. Set one with git config --global user.email you@example.com.",
  };
  const TARGET_PREFIX = /^(formula|cask|pin|ts|skill|plugin|mcp):/;

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
    // The tooltip is a fix, not a restatement; a11y still hears the level + fact.
    node.title = RESOLUTION[flag.code] || flag.message;
    node.setAttribute("aria-label", lvl + ": " + flag.message);
    return node;
  }

  function cleanTarget(target) {
    let value = String(target).replace(TARGET_PREFIX, "");
    if (value.indexOf("/") >= 0) value = value.split("/").pop();
    return value;
  }

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

    const tiles = U.tiles([
      { value: flags.length, label: "Total flags" },
      { value: attention, label: "Attention", kind: "attention" },
      { value: problems, label: "Problems", kind: "problem" },
    ]);

    const built = U.table([
      { label: "Category" },
      { label: "Level" },
      { label: "Count", num: true },
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
      const countCell = U.td(barCell, "num");
      countCell.setAttribute("data-sort", String(cat.count));

      const shown =
        cat.targets.slice(0, 5).join(", ") +
        (cat.targets.length > 5 ? ", +" + (cat.targets.length - 5) + " more" : "");

      built.tbody.append(
        U.tr([U.td(el("span", "t-name", cat.label)), U.td(U.level(cat.level, cat.level)), countCell, U.td(shown, "q")]),
      );
    });
    summaryMount.replaceChildren(tiles, built.wrap);
  }

  function decorate() {
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
  }

  const api = {
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

  return api;
})();

// ---------- workspace (with submodules nested under their repo) ----------
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("workspace");
  if (!mount) return;

  const abCells = new Map();
  const smRows = new Map();

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
    return U.cellFlex(chips);
  }

  function repoRow(repo) {
    const flags = U.flagsTd("", "workspace:" + repo.path);
    const ahead = U.td(U.quiet("···"), "num");
    const behind = U.td(U.quiet("···"), "num");
    ahead.setAttribute("data-sort", "");
    behind.setAttribute("data-sort", "");
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

  function subPart(label, valueNode) {
    const part = U.el("span", "sub-part");
    part.append(U.el("span", "q", label + " "), valueNode);
    return part;
  }
  function sep() {
    return U.el("span", "sub-sep", "·");
  }

  function subRow(sub) {
    // One nested detail line spanning the row rather than data spread across
    // columns it has no values for. The in-cell line is the flag host, so a
    // "releases behind" badge lands inline at the end of the line.
    const lead = U.el("span", "sub-lead", sub.name);
    const pinned = subPart("pinned", sub.pinned ? U.el("span", "ver", sub.pinned) : U.quiet("untagged"));
    const latest = subPart("latest", U.quiet("listing…"));
    const behind = U.el("span", "sub-part sub-status");
    behind.append(U.dash());

    smRows.set(sub.path, { latest: latest, behind: behind });

    const cell = U.flagsTd([lead, sep(), pinned, sep(), latest, sep(), behind], "submodules:" + sub.path, "sub-cell");
    cell.colSpan = 8;
    const row = U.el("tr", "subrow");
    row.append(cell);
    return row;
  }

  function raiseBehind(repo, behind) {
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
      cells.behind.title = "The fetch could not reach the remote — check your network or the repo's credentials.";
      cells.ahead.setAttribute("data-sort", "");
      cells.behind.setAttribute("data-sort", "");
      raiseBehind(event.repo, 0);
      return;
    }
    if (event.ahead == null && event.behind == null) {
      cells.ahead.replaceChildren(U.dash());
      cells.behind.replaceChildren(U.dash());
      cells.behind.title = "No upstream to compare against — set one with git push -u origin <branch>.";
      cells.ahead.setAttribute("data-sort", "");
      cells.behind.setAttribute("data-sort", "");
      raiseBehind(event.repo, 0);
      return;
    }
    raiseBehind(event.repo, event.behind);
    cells.ahead.replaceChildren(document.createTextNode(String(event.ahead)));
    cells.ahead.setAttribute("data-sort", String(event.ahead));
    cells.behind.setAttribute("data-sort", String(event.behind));
    if (event.behind > 0) {
      const strong = U.el("span");
      strong.style.fontWeight = "600";
      strong.textContent = String(event.behind);
      cells.behind.replaceChildren(strong);
      cells.behind.title = "Catch up to the remote: git pull --ff-only (or git pull --rebase).";
    } else {
      cells.behind.replaceChildren(document.createTextNode("0"));
      cells.behind.title = "Level with the remote as of the last background fetch.";
    }
  }

  function raiseSubBehind(path, behind) {
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

  function setLatest(cell, value, muted) {
    cell.replaceChildren(U.el("span", "q", "latest "), muted ? U.quiet(value) : U.el("span", "ver", value));
  }

  function fillSubmodule(event) {
    const row = smRows.get(event.submodule);
    if (!row) return;
    row.latest.classList.add("filled");
    if (event.unknown) {
      setLatest(row.latest, "listing unknown", true);
      row.latest.title = "The remote tags could not be listed — check your network or the remote's credentials.";
      row.behind.replaceChildren(U.dash());
      raiseSubBehind(event.submodule, 0);
      return;
    }
    if (event.latest == null) {
      setLatest(row.latest, "no releases", true);
      row.behind.replaceChildren(U.dash());
      raiseSubBehind(event.submodule, 0);
      return;
    }
    setLatest(row.latest, event.latest, false);
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
      row.behind.title = "Bump the submodule: fetch its tags, check out the latest, then commit the pointer.";
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

    const summary = U.tiles([
      { value: workspace.repos.length, label: "Repos" },
      { value: dirty, label: "Dirty" },
      { value: noUpstream, label: "No upstream" },
      { value: subCount, label: "Submodules" },
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
// Four subtables — Python interpreters, per-repo pins, Node tools, per-repo
// TypeScript — share one shape: Name | Version | Detail | State, laid out fixed so
// the columns align down the Section. State carries the status word and hosts the
// M6 drift badges.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("toolchains");
  if (!mount) return;

  // The shared column spec, so every subtable aligns column-for-column.
  const COLUMNS = [
    { label: "Name", width: "30%" },
    { label: "Version", width: "18%" },
    { label: "Detail", width: "26%" },
    { label: "State", width: "26%" },
  ];

  function base(path) {
    return String(path).split("/").pop();
  }
  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }
  function subHead(text) {
    return U.el("p", "sub-head", text);
  }
  function nameCell(text) {
    return U.td(U.el("span", "t-name", text));
  }
  function verCell(text) {
    return U.td(text ? U.el("span", "ver", text) : U.dash());
  }

  function interpreterTable(python) {
    const built = U.table(COLUMNS);
    python.interpreters.forEach(function (interp) {
      built.tbody.append(
        U.tr([
          nameCell(interp.implementation),
          verCell(interp.version),
          U.td(U.quiet("uv-managed")),
          U.td(interp.installed ? U.ok("installed") : U.quiet("not installed")),
        ]),
      );
    });
    return built.wrap;
  }

  function pinTable(python) {
    const built = U.table(COLUMNS);
    python.repo_pins.forEach(function (pin) {
      const matches = pin.version === python.global_pin;
      const state = U.flagsTd(U.quiet(matches ? "matches global" : "differs from global"), "toolchains:pin:" + pin.repo);
      built.tbody.append(
        U.tr([nameCell(base(pin.repo)), verCell(pin.version), U.td(U.quiet("global " + (python.global_pin || "unset"))), state]),
      );
    });
    return built.wrap;
  }

  function nodeToolTable(node) {
    const built = U.table(COLUMNS);
    const roles = { node: "runtime", npm: "package manager", tsc: "compiler" };
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
      const stateCell = U.td(tool.present ? U.ok("installed") : U.quiet("not installed"));
      if (!tool.present && pair[0] === "tsc") {
        stateCell.title = "Install TypeScript globally (npm i -g typescript), or rely on each repo's local tsc.";
      }
      built.tbody.append(U.tr([nameCell(pair[0]), verCell(tool.version), U.td(U.quiet(roles[pair[0]] || "package manager")), stateCell]));
    });
    return built.wrap;
  }

  function tsTable(node) {
    const built = U.table(COLUMNS);
    node.repos.forEach(function (repo) {
      const installed = repo.installed;
      const state = U.flagsTd(installed ? U.ok("installed") : U.quiet("not installed"), "toolchains:ts:" + repo.repo);
      if (!installed) state.title = "Install the declared TypeScript: run npm install in the repo.";
      built.tbody.append(
        U.tr([
          nameCell(base(repo.repo)),
          verCell(installed),
          U.td(U.quiet("declared " + (repo.declared || "none"))),
          state,
        ]),
      );
    });
    return built.wrap;
  }

  function render(data) {
    const py = data.python;
    const node = data.node;
    const nodes = [
      U.tiles([
        { value: py.interpreters.length, label: "Interpreters" },
        { value: py.repo_pins.length, label: "Python pins" },
        { value: 3 + node.package_managers.length, label: "Node tools" },
        { value: node.repos.length, label: "TS repos" },
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
// Plugins with a count of the skills each ships — expand a plugin row to reveal
// those skills, the only place a plugin's skills appear. Then My skills (yours,
// under ~/.claude/skills) in their own table, and the MCP servers last. Values
// carry no secrets.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("claude");
  if (!mount) return;

  // Shared shape for both skill subsections, so their columns line up.
  const SKILL_COLUMNS = [
    { label: "Skill", width: "24%" },
    { label: "Origin", width: "20%" },
    { label: "State", width: "14%" },
    { label: "Description", width: "42%" },
  ];

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }
  function subHead(text) {
    return U.el("p", "sub-head", text);
  }
  function isMine(skill) {
    return skill.origin.indexOf("@") < 0; // user or project, never a <plugin>@<market> pair
  }

  // The skills a plugin ships, as a hidden nested subtable revealed when its
  // plugin row is expanded. It shares My skills' columns and is the only place a
  // plugin's skills appear. Origin repeats the plugin so the column matches.
  function pluginSkillsRow(skills, pluginName) {
    const inner = skillTable(skills, function () {
      return pluginName;
    });
    inner.classList.add("subtable");
    const cell = U.el("td");
    cell.colSpan = 6;
    cell.append(inner);
    const row = U.el("tr", "skillrow");
    row.hidden = true;
    row.append(cell);
    return row;
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
      const skills = skillsByOrigin.get(plugin.name + "@" + plugin.marketplace) || [];
      const hasSkills = skills.length > 0;

      const nameCell = U.el("td");
      if (hasSkills) nameCell.append(U.el("span", "exp-caret", "▸"));
      nameCell.append(U.el("span", "t-name", plugin.name));

      const state = U.flagsTd(U.quiet(plugin.enabled ? "enabled" : "disabled"), "claude:plugin:" + plugin.name);

      const countCell = U.td(hasSkills ? String(skills.length) : U.quiet("—"), "num");
      countCell.setAttribute("data-sort", String(skills.length));

      const row = U.tr([
        nameCell,
        U.td(plugin.marketplace, "q"),
        U.td(plugin.repo ? plugin.repo : U.dash(), "q"),
        U.td(plugin.version === "unknown" ? U.quiet("unknown") : U.el("span", "ver", plugin.version)),
        state,
        countCell,
      ]);
      built.tbody.append(row);

      if (hasSkills) {
        const skillrow = pluginSkillsRow(skills, plugin.name);
        built.tbody.append(skillrow);
        row.classList.add("expandable");
        row.setAttribute("role", "button");
        row.tabIndex = 0;
        row.setAttribute("aria-expanded", "false");
        const toggle = function () {
          const open = row.classList.toggle("open");
          skillrow.hidden = !open;
          row.setAttribute("aria-expanded", open ? "true" : "false");
        };
        row.addEventListener("click", toggle);
        row.addEventListener("keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            toggle();
          }
        });
      }
    });
    return built.wrap;
  }

  function skillTable(skills, originText) {
    const built = U.table(SKILL_COLUMNS);
    skills.forEach(function (skill) {
      const state = U.flagsTd(U.quiet(skill.enabled ? "enabled" : "disabled"), "claude:skill:" + skill.name);
      const desc = skill.description ? U.el("div", "clamp2", skill.description) : U.dash();
      if (skill.description) desc.title = skill.description;
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", skill.name)),
          U.td(originText(skill), "q"),
          state,
          U.td(desc),
        ]),
      );
    });
    return built.wrap;
  }

  function mcpTable(servers) {
    const built = U.table([{ label: "Server" }, { label: "Origin" }, { label: "Transport" }, { label: "Auth" }]);
    servers.forEach(function (server) {
      const auth = U.flagsTd(U.quiet(server.needs_auth ? "needs auth" : "ready"), "claude:mcp:" + server.name);
      built.tbody.append(
        U.tr([U.td(U.el("span", "t-name", server.name)), U.td(server.origin, "q"), U.td(server.transport, "q"), auth]),
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
    const mine = skills.filter(isMine);
    const oss = skills.length - mine.length;

    const nodes = [
      U.tiles([
        { value: plugins.length, label: "Plugins" },
        { value: mine.length, label: "My skills" },
        { value: oss, label: "OSS skills" },
        { value: servers.length, label: "MCP servers" },
      ]),
      subHead("Plugins (" + plugins.length + ") — expand a row for the skills it ships"),
      pluginTable(plugins, skillsByOrigin),
      subHead("My skills (" + mine.length + ", under ~/.claude/skills)"),
    ];
    nodes.push(
      mine.length > 0
        ? skillTable(mine, function (s) {
            return s.origin;
          })
        : U.summaryLine(["No standalone user or project skills."]),
    );
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

    const summary = U.tiles([
      { value: tools.length, label: "Tools" },
      { value: present, label: "Present" },
      { value: tools.length - present, label: "Missing" },
    ]);

    const built = U.table([{ label: "Tool" }, { label: "Version" }, { label: "Flags" }]);
    tools.forEach(function (tool) {
      const flags = U.flagsTd("", "system:" + tool.name);
      const versionCell = U.td(tool.present && tool.version ? U.el("span", "ver", tool.version) : U.dash());
      if (!tool.present) versionCell.title = "Install it: brew install " + tool.name + " (or uv tool install " + tool.name + ").";
      built.tbody.append(U.tr([U.td(U.el("span", "t-name", tool.name)), versionCell, flags]));
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
    const built = U.table([{ label: "Package" }, { label: "Installed" }, { label: "Current" }, { label: "Flags" }]);
    packages.forEach(function (pkg) {
      const flags = U.flagsTd("", "homebrew:" + kind + ":" + pkg.name);
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", pkg.name)),
          U.td(U.el("span", "from", pkg.installed || "—")),
          U.td(U.el("span", "to", pkg.current || "—")),
          flags,
        ]),
      );
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
    const summary = U.tiles([
      { value: formulae.length, label: "Formulae" },
      { value: casks.length, label: "Casks" },
      { value: total, label: "Outdated" },
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
    // Tiles only, so the Section never scrolls sideways in its narrow panel. The
    // daemon tile is the M6 flag host; a down daemon shows its facts as "—" rather
    // than as meaningless zeros.
    const specs = [{ value: reachable ? "up" : "down", label: "Daemon", flagKey: "docker:daemon" }];
    if (reachable) {
      specs.push(
        { value: data.containers_running + " / " + data.containers_total, label: "Containers running / total" },
        { value: String(data.images), label: "Images" },
        { value: data.total_disk != null ? data.total_disk : "unknown", label: "Disk" },
        { value: data.reclaimable != null ? data.reclaimable : "unknown", label: "Reclaimable" },
      );
    } else {
      specs.push(
        { value: "—", label: "Containers" },
        { value: "—", label: "Images" },
        { value: "—", label: "Disk" },
        { value: "—", label: "Reclaimable" },
      );
    }
    mount.replaceChildren(U.tiles(specs));
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

// ---------- footprint ----------
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("footprint");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function sizeCell(value) {
    return value != null ? U.td(U.el("span", "ver", value), "num") : U.td(U.dash(), "num");
  }

  function render(data) {
    const repos = data.repos || [];
    const dockerDisk = !data.docker_reachable
      ? "down"
      : data.docker_total != null
        ? data.docker_total
        : "unknown";
    const dockerRecl =
      data.docker_reachable && data.docker_reclaimable != null ? data.docker_reclaimable : "—";

    const summary = U.tiles([
      { value: String(repos.length), label: "Repos measured" },
      { value: data.repos_total || "0 B", label: "Regenerable" },
      { value: dockerDisk, label: "Docker disk" },
      { value: dockerRecl, label: "Docker reclaimable" },
    ]);

    if (repos.length === 0) {
      mount.replaceChildren(
        summary,
        U.summaryLine(["No .venv or node_modules directories under the scanned repos."]),
      );
      return;
    }

    const built = U.table([
      { label: "Repo" },
      { label: ".venv", num: true },
      { label: "node_modules", num: true },
      { label: "Total", num: true },
    ]);
    repos.forEach(function (repo) {
      const totalCell = U.td(U.el("span", "ver", repo.total), "num");
      totalCell.setAttribute("data-sort", String(repo.total_bytes));
      built.tbody.append(
        U.tr([U.td(U.el("span", "t-name", repo.path)), sizeCell(repo.venv), sizeCell(repo.node_modules), totalCell]),
      );
    });

    mount.replaceChildren(summary, built.wrap);
  }

  fetch("/api/footprint")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not measure the disk footprint. Check that the board is still running.");
    });
})();

// ---------- editor ----------
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("editor");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  function render(data) {
    if (!data.installed) {
      note("Visual Studio Code's CLI (code) is not on the path.");
      return;
    }
    const extensions = data.extensions || [];
    const summary = U.tiles([
      { value: data.version || "unknown", label: "VS Code" },
      { value: String(extensions.length), label: "Extensions" },
    ]);
    if (extensions.length === 0) {
      mount.replaceChildren(summary, U.summaryLine(["VS Code is installed but reports no extensions."]));
      return;
    }
    const built = U.table([{ label: "Extension" }, { label: "Version", num: true }]);
    extensions.forEach(function (ext) {
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", ext.id)),
          U.td(ext.version ? U.el("span", "ver", ext.version) : U.dash(), "num"),
        ]),
      );
    });
    mount.replaceChildren(summary, built.wrap);
  }

  fetch("/api/editor")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not read the editor. Check that the board is still running.");
    });
})();

// ---------- git config ----------
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("git-config");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  // Value is already display-ready: a secret-bearing key arrives masked, a URL is
  // credential-stripped, and home paths are relativised (see ADR 0001). A masked
  // value reads recessive; a shown one keeps the mono value treatment.
  function valueCell(entry) {
    const span = U.el("span", entry.masked ? "q" : "ver", entry.value);
    if (entry.masked) span.title = "Value hidden: this key can carry a secret.";
    return U.td(span);
  }

  function keyCell(entry) {
    const cell = U.td(U.el("span", "t-name", entry.key));
    if (entry.shadowed) {
      U.append(cell, U.el("span", "q", " · shadowed"));
      cell.title = "A later entry sets this key to a different value; git takes the last, so this one has no effect.";
    }
    return cell;
  }

  function render(data) {
    const entries = data.entries || [];
    const includes = data.includes || [];

    const summary = U.tiles([
      { value: String(entries.length), label: "Keys" },
      { value: String(includes.length), label: "Includes" },
      { value: data.identity_present ? "set" : "not set", label: "Identity", flagKey: "git-config:identity" },
    ]);

    if (entries.length === 0 && includes.length === 0) {
      mount.replaceChildren(summary, U.summaryLine(["No global git config found on this machine."]));
      return;
    }

    const nodes = [summary];

    if (entries.length > 0) {
      nodes.push(U.el("p", "sub-head", "Config (" + entries.length + ")"));
      const built = U.table([{ label: "Key" }, { label: "Value" }, { label: "Origin" }, { label: "Flags" }]);
      entries.forEach(function (entry) {
        built.tbody.append(
          U.tr([keyCell(entry), valueCell(entry), U.td(U.el("span", "q", entry.origin)), U.flagsTd("", "git-config:" + entry.key)]),
        );
      });
      nodes.push(built.wrap);
    }

    if (includes.length > 0) {
      nodes.push(U.el("p", "sub-head", "Includes (" + includes.length + ")"));
      const built = U.table([{ label: "Condition" }, { label: "Path" }, { label: "State" }]);
      includes.forEach(function (inc) {
        const status = inc.exists
          ? U.flagsTd(U.ok("found"), "git-config:" + inc.path)
          : U.flagsTd(U.el("span", "q", "missing"), "git-config:" + inc.path);
        built.tbody.append(
          U.tr([
            U.td(inc.condition ? U.el("span", "ver", inc.condition) : U.quiet("always")),
            U.td(U.el("span", "t-name", inc.path)),
            status,
          ]),
        );
      });
      nodes.push(built.wrap);
    }

    mount.replaceChildren.apply(mount, nodes);
  }

  fetch("/api/git-config")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not read the git config. Check that the board is still running.");
    });
})();
