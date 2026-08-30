// Board behaviour. Every Section leads with a one-line summary and lays its facts
// out in a sortable table beneath. Colour on a fact is reserved for the M6 Flag
// layer: sections stamp a data-flag-key host element and the flag layer badges it;
// neutral facts are told apart by weight, a muted tone, and a label, never by hue.
// The chrome carries one colour of its own: --sky on the Section headings, the
// board's wayfinding colour (styles.css).

// ---------- the View (M12): the board's own file, read live, written on change ----------
// Every view preference — the theme, the Hidden and Collapsed panels, and the
// Mutes — lives in wkx-ecosystem-localhost.view.toml, the file the board owns
// (ADR 0004). The board reads it on load through GET /api/view and writes it on
// every change through PATCH /api/view, one preference per call; a successful
// write is pushed to every open tab over /api/view/stream, so no tab holds a
// stale View. This module is the one client-side home for that: it fetches the
// View, migrates the old localStorage keys into it once, and lets each control
// read the current value, write a change, and re-apply when any tab writes. No
// preference lives in localStorage any more — the file is the only store.
window.wkxView = (function () {
  "use strict";

  // The old localStorage keys, migrated once into the View and then removed. This
  // is the only place they are named; after migration none remains.
  const LEGACY_THEME = "wkx-theme";
  const LEGACY_SECTIONS = "wkx-sections";
  const LEGACY_COLLAPSED = "wkx-collapsed";

  // The effective View plus its file state, mirroring the /api/view payload. It
  // starts empty (a board at its defaults) and is replaced by the server's copy.
  let current = {
    theme: null,
    sections_hidden: [],
    sections_collapsed: [],
    mute: [],
    filter: {},
    columns_hidden: {},
    sort: {},
    file: null,
    found: false,
    writable: true,
    unknown_keys: [],
  };
  const listeners = [];

  function notify() {
    listeners.forEach(function (fn) {
      fn(current);
    });
  }

  // Replace the current View with the server's authoritative copy and wake every
  // listener, so the theme, the Hidden menu, and the Collapsed headings re-apply.
  function apply(view) {
    if (view && typeof view === "object") {
      current = view;
      notify();
    }
    return current;
  }

  function theme() {
    return current.theme;
  }
  function mute() {
    return current.mute || [];
  }
  function isHidden(id) {
    return (current.sections_hidden || []).indexOf(id) >= 0;
  }
  function isCollapsed(id) {
    return (current.sections_collapsed || []).indexOf(id) >= 0;
  }
  // The three M13 table overrides, read by wkxTables and wkxFilter. Each returns a
  // safe default (empty text, empty list, no rule) when the View names no override.
  function filterFor(sectionId) {
    return (current.filter || {})[sectionId] || "";
  }
  function columnsHiddenFor(tableId) {
    return (current.columns_hidden || {})[tableId] || [];
  }
  function sortFor(tableId) {
    return (current.sort || {})[tableId] || null;
  }
  function fileState() {
    return {
      file: current.file,
      found: current.found,
      writable: current.writable,
      unknown_keys: current.unknown_keys || [],
    };
  }

  // The two config-Section Flags the View state raises. view-not-saved (red) is
  // raised when a write fails and cleared when one succeeds; view-unknown-key
  // (amber) is raised when the file names a panel or Category the board does not
  // know. Both badge the config Section's View-file line.
  function raiseNotSaved() {
    if (window.wkxFlags)
      window.wkxFlags.add({
        section: "config",
        target: "view-file",
        level: "problem",
        category: "view-not-saved",
        message: "not saved",
      });
  }
  function clearNotSaved() {
    if (window.wkxFlags) window.wkxFlags.clear("config", "view-file", "view-not-saved");
  }
  function raiseUnknownKeys() {
    const keys = current.unknown_keys || [];
    if (keys.length === 0 || !window.wkxFlags) return;
    window.wkxFlags.add({
      section: "config",
      target: "view-file",
      level: "attention",
      category: "view-unknown-key",
      message: keys.length === 1 ? "1 unknown key" : keys.length + " unknown keys",
    });
  }

  // PATCH one preference. On success the server returns the effective View, which
  // becomes the source of truth and clears the not-saved Flag. On failure the
  // preference did not persist, so the board raises view-not-saved and resyncs
  // from the server rather than keeping a value the file never took.
  function patch(body) {
    return fetch("/api/view", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (view) {
        apply(view);
        clearNotSaved();
        return view;
      })
      .catch(function (err) {
        raiseNotSaved();
        return refresh().then(function () {
          throw err;
        });
      });
  }

  function setTheme(value) {
    return patch({ field: "theme", value: value || "auto" });
  }
  function setHidden(id, on) {
    return patch({ field: "sections_hidden", panel: id, on: !!on });
  }
  function setCollapsed(id, on) {
    return patch({ field: "sections_collapsed", panel: id, on: !!on });
  }
  function setFilter(sectionId, text) {
    return patch({ field: "filter", section: sectionId, text: text || "" });
  }
  function setColumnHidden(tableId, column, on) {
    return patch({ field: "columns_hidden", table: tableId, column: column, on: !!on });
  }
  function setSort(tableId, column, direction) {
    return patch({ field: "sort", table: tableId, column: column, direction: direction || null });
  }

  function refresh() {
    return fetch("/api/view")
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (view) {
        return apply(view);
      })
      .catch(function () {
        return current;
      });
  }

  // Migration: read the three old localStorage keys once, write each preference
  // through PATCH, and delete the keys only after every write has landed. A write
  // that the board rejects as an unknown key (an old panel id it no longer knows)
  // is dropped rather than treated as a durable failure, so the migration still
  // completes and the keys are cleared.
  function readLegacy(key) {
    try {
      return localStorage.getItem(key);
    } catch (_err) {
      return null;
    }
  }
  function legacyMap(key, field, wanted) {
    let parsed;
    try {
      parsed = JSON.parse(readLegacy(key) || "{}");
    } catch (_err) {
      parsed = {};
    }
    const writes = [];
    if (parsed && typeof parsed === "object") {
      Object.keys(parsed).forEach(function (id) {
        if (parsed[id] === wanted) writes.push({ field: field, panel: id, on: true });
      });
    }
    return writes;
  }
  function migrateWrite(body) {
    return fetch("/api/view", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) {
      if (response.ok) return response.json().then(apply);
      if (response.status === 422) return current; // an old id the board no longer knows
      throw new Error("HTTP " + response.status);
    });
  }
  function clearLegacy() {
    try {
      localStorage.removeItem(LEGACY_THEME);
      localStorage.removeItem(LEGACY_SECTIONS);
      localStorage.removeItem(LEGACY_COLLAPSED);
    } catch (_err) {
      // A storage-blocked browser has nothing to clear.
    }
  }
  function migrate() {
    let writes = [];
    const savedTheme = readLegacy(LEGACY_THEME);
    if (savedTheme === "light" || savedTheme === "dark")
      writes.push({ field: "theme", value: savedTheme });
    // wkx-sections stored panel id -> visible; a false means the panel was Hidden.
    writes = writes.concat(legacyMap(LEGACY_SECTIONS, "sections_hidden", false));
    // wkx-collapsed stored panel id -> true for each Collapsed panel.
    writes = writes.concat(legacyMap(LEGACY_COLLAPSED, "sections_collapsed", true));
    if (writes.length === 0) return Promise.resolve();
    // Chain the writes so the file is merged one preference at a time; delete the
    // keys only once every write has succeeded.
    return writes
      .reduce(function (chain, body) {
        return chain.then(function () {
          return migrateWrite(body);
        });
      }, Promise.resolve())
      .then(clearLegacy);
  }

  // Converge: hold /api/view/stream open and apply every view event another tab's
  // write pushes, so no tab keeps a stale View.
  function converge() {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/view/stream");
    source.addEventListener("view", function (message) {
      try {
        apply(JSON.parse(message.data));
        raiseUnknownKeys();
      } catch (_err) {
        // Ignore a malformed frame rather than tearing down the stream.
      }
    });
    // EventSource reconnects on its own if the stream drops; nothing to do here.
  }

  const ready = refresh()
    .then(raiseUnknownKeys)
    .then(migrate)
    .then(converge);

  return {
    ready: ready,
    theme: theme,
    mute: mute,
    isHidden: isHidden,
    isCollapsed: isCollapsed,
    filterFor: filterFor,
    columnsHiddenFor: columnsHiddenFor,
    sortFor: sortFor,
    fileState: fileState,
    setTheme: setTheme,
    setHidden: setHidden,
    setCollapsed: setCollapsed,
    setFilter: setFilter,
    setColumnHidden: setColumnHidden,
    setSort: setSort,
    onChange: function (fn) {
      listeners.push(fn);
    },
  };
})();

// ---------- theme control ----------
// The masthead toggle cycles auto -> light -> dark and writes the choice to the
// View through wkxView; the board applies the theme by stamping data-theme on
// <html>. The server has already stamped the saved theme as it served the page,
// so there is no flash on load; this only keeps the button label and the
// attribute in step as the View changes here or in another tab.
(function () {
  "use strict";

  const MODES = ["auto", "light", "dark"];
  const button = document.getElementById("theme-toggle");
  const V = window.wkxView;
  if (!button || !V) return;

  function currentMode() {
    const theme = V.theme();
    return theme === "light" || theme === "dark" ? theme : "auto";
  }

  function apply() {
    const mode = currentMode();
    if (mode === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = mode;
    button.textContent = "theme: " + mode;
  }

  button.addEventListener("click", function () {
    const next = MODES[(MODES.indexOf(currentMode()) + 1) % MODES.length];
    V.setTheme(next);
  });

  V.ready.then(apply);
  V.onChange(apply);
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

  // Sorting has three states (M13): a header click goes ascending, descending, then
  // unsorted — the table back in source order. Source order is the row order at the
  // first sort, snapshotted once so the third click can restore it exactly.
  function ensureSnapshot(table) {
    const tbody = table.tBodies[0];
    if (tbody && !table.__srcOrder) table.__srcOrder = Array.prototype.slice.call(tbody.rows);
  }

  function restoreSource(table) {
    const tbody = table.tBodies[0];
    if (!tbody || !table.__srcOrder) return;
    const frag = document.createDocumentFragment();
    table.__srcOrder.forEach(function (row) {
      if (row.parentNode === tbody) frag.appendChild(row);
    });
    tbody.appendChild(frag);
  }

  function clearHeads(table) {
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (head) {
      head.removeAttribute("aria-sort");
      head.classList.remove("sort-asc", "sort-desc");
    });
  }

  function reorder(table, index, dir) {
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

  // Set the table to one sort state without persisting (the View is the source when
  // this is called from a saved rule). A null direction is the unsorted state.
  function applySort(table, index, th, dir) {
    ensureSnapshot(table);
    clearHeads(table);
    if (!dir) {
      restoreSource(table);
      return;
    }
    th.setAttribute("aria-sort", dir);
    th.classList.add(dir === "ascending" ? "sort-asc" : "sort-desc");
    reorder(table, index, dir);
  }

  function nextDir(current) {
    if (current === "ascending") return "descending";
    if (current === "descending") return null;
    return "ascending";
  }

  // A header click (or Enter/Space) cycles the state and persists it through the
  // View when the table carries an id, so the sort survives a reload.
  function cycleSort(table, index, th) {
    const dir = nextDir(th.getAttribute("aria-sort"));
    applySort(table, index, th, dir);
    // Persist the clicked column even when the new state is unsorted (dir null): the
    // write route names the column and reads a null direction as "clear this sort".
    if (window.wkxTables) window.wkxTables.persistSort(table, th.dataset.col, dir);
  }

  // Apply a saved sort by column key, for wkxTables to replay the View on load. A
  // null key or direction is the unsorted state.
  function applySortByKey(table, key, dir) {
    if (!key || !dir) {
      applySort(table, -1, null, null);
      return;
    }
    const heads = table.tHead && table.tHead.rows[0];
    if (!heads) return;
    let index = -1;
    let target = null;
    Array.prototype.forEach.call(heads.cells, function (head, i) {
      if (head.dataset.col === key) {
        index = i;
        target = head;
      }
    });
    if (index < 0) return;
    applySort(table, index, target, dir);
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
        cycleSort(table, index, th);
      });
      th.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          cycleSort(table, index, th);
        }
      });
    });
  }

  // Build a scrollable, sortable table from column specs ({label, num, width}).
  // When any column carries a width, the table lays out fixed with a colgroup so
  // sibling tables that share the same spec align column-for-column.
  //
  // Every table ends in a right-justified Flags column: the flag rail, unbroken
  // from the needs-attention summary at the top down through every Section. It is
  // appended here unless the spec already lists its own flags column (the
  // fixed-width specs, which set its width to keep the subtables aligned). A row
  // lands its badge in this column via wkxUI.flagCell, so anomalies line up down
  // one edge and a clean row leaves it empty.
  function table(columns) {
    const cols = columns.slice();
    if (!cols.some(function (c) { return c.flags; })) {
      cols.push({ label: "Flags", flags: true });
    }
    const wrap = el("div", "tbl-wrap");
    const t = el("table");
    if (cols.some(function (c) { return c.width; })) {
      t.style.tableLayout = "fixed";
      const colgroup = document.createElement("colgroup");
      cols.forEach(function (c) {
        const col = document.createElement("col");
        if (c.width) col.style.width = c.width;
        colgroup.appendChild(col);
      });
      t.appendChild(colgroup);
    }
    const thead = el("thead");
    const headRow = el("tr");
    cols.forEach(function (col) {
      headRow.append(el("th", col.num ? "num" : col.flags ? "flags" : null, col.label));
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

  // A token cell's inner span: a repo name, a tool name, or a version, tagged
  // with its (kind, value) identity so the M8 token layer can light every cell
  // that shares it across the whole board. className keeps the span's existing
  // treatment (t-name, ver); only curated cells become tokens, so branches,
  // origins, paths, and config values are built with plain el() and stay inert.
  function token(kind, value, className) {
    const node = el("span", className, value);
    node.dataset.tokenKind = kind;
    node.dataset.tokenValue = value == null ? "" : String(value);
    return node;
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

  // The right-most cell of the flag rail. Given a key it is a flag host the M6
  // layer badges; given none it is an empty, right-justified cell that keeps a
  // never-flagged row aligned under the Flags header. Both are right-justified by
  // the .flags-col rule, so every table's badges settle on one vertical edge.
  function flagCell(flagKey) {
    return flagKey ? flagsTd("", flagKey, "flags-col") : td("", "flags-col");
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
    applySortByKey: applySortByKey,
    td: td,
    token: token,
    cellFlex: cellFlex,
    flagsTd: flagsTd,
    flagCell: flagCell,
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

// ---------- sections: Off (server) + Hidden (viewer) ----------
// The masthead's second control, beside the theme toggle, and the board's boot
// gate. On load it reads /api/config for the Off Sections and the View for the
// Hidden panels, removes the panels the operator turned Off in configuration,
// applies the viewer's Hidden state, and only then resolves `ready`, which every
// Section fetch waits behind — so the board never fires a request for a panel it
// is about to remove. Off is the server's word: an Off Section's route is not
// even registered, so it is dropped outright. Hidden is the viewer's, kept in the
// View file (ADR 0004) as overrides only (a panel not named there is visible); a
// Hidden Section still carries the `hidden` attribute rather than leaving, so it
// is still fetched and its Flags still reach the needs-attention tally.
window.wkxSections = (function () {
  "use strict";

  const U = window.wkxUI;
  const V = window.wkxView;
  // Every panel the menu governs, in board order. "summary" is needs attention:
  // it is not a Section (it can never be Off) but it can be Hidden, so it takes a
  // checkbox too. The rest are the ten Sections, each id matching the enum value.
  const PANELS = [
    { id: "summary", label: "needs attention", section: false },
    { id: "workspace", label: "workspace", section: true },
    { id: "toolchains", label: "toolchains", section: true },
    { id: "claude", label: "claude", section: true },
    { id: "homebrew", label: "homebrew", section: true },
    { id: "system", label: "system", section: true },
    { id: "docker", label: "docker", section: true },
    { id: "footprint", label: "footprint", section: true },
    { id: "editor", label: "editor", section: true },
    { id: "git-config", label: "git config", section: true },
    { id: "config", label: "config", section: true },
  ];

  const toggle = document.getElementById("sections-toggle");
  const menu = document.getElementById("sections-menu");

  let off = []; // the Off Section ids, learned from /api/config
  let configData = null; // the parsed /api/config body, so the config panel reuses it
  const boxes = {}; // panel id → its menu checkbox, so a View change re-checks it

  function panelOf(id) {
    const mount = document.getElementById(id);
    return mount ? mount.closest("section") : null;
  }

  function isOff(id) {
    return off.indexOf(id) >= 0;
  }
  // Hidden is a View preference now (ADR 0004): the View holds the Hidden panel
  // ids as overrides, so a panel not named there is visible. An Off panel is never
  // visible, whatever the View says.
  function visible(id) {
    if (isOff(id)) return false;
    return V ? !V.isHidden(id) : true;
  }

  // Off panels are removed outright; Hidden ones keep their place but carry the
  // `hidden` attribute, so they are still fetched and still counted.
  function applyOne(entry) {
    const panel = panelOf(entry.id);
    if (!panel) return;
    if (entry.section && isOff(entry.id)) {
      panel.remove();
      return;
    }
    panel.hidden = !visible(entry.id);
  }
  function applyAll() {
    PANELS.forEach(applyOne);
  }

  // Write the change to the View; the PATCH response (and any other tab's write)
  // comes back through onChange, which re-applies the panels and re-checks the
  // menu, so the file stays the single source of truth.
  function setVisible(entry, show) {
    if (V) V.setHidden(entry.id, !show);
  }

  function buildMenu() {
    if (!menu) return;
    menu.replaceChildren();
    PANELS.forEach(function (entry) {
      const row = U.el("label", "disc-item" + (isOff(entry.id) ? " disc-item--off" : ""));
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = visible(entry.id);
      if (isOff(entry.id)) box.disabled = true;
      box.addEventListener("change", function () {
        setVisible(entry, box.checked);
      });
      boxes[entry.id] = box;
      row.append(box, U.el("span", "disc-label", entry.label));
      if (isOff(entry.id)) row.append(U.el("span", "disc-note", "off in config"));
      menu.append(row);
    });
  }

  // Re-check each menu box from the View, so a change made here or in another tab
  // is reflected without rebuilding the open menu.
  function updateMenu() {
    PANELS.forEach(function (entry) {
      const box = boxes[entry.id];
      if (box && !isOff(entry.id)) box.checked = visible(entry.id);
    });
  }

  function openMenu(open) {
    if (!menu || !toggle) return;
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (toggle && menu) {
    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      openMenu(menu.hidden);
    });
    // A click outside the open menu, or Escape, closes it — the theme toggle sets
    // no such trap, so this is the one place the masthead listens on the document.
    document.addEventListener("click", function (event) {
      if (!menu.hidden && !menu.contains(event.target) && event.target !== toggle) openMenu(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") openMenu(false);
    });
  }

  // Boot: read the effective configuration for the Off Sections, and the View for
  // the Hidden panels; remove the Off panels, apply the Hidden state, then build
  // the menu. `ready` resolves only after all of that, so the Section fetches
  // queued behind it never race the removal. A failed or absent config or View
  // just leaves every panel at its default.
  const configReady = fetch("/api/config")
    .then(function (response) {
      return response.ok ? response.json() : null;
    })
    .catch(function () {
      return null;
    })
    .then(function (data) {
      configData = data;
      off = (data && data.sections_off && data.sections_off.sections) || [];
    });
  const viewReady = V ? V.ready : Promise.resolve();
  const ready = Promise.all([configReady, viewReady]).then(function () {
    applyAll();
    buildMenu();
  });

  // Converge: re-apply the panels and re-check the menu whenever the View changes,
  // here or in another tab.
  if (V)
    V.onChange(function () {
      applyAll();
      updateMenu();
    });

  function whenActive(mount, run) {
    ready.then(function () {
      // An Off panel was removed, so its mount is detached; skip its fetch. A
      // Hidden panel is still connected, so it fetches and counts as normal.
      if (mount && mount.isConnected) run();
    });
  }

  // The parsed /api/config body from the boot fetch, so the config panel renders
  // from it rather than fetching the same endpoint a second time. Null when the
  // boot fetch failed, which the config panel renders as its own error.
  function config() {
    return configData;
  }

  return { ready: ready, whenActive: whenActive, isOff: isOff, config: config };
})();

// ---------- Flag layer (M6) + needs-attention summary + muting (M10) ----------
// The cross-cutting anomaly layer. It gathers no facts of its own — the server
// derives the at-rest Flags over /api/flags — but it owns the two places a Flag
// shows: an inline amber (attention) or red (problem) badge on the row carrying
// the fact, and the needs-attention summary that groups every open Flag by
// Category. Every flaggable row stamps a data-flag-key of "<section>:<target>",
// so a Flag settles onto its row without this layer knowing how the row is drawn;
// a MutationObserver re-decorates as panels and SSE updates land. The summary
// reads the same registry, so at-rest and SSE-raised Flags share one source of
// truth and the summary updates the moment a background probe lands.
//
// Muting is a client-side view preference (M10). The operator's Mute rules arrive
// on /api/config; place() is the one choke point every Flag passes through, at
// rest or raised from SSE, and it drops a muted Flag into a separate `muted` set
// before it ever reaches the registry — so neither decorate() nor the summary's
// Total/Attention/Problems tiles see it. A fourth Muted tile counts the muted set,
// so nothing is hidden silently; /api/flags still reports every Flag, muted or not.
window.wkxFlags = (function () {
  "use strict";

  const U = window.wkxUI;
  const board = document.querySelector(".board");
  const summaryMount = document.getElementById("summary");
  if (!board) {
    return {
      add: function () {},
      clear: function () {},
      tally: function () {
        return { attention: 0, problems: 0 };
      },
      subscribe: function () {},
    };
  }

  // The label each Flag Category rolls up to in the summary. Its keys are the
  // twenty-one Category ids; a test cross-checks them against flags.CATEGORIES.
  const CATEGORY_LABEL = {
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
    "view-not-saved": "View not saved",
    "view-unknown-key": "Unknown View key",
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
    "view-not-saved": "The last change could not be written to the View file. Check the file is present and writable, then try again.",
    "view-unknown-key": "The View file names a panel or Category the board does not know; the board dropped it. Check the file for a stale name.",
  };
  const TARGET_PREFIX = /^(formula|cask|pin|ts|skill|plugin|mcp):/;

  // The live Flags the board shows, and the muted ones it counts but hides. A
  // Flag is in exactly one of the two, decided by place() the moment it arrives.
  const registry = new Map();
  const muted = new Map();
  let decorating = false;

  // Listeners woken whenever the live registry changes, so a reader of the tally
  // (the collapse layer's collapsed headings) re-renders as Flags land and clear.
  // Muted Flags never reach the registry, so they never wake a listener.
  const subscribers = [];
  function notify() {
    subscribers.forEach(function (fn) {
      fn();
    });
  }

  function el(tag, className, text) {
    return U.el(tag, className, text);
  }
  function keyOf(flag) {
    return flag.section + "|" + flag.target + "|" + flag.category;
  }
  function rowKey(flag) {
    return flag.section + ":" + flag.target;
  }

  // The operator's Mute rules, read from the View (ADR 0004): Mute moved out of
  // the configuration into the board's own file. Empty until the View lands (and
  // if it fails), so a Flag arriving early is simply not muted rather than
  // erroring. Flag placement is behind the boot gate, which waits on the View, so
  // the rules are present by the time a Flag is placed.
  function muteRules() {
    return window.wkxView ? window.wkxView.mute() : [];
  }

  // A Flag is muted when a rule names its Category and either targets it exactly
  // or (no target) mutes the whole Category, including the SSE-raised ones.
  function isMuted(flag) {
    return muteRules().some(function (rule) {
      if (rule.category !== flag.category) return false;
      return rule.target == null || rule.target === flag.target;
    });
  }

  // The one choke point every Flag passes through, at rest or raised from SSE: a
  // muted Flag lands in `muted` and never reaches the registry, so decorate() and
  // the Total/Attention/Problems tiles never see it; a live one lands in the
  // registry. Keeping a Flag out of both on the other outcome keeps a rule change
  // from leaving a stale copy behind.
  function place(flag) {
    const key = keyOf(flag);
    if (isMuted(flag)) {
      registry.delete(key);
      muted.set(key, flag);
    } else {
      muted.delete(key);
      registry.set(key, flag);
    }
  }

  // Drop a Flag by identity from wherever it sits, so clearing an SSE Flag (a repo
  // caught up to its remote) removes it whether it was live or muted.
  function remove(section, target, category) {
    const key = section + "|" + target + "|" + category;
    registry.delete(key);
    muted.delete(key);
  }

  function badge(flag) {
    const lvl = flag.level === "problem" ? "problem" : "attention";
    const node = el("span", "flag flag--" + lvl, flag.message);
    node.dataset.flagCategory = flag.category;
    // The tooltip is a fix, not a restatement; a11y still hears the level + fact.
    node.title = RESOLUTION[flag.category] || flag.message;
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
    const mutedCount = muted.size;
    // Needs attention shows its own total on its collapsed heading — the count of
    // open Flags — rather than a per-Section tally, because it is the rollup.
    if (window.wkxCollapse) {
      window.wkxCollapse.count("summary", flags.length === 1 ? "1 flag" : flags.length + " flags");
    }
    if (flags.length === 0 && mutedCount === 0) {
      summaryMount.replaceChildren(
        U.summaryLine(["Every Section is clear — nothing wants attention right now."]),
      );
      return;
    }

    const problems = flags.filter(function (f) {
      return f.level === "problem";
    }).length;
    const attention = flags.length - problems;

    // Four tiles: Total, Attention, and Problems count the live Flags only; Muted
    // counts the ones a rule silenced, so the suppression is always in view and
    // never a silent subtraction. Muted reads in the quiet tone, not amber or red:
    // a muted Flag is deliberately quieted, not a live anomaly.
    const tiles = U.tiles([
      { value: flags.length, label: "Total flags" },
      { value: attention, label: "Attention", kind: "attention" },
      { value: problems, label: "Problems", kind: "problem" },
      { value: mutedCount, label: "Muted", kind: "muted" },
    ]);

    if (flags.length === 0) {
      // Everything visible is clear, but a rule has muted some Flags — say so, so
      // the Muted tile reads as a deliberate choice rather than a mystery.
      summaryMount.replaceChildren(
        tiles,
        U.summaryLine([
          mutedCount === 1
            ? "Every visible Section is clear; 1 Flag is muted."
            : "Every visible Section is clear; " + mutedCount + " Flags are muted.",
        ]),
      );
      return;
    }

    const order = [];
    const groups = new Map();
    flags.forEach(function (flag) {
      const label = CATEGORY_LABEL[flag.category] || flag.category;
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

    const max = cats.reduce(function (m, c) {
      return Math.max(m, c.count);
    }, 1);

    // The summary rides the same rail as every Section: its right-most column is
    // Flags too, holding each Category's level badge, so the amber/red marks line
    // up from the top of the board down. The badge is the level marker (.lvl),
    // decorative and never touched by the flag layer's cleanup.
    const built = U.table([
      { label: "Category" },
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
        U.tr([
          U.td(el("span", "t-name", cat.label)),
          countCell,
          U.td(shown, "q"),
          U.td(U.level(cat.level, cat.level), "flags-col"),
        ]),
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
          if (host.querySelector(':scope > .flag[data-flag-category="' + flag.category + '"]')) return;
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
        const category = node.dataset.flagCategory;
        let live = false;
        registry.forEach(function (flag) {
          if (rowKey(flag) === key && flag.category === category) live = true;
        });
        if (!live) node.remove();
      });
    } finally {
      decorating = false;
    }
  }

  // A Section's live Flag tally: attention and problem counts over the registry,
  // so muted Flags are already excluded. Keyed by the Flag's section, which equals
  // the panel id (the Section enum value); "summary" is never a Flag's section, so
  // its tally is empty and the rollup shows its own total instead.
  function tally(section) {
    let attention = 0;
    let problems = 0;
    registry.forEach(function (flag) {
      if (flag.section !== section) return;
      if (flag.level === "problem") problems++;
      else attention++;
    });
    return { attention: attention, problems: problems };
  }

  const api = {
    add: function (flag) {
      place(flag);
      decorate();
      renderSummary();
      notify();
    },
    clear: function (section, target, category) {
      remove(section, target, category);
      decorate();
      renderSummary();
      notify();
    },
    tally: tally,
    // Register a listener for registry changes; it fires on every add and clear
    // and once more when the at-rest Flags land. Returns nothing; there is no
    // unsubscribe, because the collapse layer lives for the life of the page.
    subscribe: function (fn) {
      subscribers.push(fn);
    },
  };

  new MutationObserver(decorate).observe(board, { childList: true, subtree: true });

  // Wait for the boot gate: Off panels are removed first, so no Flag ever lands on
  // a host the board is about to drop. Needs attention itself is never Off, so this
  // always runs; the server has already left every Off Section's Flags out.
  window.wkxSections.ready.then(function () {
    fetch("/api/flags")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        // Through the same choke point as the SSE-raised Flags, so a muted at-rest
        // Flag is counted and hidden here too, not just the ones raised later.
        (data.flags || []).forEach(place);
        decorate();
        renderSummary();
        notify();
      })
      .catch(function () {
        if (summaryMount) {
          summaryMount.replaceChildren(
            U.summaryLine(["Could not derive the flags. Check that the board is still running."]),
          );
        }
      });
  });

  return api;
})();

// ---------- collapse (M11) ----------
// A viewer's fold-to-heading preference, the third client-side view preference
// beside the theme and Hidden. Every panel — the ten Sections and the Needs
// attention rollup — collapses to its `signage` heading and expands again. The
// whole heading line is the toggle: a <button> inside the `signage` paragraph
// wrapping the label and a rotating caret, the idiom the expandable plugin row
// uses, with `aria-expanded` and `aria-controls` naming the panel's mount.
//
// State is the View's `sections_collapsed` list (ADR 0004), overrides only the
// way Hidden is: collapsing adds the panel id, expanding removes it, and a panel
// not in the list is expanded. The board writes each change to the View file and
// re-applies as the View changes here or in another tab. Collapsed and Hidden are
// independent, and an Off panel's stale id is inert because its mount is gone.
//
// A Collapsed panel stays on the board and is still fetched, so its Flags still
// count (CONTEXT.md): collapse is a reading convenience, not a Mute. Hiding the
// body keeps the mount in the DOM (the `hidden` attribute, never a display class
// on a table element), so the Flag layer still badges its rows and the tally still
// reads them. While collapsed, and only then because the tiles carry these when
// expanded, the heading shows two things: the one-line count the Section's render
// supplies through count(), and the Section's live Flag tally from the registry,
// re-rendered as Flags land and clear. Before the data lands the count is the
// pending glyph.
window.wkxCollapse = (function () {
  "use strict";

  const U = window.wkxUI;
  const flags = window.wkxFlags;
  const V = window.wkxView;
  const PENDING = "···"; // the board's pending glyph, shown before a count lands
  // Every panel id, the Section enum values plus "summary" (Needs attention).
  const IDS = [
    "summary",
    "workspace",
    "toolchains",
    "claude",
    "homebrew",
    "system",
    "docker",
    "footprint",
    "editor",
    "git-config",
    "config",
  ];

  const counts = {}; // panel id → the latest one-line count its render supplied
  const parts = {}; // panel id → its built DOM handles, once wired

  // Collapsed is a View preference now (ADR 0004): the View holds the Collapsed
  // panel ids as overrides, so a panel not named there is expanded.
  function collapsed(id) {
    return V ? V.isCollapsed(id) : false;
  }

  // Format a plural count from a bare noun, e.g. label(14, "repo") → "14 repos".
  function label(n, singular) {
    return n + " " + (n === 1 ? singular : singular + "s");
  }

  // The live Flag tally as level badges (attention, then problem), reusing the
  // summary's decorative `.lvl` marker — never the flag layer's `.flag`, which its
  // decorate() cleanup would strip from a heading that hosts no data-flag-key.
  function renderTally(id) {
    const p = parts[id];
    if (!p) return;
    const t = flags.tally(id);
    const nodes = [];
    if (t.attention > 0) {
      const badge = U.level("attention", String(t.attention));
      badge.setAttribute("aria-label", label(t.attention, "attention flag"));
      badge.title = label(t.attention, "attention flag");
      nodes.push(badge);
    }
    if (t.problems > 0) {
      const badge = U.level("problem", String(t.problems));
      badge.setAttribute("aria-label", label(t.problems, "problem flag"));
      badge.title = label(t.problems, "problem flag");
      nodes.push(badge);
    }
    p.tally.replaceChildren.apply(p.tally, nodes);
  }

  function renderCount(id) {
    const p = parts[id];
    if (!p) return;
    p.count.textContent = counts[id] != null ? counts[id] : PENDING;
  }

  // Reflect a panel's state onto its DOM: the mount keeps its place but hides its
  // body when collapsed, the caret and aria-expanded flip, and the collapsed
  // heading's count and tally show only while collapsed.
  function apply(id) {
    const p = parts[id];
    if (!p) return;
    const isCollapsed = collapsed(id);
    p.section.classList.toggle("panel--collapsed", isCollapsed);
    p.mount.hidden = isCollapsed;
    p.info.hidden = !isCollapsed;
    p.toggle.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
    if (isCollapsed) {
      renderCount(id);
      renderTally(id);
    }
  }

  // Write the change to the View; the PATCH response (and any other tab's write)
  // comes back through onChange, which re-applies the panel, so the file stays the
  // single source of truth.
  function setCollapsed(id, value) {
    if (V) V.setCollapsed(id, value);
  }

  function applyAll() {
    IDS.forEach(apply);
  }

  // Turn a panel's `signage` heading into the toggle: a button wrapping a rotating
  // caret and the existing label, plus a heading-only info span for the collapsed
  // count and tally. Returns the handles apply() and the renderers work through.
  function wire(id) {
    const mount = document.getElementById(id);
    if (!mount) return null;
    const section = mount.closest("section");
    const signage = section && section.querySelector(".signage");
    if (!section || !signage) return null;

    const labelText = signage.textContent.trim();
    const toggle = U.el("button", "signage-toggle");
    toggle.type = "button";
    toggle.setAttribute("aria-controls", id);
    toggle.append(
      U.el("span", "signage-caret", "▸"),
      U.el("span", "signage-label", labelText),
    );

    const count = U.el("span", "signage-count");
    const tally = U.el("span", "signage-tally");
    const info = U.el("span", "signage-info");
    info.append(count, tally);

    signage.replaceChildren(toggle, info);
    toggle.addEventListener("click", function () {
      setCollapsed(id, !collapsed(id));
    });

    return { section: section, mount: mount, toggle: toggle, info: info, count: count, tally: tally };
  }

  IDS.forEach(function (id) {
    const p = wire(id);
    if (p) {
      parts[id] = p;
      apply(id);
    }
  });

  // Apply the Collapsed state once the View lands, and again whenever it changes
  // here or in another tab, so a fold made in one tab folds in the others too.
  if (V) {
    V.ready.then(applyAll);
    V.onChange(applyAll);
  }

  // Re-render the tally of every Collapsed panel as Flags land and clear; an
  // expanded panel carries its Flags on its tiles, so it needs no update.
  flags.subscribe(function () {
    IDS.forEach(function (id) {
      if (collapsed(id)) renderTally(id);
    });
  });

  return {
    label: label,
    // A Section's render supplies its one-line count here (e.g. "14 repos"); the
    // collapsed heading shows it, and the pending glyph until the first call.
    count: function (id, text) {
      counts[id] = text;
      if (collapsed(id)) renderCount(id);
    },
  };
})();

// ---------- token highlight (M8) ----------
// The board's one interactive accent. Hovering or keyboard-focusing a repo name,
// a tool name, or a version lights every cell holding that exact same-kind value,
// across the whole board, in the reserved --match colour. Matching is exact and
// same-kind, so "3.14.4" lights other "3.14.4" while "3.14" does not, with no
// semver reading. Real divergence is already the drift Flags' job. Cells stamp
// their (kind, value) identity at construction (wkxUI.token); this layer prepares
// each one to take keyboard focus and, like the Flag layer, re-decorates as panels
// render and SSE fields land, so a late value is still highlightable.
//
// The highlight has two states. Hover or focus lights it transiently, clearing as
// the pointer or focus moves away. A click, or Enter/Space on a focused token,
// PINS it: the origin takes a committed treatment (a crisp --match ring on top of
// the wash) and the highlight persists after the pointer leaves, so a value can be
// compared across panels hands-free. Esc, or a click on empty space, releases the
// pin. A pinned token reports its state to assistive tech as a pressed toggle
// button. The pin gesture cooperates with cells already wired to a click
// (expandable plugin rows, sortable headers): a token click stops there and pins
// rather than also toggling the cell underneath it, and a click that lands on
// another interactive cell keeps the pin rather than dropping it as empty space.
window.wkxTokens = (function () {
  "use strict";

  const board = document.querySelector(".board");
  if (!board) return { decorate: function () {} };

  const TOKEN = "[data-token-kind]";
  let lit = [];
  let pinned = null; // the pinned origin cell, or null when nothing is pinned

  function tokenAt(target) {
    return target && target.closest ? target.closest(TOKEN) : null;
  }

  // Identity is stamped at construction; this wires each token cell to be a
  // keyboard-operable toggle: focusable, announced as a button, and reporting its
  // pin state through aria-pressed. It runs again as new cells render
  // (MutationObserver) and touches only cells not yet prepared, so it is cheap and
  // idempotent. It sets attributes and binds the cell's own click/keydown, never
  // appends children, so it can never retrigger the childList observer.
  function decorate() {
    board.querySelectorAll(TOKEN + ":not([data-token-ready])").forEach(function (node) {
      node.dataset.tokenReady = "1";
      node.tabIndex = 0;
      node.setAttribute("role", "button");
      node.setAttribute("aria-pressed", "false");
      node.setAttribute("aria-label", "Highlight matches of " + node.dataset.tokenValue + " across the board");
      node.addEventListener("click", onActivate);
      node.addEventListener("keydown", onKeydown);
    });
  }

  function clear() {
    lit.forEach(function (node) {
      node.classList.remove("tok-match", "tok-origin", "tok-pinned");
    });
    lit = [];
  }

  // Light every cell sharing the origin's (kind, value); the origin takes the
  // stronger origin wash, and the committed ring too when it is the pinned one.
  function paint(origin) {
    const kind = origin.dataset.tokenKind;
    const value = origin.dataset.tokenValue;
    if (kind == null || value == null) return;
    clear();
    board.querySelectorAll(TOKEN).forEach(function (node) {
      if (node.dataset.tokenKind === kind && node.dataset.tokenValue === value) {
        node.classList.add("tok-match");
        lit.push(node);
      }
    });
    origin.classList.add("tok-origin");
    if (origin === pinned) origin.classList.add("tok-pinned");
  }

  // After a transient hover or focus ends, fall back to the pinned highlight
  // rather than going dark, so a pin survives the pointer moving away or previewing
  // another value.
  function restore() {
    if (pinned) paint(pinned);
    else clear();
  }

  function setPressed(node, on) {
    if (node) node.setAttribute("aria-pressed", on ? "true" : "false");
  }

  function pin(origin) {
    if (pinned === origin) {
      release(); // a second activation on the same token unpins it
      return;
    }
    setPressed(pinned, false);
    pinned = origin;
    setPressed(pinned, true);
    paint(origin);
  }

  function release() {
    setPressed(pinned, false);
    pinned = null;
    clear();
  }

  // A token's own click pins it and stops there, so the expandable row or sortable
  // header hosting it does not also fire; re-clicking the pinned token unpins it.
  function onActivate(event) {
    event.stopPropagation();
    pin(event.currentTarget);
  }

  function onKeydown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault(); // no page scroll on Space; role=button gets no synthetic click
      event.stopPropagation(); // don't let the row/header keydown handler toggle too
      pin(event.currentTarget);
    }
  }

  // Delegate hover and focus on the board so late-rendered cells are covered
  // without rebinding. Leaving a token restores the pin (or clears); moving
  // straight onto another re-lights on its enter.
  board.addEventListener("mouseover", function (event) {
    const origin = tokenAt(event.target);
    if (origin) paint(origin);
  });
  board.addEventListener("mouseout", function (event) {
    if (tokenAt(event.target)) restore();
  });
  board.addEventListener("focusin", function (event) {
    const origin = tokenAt(event.target);
    if (origin) paint(origin);
  });
  board.addEventListener("focusout", function (event) {
    if (tokenAt(event.target)) restore();
  });

  // A click that misses every token releases the pin, but only when it lands on
  // genuine empty space: a click on another interactive cell (a sortable header
  // or an expandable row, both role=button) or a link (a GitHub repo link) keeps
  // the pin so the gestures coexist and a comparison survives opening a repo. A
  // token's own click never reaches here (it stops propagation).
  board.addEventListener("click", function (event) {
    if (tokenAt(event.target)) return;
    if (event.target.closest && event.target.closest('[role="button"], a')) return;
    release();
  });

  // Esc releases from anywhere, whether or not focus is inside the board.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") release();
  });

  new MutationObserver(decorate).observe(board, { childList: true, subtree: true });
  decorate();

  return { decorate: decorate };
})();

// ---------- tables: the columns menu and the three-state sort (M13) ----------
// Every board table reads through three controls the View persists (ADR 0004): a
// per-Section Filter (wkxFilter, below), a per-table columns menu, and a sort that
// clears back to source order. This module owns the last two. A render builds its
// table with wkxTables.mount(labelCols, id), appends its rows, then calls equip():
// mount adds the slim `columns ▾` toolbar (the board's own `.disc` checklist) above
// the table and tags the <table> with its id; equip stamps each cell with its
// column key, applies the View's Hidden columns and sort, and registers the table
// with its Section's Filter. Column hiding is a class on the <table>
// (`hide-<key>`), never a display rule on a cell, so a td/th/tr never carries a
// display-altering class (styles.css, tests/test_static_assets.py). Tables that
// share one column spec share one id — the four toolchains subtables and the two
// Claude skills tables — so a change to one aligns the others through the View.
window.wkxTables = (function () {
  "use strict";

  const U = window.wkxUI;
  const V = window.wkxView;

  // The catalogue mirror: every table id maps to its column keys, in board order.
  // A test pins this to the Python catalogue (flags.TABLES) the way CATEGORY_LABEL
  // is pinned to CATEGORIES, so the client and the write-side validation agree.
  const TABLE_COLUMNS = {
    "workspace": ["repo", "branch", "upstream", "ahead", "behind", "working-tree", "stash", "roadmap", "flags"],
    "toolchains": ["name", "version", "detail", "state", "flags"],
    "claude-plugins": ["plugin", "marketplace", "repo", "version", "state", "skills", "flags"],
    "claude-skills": ["skill", "origin", "state", "description", "flags"],
    "claude-mcp": ["server", "origin", "transport", "auth", "flags"],
    "system-tools": ["tool", "version", "flags"],
    "homebrew-packages": ["package", "installed", "current", "flags"],
    "footprint": ["repo", "venv", "node-modules", "total", "flags"],
    "editor-extensions": ["extension", "version", "flags"],
    "git-config-keys": ["key", "value", "origin", "flags"],
    "git-config-includes": ["condition", "path", "state", "flags"],
    "config-settings": ["setting", "value", "source", "flags"],
    "config-excludes": ["exclude-glob", "flags"],
    "config-tools": ["tool", "version-probe", "flags"],
    "config-off": ["section", "flags"],
    "config-mutes": ["category", "target", "flags"],
  };

  // The catalogue mirror's section field: every table id maps to the Section it
  // lives in, so the per-Section Filter registers each table under its own
  // Section (a table id is not its Section id — claude-skills lives in claude).
  // Pinned to flags.TABLES the same way TABLE_COLUMNS is.
  const TABLE_SECTION = {
    "workspace": "workspace",
    "toolchains": "toolchains",
    "claude-plugins": "claude",
    "claude-skills": "claude",
    "claude-mcp": "claude",
    "system-tools": "system",
    "homebrew-packages": "homebrew",
    "footprint": "footprint",
    "editor-extensions": "editor",
    "git-config-keys": "git-config",
    "git-config-includes": "git-config",
    "config-settings": "config",
    "config-excludes": "config",
    "config-tools": "config",
    "config-off": "config",
    "config-mutes": "config",
  };

  // The locked columns of each table: the name column (the row's identity) and the
  // Flags rail. A locked column is shown fixed in the menu and can never be Hidden.
  const LOCKED = {
    "workspace": ["repo", "flags"],
    "toolchains": ["name", "flags"],
    "claude-plugins": ["plugin", "flags"],
    "claude-skills": ["skill", "flags"],
    "claude-mcp": ["server", "flags"],
    "system-tools": ["tool", "flags"],
    "homebrew-packages": ["package", "flags"],
    "footprint": ["repo", "flags"],
    "editor-extensions": ["extension", "flags"],
    "git-config-keys": ["key", "flags"],
    "git-config-includes": ["path", "flags"],
    "config-settings": ["setting", "flags"],
    "config-excludes": ["exclude-glob", "flags"],
    "config-tools": ["tool", "flags"],
    "config-off": ["section", "flags"],
    "config-mutes": ["category", "flags"],
  };

  const registry = []; // { table, id, keys, locked } for every equipped table

  function hiddenSet(id) {
    return new Set(V ? V.columnsHiddenFor(id) : []);
  }

  // Reflect the View's Hidden columns onto one table: a `hide-<key>` class on the
  // <table> for each Hidden column, and nothing on any cell.
  function applyHidden(entry) {
    const hidden = hiddenSet(entry.id);
    entry.keys.forEach(function (key) {
      if (entry.locked.indexOf(key) >= 0) return;
      entry.table.classList.toggle("hide-" + key, hidden.has(key));
    });
    if (entry.boxes) {
      entry.keys.forEach(function (key) {
        const box = entry.boxes[key];
        if (box && entry.locked.indexOf(key) < 0) box.checked = !hidden.has(key);
      });
    }
  }

  // Reflect the View's sort onto one table, without persisting (the View is already
  // the source). An absent rule is the unsorted, source-order state.
  function applySort(entry) {
    const rule = V ? V.sortFor(entry.id) : null;
    U.applySortByKey(entry.table, rule ? rule.column : null, rule ? rule.direction : null);
  }

  // Build the slim, right-aligned `columns ▾` toolbar above a table: the board's own
  // `.disc` checklist, one row per column, locked columns shown fixed.
  function buildToolbar(entry) {
    const bar = U.el("div", "table-toolbar");
    const ctrl = U.el("div", "sections-ctrl");
    const btn = U.el("button", "disc");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.append(document.createTextNode("columns"), U.el("span", "disc-caret", "▾"));
    const menu = U.el("div", "disc-menu");
    menu.hidden = true;
    menu.setAttribute("role", "group");
    menu.setAttribute("aria-label", "Columns");
    entry.boxes = {};
    const hidden = hiddenSet(entry.id);
    const heads = entry.table.tHead && entry.table.tHead.rows[0];
    entry.keys.forEach(function (key, index) {
      const isLocked = entry.locked.indexOf(key) >= 0;
      const label = heads && heads.cells[index] ? heads.cells[index].textContent.trim() : key;
      const row = U.el("label", "disc-item" + (isLocked ? " disc-item--off" : ""));
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = isLocked ? true : !hidden.has(key);
      box.disabled = isLocked;
      if (!isLocked)
        box.addEventListener("change", function () {
          if (V) V.setColumnHidden(entry.id, key, !box.checked);
        });
      entry.boxes[key] = box;
      row.append(box, U.el("span", "disc-label", label));
      if (isLocked) row.append(U.el("span", "disc-note", "locked"));
      menu.append(row);
    });
    btn.addEventListener("click", function (event) {
      event.stopPropagation();
      const open = menu.hidden;
      menu.hidden = !open;
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("click", function (event) {
      if (!menu.hidden && !ctrl.contains(event.target)) {
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !menu.hidden) {
        menu.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });
    ctrl.append(btn, menu);
    bar.append(ctrl);
    return bar;
  }

  // Stamp each header and body cell with its column key, so a `hide-<key>` class on
  // the table can drop the column and the Filter can read a row value by column.
  // Rows whose cell count does not match the spec (a full-width nested subtable) are
  // left alone: they span the table and carry no per-column cells.
  function stampCols(entry) {
    const keys = entry.keys;
    const head = entry.table.tHead && entry.table.tHead.rows[0];
    if (head)
      Array.prototype.forEach.call(head.cells, function (th, index) {
        if (keys[index]) th.dataset.col = keys[index];
      });
    const tbody = entry.table.tBodies[0];
    if (!tbody) return;
    Array.prototype.forEach.call(tbody.rows, function (row) {
      if (row.cells.length !== keys.length) return;
      Array.prototype.forEach.call(row.cells, function (cell, index) {
        cell.dataset.col = keys[index];
      });
    });
  }

  // Build a table wired for the columns menu and the three-state sort. Returns the
  // block to mount (`wrap`), the tbody to append rows to, and equip() to call once
  // the rows are in place.
  function mount(labelCols, id) {
    const built = U.table(labelCols);
    const table = built.wrap.querySelector("table");
    const keys = TABLE_COLUMNS[id] || [];
    const entry = { table: table, id: id, keys: keys, locked: LOCKED[id] || [] };
    table.dataset.tableId = id;
    const block = U.el("div", "table-block");
    block.append(buildToolbar(entry), built.wrap);
    registry.push(entry);
    return {
      wrap: block,
      tbody: built.tbody,
      equip: function () {
        stampCols(entry);
        applyHidden(entry);
        applySort(entry);
        if (window.wkxFilter) window.wkxFilter.register(TABLE_SECTION[id] || id, table);
      },
    };
  }

  // Persist a sort a header click produced. Called by wkxUI.makeSortable for any
  // table that carries a table id. A null direction clears the sort (source order);
  // the column is still named so the write route accepts the clear.
  function persistSort(table, column, direction) {
    if (!V || !table.dataset.tableId) return;
    V.setSort(table.dataset.tableId, column, direction || null);
  }

  // Re-apply the Hidden columns and the sort whenever the View changes here or in
  // another tab, and re-check every open menu, so the tables stay in step.
  if (V)
    V.onChange(function () {
      registry.forEach(function (entry) {
        applyHidden(entry);
        applySort(entry);
      });
    });

  return { mount: mount, persistSort: persistSort };
})();

// ---------- filter: one Filter per Section, header-native (M13) ----------
// Each filterable Section's `signage` heading gains a ⌕ button; a click reveals a
// Filter input beside it, which stays visible while a Filter is set and shows an
// "N of M" count. One Filter narrows every table in its Section: a row stays when
// any of its visible values — the Flag badge text included — contains the Filter
// text, regardless of letter case; a Hidden column is outside the Filter's reach.
// The matching text is marked with the board's `--match` token wash so it stays
// legible in both themes. A filtered-out row is hidden with the `hidden` attribute
// (never a display-altering class on a tr), so it is still fetched and its Flags
// still count. The Filter runs again when an SSE-raised Flag lands, and when a
// column is Hidden or shown (the scope changed). Writes to the View are debounced
// so typing does not write on every keystroke. There is no `/` shortcut.
window.wkxFilter = (function () {
  "use strict";

  const U = window.wkxUI;
  const V = window.wkxView;
  const flags = window.wkxFlags;
  const WRITE_DELAY = 400; // debounce, so a burst of keystrokes is one write

  // Every filterable Section: the ones that own at least one table. Docker is
  // tiles-only and the summary is the Flag rollup, so neither is here.
  const SECTION_IDS = [
    "workspace",
    "toolchains",
    "claude",
    "homebrew",
    "system",
    "footprint",
    "editor",
    "git-config",
    "config",
  ];

  const sections = {}; // section id -> { input, count, tables:Set, timer }

  function groupsOf(tbody) {
    const groups = [];
    Array.prototype.forEach.call(tbody.rows, function (row) {
      const child = row.classList.contains("subrow") || row.classList.contains("skillrow");
      if (child && groups.length) groups[groups.length - 1].push(row);
      else groups.push([row]);
    });
    return groups;
  }

  // Unwrap every match mark in a row, restoring its plain text nodes.
  function clearMarks(row) {
    const marks = row.querySelectorAll("mark.match");
    Array.prototype.forEach.call(marks, function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    if (marks.length) row.normalize();
  }

  // One row's searchable text: every visible cell's text, a Hidden column left out.
  function rowText(row, hiddenCols) {
    let text = "";
    Array.prototype.forEach.call(row.cells, function (cell) {
      const col = cell.dataset.col;
      if (col && hiddenCols.has(col)) return;
      text += " " + cell.textContent;
    });
    return text.toLowerCase();
  }

  // Wrap each first per-text-node match in one visible cell with a `.match` mark.
  function markCell(cell, query) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, null);
    const nodes = [];
    let node = walker.nextNode();
    while (node) {
      nodes.push(node);
      node = walker.nextNode();
    }
    nodes.forEach(function (textNode) {
      const idx = textNode.nodeValue.toLowerCase().indexOf(query);
      if (idx < 0) return;
      const mid = textNode.splitText(idx);
      mid.splitText(query.length);
      const mark = U.el("mark", "match", mid.nodeValue);
      mid.parentNode.replaceChild(mark, mid);
    });
  }

  function markRow(row, hiddenCols, query) {
    Array.prototype.forEach.call(row.cells, function (cell) {
      const col = cell.dataset.col;
      if (col && hiddenCols.has(col)) return;
      markCell(cell, query);
    });
  }

  // Apply a Section's Filter to every table registered under it, and update the
  // "N of M" count. A group is its parent row plus any child rows (a submodule
  // beneath its repo); the whole group stays or goes together so a child never
  // outlives its parent. A nested skills subtable (a skillrow) is left to its own
  // expand toggle when its parent stays, and hidden with its parent when it goes.
  function apply(id) {
    const reg = sections[id];
    if (!reg) return;
    const raw = reg.input.value;
    const query = raw.trim().toLowerCase();
    let shown = 0;
    let total = 0;
    reg.tables.forEach(function (table) {
      // Skip a detached table rather than counting it: a table is registered by
      // equip() before its Section appends it (so it is momentarily disconnected
      // on its first apply), and a re-render leaves its old table disconnected —
      // either way an unconnected table is inert, never deleted here.
      if (!table.isConnected) return;
      const tbody = table.tBodies[0];
      if (!tbody) return;
      const hiddenCols = new Set(V ? V.columnsHiddenFor(table.dataset.tableId) : []);
      groupsOf(tbody).forEach(function (group) {
        total += 1;
        group.forEach(clearMarks);
        const match =
          !query ||
          group.some(function (row) {
            return rowText(row, hiddenCols).indexOf(query) >= 0;
          });
        if (match) shown += 1;
        group.forEach(function (row) {
          if (row.classList.contains("skillrow")) {
            if (!match) row.hidden = true; // parent gone → the nested table goes too
            return; // otherwise the expand toggle owns its visibility
          }
          row.hidden = !match;
          if (match && query) markRow(row, hiddenCols, query);
        });
      });
    });
    if (raw) {
      reg.count.textContent = shown + " of " + total;
      reg.count.hidden = false;
    } else {
      reg.count.hidden = true;
    }
  }

  // Reveal the input (and focus it), or leave it in place while a Filter is set.
  function reveal(id) {
    const reg = sections[id];
    if (!reg) return;
    reg.input.hidden = false;
    reg.input.focus();
  }

  // Wire one Section's signage: the ⌕ button, the input (hidden until asked for or
  // a Filter is set), and the count. Runs after wkxCollapse has rebuilt the signage,
  // so it appends to the heading the collapse toggle already occupies.
  function wire(id) {
    const panelMount = document.getElementById(id);
    const panel = panelMount && panelMount.closest("section");
    const signage = panel && panel.querySelector(".signage");
    if (!signage) return null;

    const find = U.el("button", "signage-find");
    find.type = "button";
    find.textContent = "⌕";
    find.title = "Filter this section";
    find.setAttribute("aria-label", "Filter this section");
    const input = U.el("input", "signage-filter");
    input.type = "search";
    input.hidden = true;
    input.setAttribute("aria-label", "Filter " + id);
    input.placeholder = "filter…";
    const count = U.el("span", "signage-fcount");
    count.hidden = true;

    find.addEventListener("click", function () {
      if (input.hidden) reveal(id);
      else if (!input.value) input.hidden = true;
      else input.focus();
    });
    input.addEventListener("input", function () {
      apply(id);
      if (V) {
        clearTimeout(sections[id].timer);
        sections[id].timer = setTimeout(function () {
          V.setFilter(id, input.value);
        }, WRITE_DELAY);
      }
    });

    signage.append(find, input, count);
    sections[id] = { input: input, count: count, tables: new Set(), timer: 0 };
    return sections[id];
  }

  // Register a table so its Section's Filter narrows it. Re-applies the current
  // Filter so a table that renders after the Filter was set is narrowed at once.
  function register(sectionId, table) {
    const reg = sections[sectionId];
    if (!reg) return;
    reg.tables.add(table);
    apply(sectionId);
  }

  // Adopt the View's saved Filter for a Section: fill the input, reveal it, apply.
  function adopt(id) {
    const reg = sections[id];
    if (!reg || !V) return;
    const saved = V.filterFor(id);
    if (saved) {
      reg.input.value = saved;
      reg.input.hidden = false;
    } else if (!reg.input.value) {
      reg.input.hidden = true;
    }
    apply(id);
  }

  SECTION_IDS.forEach(wire);

  // Adopt saved Filters once the View lands, and re-adopt whenever it changes here
  // or in another tab (a Filter set elsewhere, or a column Hidden that changes what
  // the Filter can reach).
  if (V) {
    V.ready.then(function () {
      SECTION_IDS.forEach(adopt);
    });
    V.onChange(function () {
      SECTION_IDS.forEach(adopt);
    });
  }

  // Re-run every Section's Filter as Flags land (an SSE-raised Flag joins a row's
  // visible text), so a row the Filter dropped can return and one it kept can leave.
  if (flags && flags.subscribe)
    flags.subscribe(function () {
      SECTION_IDS.forEach(apply);
    });

  return { register: register };
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

  // A small, unobtrusive link to a GitHub-hosted item's repository. Only owner
  // and repo ever reach the href, derived credential-stripped on the backend, so
  // the link is safe to show and to share in a screenshot. A non-GitHub item is
  // never passed one, so it shows no link at all.
  function githubLink(href) {
    const link = U.el("a", "gh-link", "↗");
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "Open on GitHub: " + href;
    link.setAttribute("aria-label", "Open on GitHub: " + href);
    return link;
  }

  // The Roadmap cell: a repo's ROADMAP.md task-item progress, sat left of the
  // Flags rail. A repo with no file shows an empty cell; a file with no task items
  // shows the not-applicable glyph; otherwise "ticked / total" with a thin neutral
  // meter beneath (no Flag colour, no --match) and the percentage as the title.
  // data-sort is the ratio, so the column sorts by progress with empty and
  // not-applicable cells sorting last. The cell is not a link and not a token, and
  // its absence is never a Flag.
  function roadmapCell(roadmap) {
    if (!roadmap) {
      const empty = U.td("");
      empty.setAttribute("data-sort", "");
      return empty;
    }
    if (!roadmap.total) {
      const na = U.td(U.dash());
      na.title = "no task items";
      na.setAttribute("data-sort", "");
      return na;
    }
    const ratio = roadmap.ticked / roadmap.total;
    const pct = Math.round(ratio * 100);
    const wrap = U.el("span", "rm");
    wrap.append(U.el("span", "rm-count", roadmap.ticked + " / " + roadmap.total));
    const meter = U.el("span", "rm-meter");
    const fill = U.el("span", "rm-fill");
    fill.style.width = pct + "%";
    meter.append(fill);
    wrap.append(meter);
    const cell = U.td(wrap);
    cell.title = pct + "%";
    cell.setAttribute("data-sort", String(ratio));
    return cell;
  }

  function repoRow(repo) {
    const flags = U.flagCell("workspace:" + repo.path);
    const ahead = U.td(U.quiet("···"), "num");
    const behind = U.td(U.quiet("···"), "num");
    ahead.setAttribute("data-sort", "");
    behind.setAttribute("data-sort", "");
    abCells.set(repo.path, { ahead: ahead, behind: behind });
    const name = U.token("repo", repo.name, "t-name");
    const nameCell = repo.github ? U.td([name, " ", githubLink(repo.github)]) : U.td(name);
    return U.tr([
      nameCell,
      branchCell(repo),
      U.td(repo.upstream ? U.el("span", "q", repo.upstream) : U.dash()),
      ahead,
      behind,
      U.td(workingTree(repo)),
      U.td(repo.stashes > 0 ? String(repo.stashes) : U.quiet("0"), "num"),
      roadmapCell(repo.roadmap),
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
    // One nested detail line spanning the fact columns rather than data spread
    // across columns it has no values for, with a trailing flag cell so a
    // "releases behind" badge lands on the rail beside its parent repo's flags.
    const lead = U.el("span", "sub-lead", sub.name);
    const pinned = subPart("pinned", sub.pinned ? U.token("version", sub.pinned, "ver") : U.quiet("untagged"));
    const latest = subPart("latest", U.quiet("listing…"));
    // The GitHub-blessed release, shown labelled beside the tag-based latest only
    // when the probe finds the two disagree; empty (and separator-free) otherwise,
    // so the common case where they agree stays quiet.
    const release = U.el("span", "sub-release");
    const behind = U.el("span", "sub-part sub-status");
    behind.append(U.dash());

    smRows.set(sub.path, { latest: latest, release: release, behind: behind });

    const parts = [lead];
    if (sub.github) parts.push(sep(), githubLink(sub.github));
    parts.push(sep(), pinned, sep(), latest, release, sep(), behind);
    const cell = U.td(U.cellFlex(parts), "sub-cell");
    cell.colSpan = 8;
    const row = U.el("tr", "subrow");
    // A submodule is a row of the workspace table, not a Section of its own, so its
    // "releases behind" badge is homed on workspace beside its parent repo's flags.
    row.append(cell, U.flagCell("workspace:" + sub.path));
    return row;
  }

  function raiseBehind(repo, behind) {
    if (behind > 0) {
      window.wkxFlags.add({
        section: "workspace",
        target: repo,
        level: "attention",
        category: "behind-remote",
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
    // Homed on workspace, not a submodules Section: submodules are rows of the
    // workspace table, so this badge rides the workspace rail beside its repo.
    if (behind > 0) {
      window.wkxFlags.add({
        section: "workspace",
        target: path,
        level: "attention",
        category: "submodule-tags-behind",
        message: behind === 1 ? "1 release behind" : behind + " releases behind",
      });
    } else {
      window.wkxFlags.clear("workspace", path, "submodule-tags-behind");
    }
  }

  function setLatest(cell, value, muted) {
    cell.replaceChildren(U.el("span", "q", "latest "), muted ? U.quiet(value) : U.token("version", value, "ver"));
  }

  // Surface the GitHub-blessed release beside the tag-based latest only when the
  // backend sent one and it names a different tag; otherwise leave the slot empty
  // so nothing extra is drawn. The backend already keeps the agreeing case quiet;
  // the value check here is the second guard the operator's eye can trust.
  function fillRelease(node, event) {
    if (event.github_release && event.github_release !== event.latest) {
      node.replaceChildren(sep(), U.el("span", "q", "release "), U.token("version", event.github_release, "ver"));
      node.title = "GitHub blesses " + event.github_release + " as its latest release, which differs from the highest tag.";
    } else {
      node.replaceChildren();
      node.removeAttribute("title");
    }
  }

  function fillSubmodule(event) {
    const row = smRows.get(event.submodule);
    if (!row) return;
    row.latest.classList.add("filled");
    fillRelease(row.release, event);
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("workspace", window.wkxCollapse.label(workspace.repos.length, "repo"));
    }
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

    const built = window.wkxTables.mount(
      [
        { label: "Repo" },
        { label: "Branch" },
        { label: "Upstream" },
        { label: "Ahead", num: true },
        { label: "Behind", num: true },
        { label: "Working tree" },
        { label: "Stash", num: true },
        { label: "Roadmap" },
      ],
      "workspace",
    );
    workspace.repos.forEach(function (repo) {
      built.tbody.append(repoRow(repo));
      (subsByRepo.get(repo.path) || []).forEach(function (sub) {
        built.tbody.append(subRow(sub));
      });
    });
    built.equip();

    mount.replaceChildren(summary, built.wrap);
    startStream("/api/workspace/fetch", fillAheadBehind);
    startStream("/api/submodules/probe", fillSubmodule);
  }

  window.wkxSections.whenActive(mount, function () {
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

  // The shared column spec, so every subtable aligns column-for-column. State
  // carries the status word; the drift badges now land on the trailing Flags
  // rail. The widths carry it so all four subtables keep their alignment.
  const COLUMNS = [
    { label: "Name", width: "28%" },
    { label: "Version", width: "16%" },
    { label: "Detail", width: "24%" },
    { label: "State", width: "16%" },
    { label: "Flags", flags: true, width: "16%" },
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
  function nameCell(text, kind) {
    return U.td(U.token(kind, text, "t-name"));
  }
  function verCell(text) {
    return U.td(text ? U.token("version", text, "ver") : U.dash());
  }

  function interpreterTable(python) {
    const built = window.wkxTables.mount(COLUMNS, "toolchains");
    python.interpreters.forEach(function (interp) {
      built.tbody.append(
        U.tr([
          nameCell(interp.implementation, "tool"),
          verCell(interp.version),
          U.td(U.quiet("uv-managed")),
          U.td(interp.installed ? U.ok("installed") : U.quiet("not installed")),
          U.flagCell(),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function pinTable(python) {
    const built = window.wkxTables.mount(COLUMNS, "toolchains");
    python.repo_pins.forEach(function (pin) {
      const matches = pin.version === python.global_pin;
      const state = U.td(U.quiet(matches ? "matches global" : "differs from global"));
      built.tbody.append(
        U.tr([
          nameCell(base(pin.repo), "repo"),
          verCell(pin.version),
          U.td(U.quiet("global " + (python.global_pin || "unset"))),
          state,
          U.flagCell("toolchains:pin:" + pin.repo),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function nodeToolTable(node) {
    const built = window.wkxTables.mount(COLUMNS, "toolchains");
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
      built.tbody.append(
        U.tr([
          nameCell(pair[0], "tool"),
          verCell(tool.version),
          U.td(U.quiet(roles[pair[0]] || "package manager")),
          stateCell,
          U.flagCell(),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function tsTable(node) {
    const built = window.wkxTables.mount(COLUMNS, "toolchains");
    node.repos.forEach(function (repo) {
      const installed = repo.installed;
      const state = U.td(installed ? U.ok("installed") : U.quiet("not installed"));
      if (!installed) state.title = "Install the declared TypeScript: run npm install in the repo.";
      built.tbody.append(
        U.tr([
          nameCell(base(repo.repo), "repo"),
          verCell(installed),
          U.td(U.quiet("declared " + (repo.declared || "none"))),
          state,
          U.flagCell("toolchains:ts:" + repo.repo),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function render(data) {
    const py = data.python;
    const node = data.node;
    if (window.wkxCollapse) {
      window.wkxCollapse.count("toolchains", window.wkxCollapse.label(py.interpreters.length, "interpreter"));
    }
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

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/toolchains")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not load toolchains. Check that the board is still running.");
      });
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

  // Shared shape for both skill subsections, so their columns line up. State
  // keeps the enabled/disabled word; the disabled/shadow badges land on the
  // trailing Flags rail.
  const SKILL_COLUMNS = [
    { label: "Skill", width: "22%" },
    { label: "Origin", width: "18%" },
    { label: "State", width: "12%" },
    { label: "Description", width: "34%" },
    { label: "Flags", flags: true, width: "14%" },
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
    cell.colSpan = 7;
    cell.append(inner);
    const row = U.el("tr", "skillrow");
    row.hidden = true;
    row.append(cell);
    return row;
  }

  function pluginTable(plugins, skillsByOrigin) {
    const built = window.wkxTables.mount(
      [
        { label: "Plugin" },
        { label: "Marketplace" },
        { label: "Repo" },
        { label: "Version" },
        { label: "State" },
        { label: "Skills", num: true },
      ],
      "claude-plugins",
    );
    plugins.forEach(function (plugin) {
      const skills = skillsByOrigin.get(plugin.name + "@" + plugin.marketplace) || [];
      const hasSkills = skills.length > 0;

      const nameCell = U.el("td");
      if (hasSkills) nameCell.append(U.el("span", "exp-caret", "▸"));
      nameCell.append(U.el("span", "t-name", plugin.name));

      const state = U.td(U.quiet(plugin.enabled ? "enabled" : "disabled"));

      const countCell = U.td(hasSkills ? String(skills.length) : U.quiet("—"), "num");
      countCell.setAttribute("data-sort", String(skills.length));

      const row = U.tr([
        nameCell,
        U.td(plugin.marketplace, "q"),
        U.td(plugin.repo ? plugin.repo : U.dash(), "q"),
        U.td(plugin.version === "unknown" ? U.quiet("unknown") : U.token("version", plugin.version, "ver")),
        state,
        countCell,
        U.flagCell("claude:plugin:" + plugin.name),
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
    built.equip();
    return built.wrap;
  }

  // The State word is the skill's own state: "disabled" when it is off, the
  // visibility tier (name-only, user-invocable-only) when it is enabled but
  // restricted, and "enabled" otherwise. Only "disabled" carries a Flag.
  function skillStateWord(skill) {
    if (!skill.enabled) return "disabled";
    if (skill.visibility) return skill.visibility;
    return "enabled";
  }

  // The State cell: the state word, plus a quiet "plugin disabled" note when a
  // plugin skill's owning plugin is off. A plugin skill has no switch of its own,
  // so it stays enabled; the note explains why it will not run, with no badge.
  function skillStateCell(skill) {
    const cell = U.td(U.quiet(skillStateWord(skill)));
    if (skill.plugin_enabled === false) {
      cell.append(U.el("div", "skill-plugin-note", "plugin disabled"));
    }
    return cell;
  }

  function skillTable(skills, originText) {
    const built = window.wkxTables.mount(SKILL_COLUMNS, "claude-skills");
    skills.forEach(function (skill) {
      const state = skillStateCell(skill);
      const desc = skill.description ? U.el("div", "clamp2", skill.description) : U.dash();
      if (skill.description) desc.title = skill.description;
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", skill.name)),
          U.td(originText(skill), "q"),
          state,
          U.td(desc),
          U.flagCell("claude:skill:" + skill.name),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function mcpTable(servers) {
    const built = window.wkxTables.mount(
      [{ label: "Server" }, { label: "Origin" }, { label: "Transport" }, { label: "Auth" }],
      "claude-mcp",
    );
    servers.forEach(function (server) {
      const auth = U.td(U.quiet(server.needs_auth ? "needs auth" : "ready"));
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", server.name)),
          U.td(server.origin, "q"),
          U.td(server.transport, "q"),
          auth,
          U.flagCell("claude:mcp:" + server.name),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  function render(data) {
    const skills = data.skills || [];
    const plugins = data.plugins || [];
    const servers = data.mcp_servers || [];
    if (window.wkxCollapse) {
      window.wkxCollapse.count("claude", window.wkxCollapse.label(plugins.length, "plugin"));
    }
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

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/claude")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not load the Claude environment. Check that the board is still running.");
      });
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("system", window.wkxCollapse.label(tools.length, "tool"));
    }
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

    const built = window.wkxTables.mount([{ label: "Tool" }, { label: "Version" }], "system-tools");
    tools.forEach(function (tool) {
      const flags = U.flagCell("system:" + tool.name);
      const versionCell = U.td(tool.present && tool.version ? U.token("version", tool.version, "ver") : U.dash());
      if (!tool.present) versionCell.title = "Install it: brew install " + tool.name + " (or uv tool install " + tool.name + ").";
      built.tbody.append(U.tr([U.td(U.token("tool", tool.name, "t-name")), versionCell, flags]));
    });
    built.equip();

    mount.replaceChildren(summary, built.wrap);
  }

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/system")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not load system tools. Check that the board is still running.");
      });
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
    const built = window.wkxTables.mount(
      [{ label: "Package" }, { label: "Installed" }, { label: "Current" }],
      "homebrew-packages",
    );
    packages.forEach(function (pkg) {
      const flags = U.flagCell("homebrew:" + kind + ":" + pkg.name);
      built.tbody.append(
        U.tr([
          U.td(U.token("tool", pkg.name, "t-name")),
          U.td(U.el("span", "from", pkg.installed || "—")),
          U.td(U.el("span", "to", pkg.current || "—")),
          flags,
        ]),
      );
    });
    built.equip();
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("homebrew", total + " outdated");
    }
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

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/homebrew")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not load Homebrew. Check that the board is still running.");
      });
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("docker", reachable ? "daemon up" : "daemon down");
    }
    // Tiles only, no table: the daemon tile is the M6 flag host, and a down
    // daemon shows its facts as "—" rather than as meaningless zeros.
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

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/docker")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not load Docker. Check that the board is still running.");
      });
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("footprint", window.wkxCollapse.label(repos.length, "repo") + " measured");
    }
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

    const built = window.wkxTables.mount(
      [
        { label: "Repo" },
        { label: ".venv", num: true },
        { label: "node_modules", num: true },
        { label: "Total", num: true },
      ],
      "footprint",
    );
    repos.forEach(function (repo) {
      const totalCell = U.td(U.el("span", "ver", repo.total), "num");
      totalCell.setAttribute("data-sort", String(repo.total_bytes));
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", repo.path)),
          sizeCell(repo.venv),
          sizeCell(repo.node_modules),
          totalCell,
          U.flagCell(),
        ]),
      );
    });
    built.equip();

    mount.replaceChildren(summary, built.wrap);
  }

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/footprint")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not measure the disk footprint. Check that the board is still running.");
      });
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("editor", window.wkxCollapse.label(extensions.length, "extension"));
    }
    const summary = U.tiles([
      { value: data.version || "unknown", label: "VS Code" },
      { value: String(extensions.length), label: "Extensions" },
    ]);
    if (extensions.length === 0) {
      mount.replaceChildren(summary, U.summaryLine(["VS Code is installed but reports no extensions."]));
      return;
    }
    const built = window.wkxTables.mount(
      [{ label: "Extension" }, { label: "Version", num: true }],
      "editor-extensions",
    );
    extensions.forEach(function (ext) {
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", ext.id)),
          U.td(ext.version ? U.token("version", ext.version, "ver") : U.dash(), "num"),
          U.flagCell(),
        ]),
      );
    });
    built.equip();
    mount.replaceChildren(summary, built.wrap);
  }

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/editor")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not read the editor. Check that the board is still running.");
      });
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
    if (window.wkxCollapse) {
      window.wkxCollapse.count("git-config", window.wkxCollapse.label(entries.length, "key"));
    }

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
      const built = window.wkxTables.mount(
        [{ label: "Key" }, { label: "Value" }, { label: "Origin" }],
        "git-config-keys",
      );
      entries.forEach(function (entry) {
        built.tbody.append(
          U.tr([
            keyCell(entry),
            valueCell(entry),
            U.td(U.el("span", "q", entry.origin)),
            U.flagCell("git-config:" + entry.key),
          ]),
        );
      });
      built.equip();
      nodes.push(built.wrap);
    }

    if (includes.length > 0) {
      nodes.push(U.el("p", "sub-head", "Includes (" + includes.length + ")"));
      const built = window.wkxTables.mount(
        [{ label: "Condition" }, { label: "Path" }, { label: "State" }],
        "git-config-includes",
      );
      includes.forEach(function (inc) {
        const status = inc.exists ? U.td(U.ok("found")) : U.td(U.el("span", "q", "missing"));
        built.tbody.append(
          U.tr([
            U.td(inc.condition ? U.el("span", "ver", inc.condition) : U.quiet("always")),
            U.td(U.el("span", "t-name", inc.path)),
            status,
            U.flagCell("git-config:" + inc.path),
          ]),
        );
      });
      built.equip();
      nodes.push(built.wrap);
    }

    mount.replaceChildren.apply(mount, nodes);
  }

  window.wkxSections.whenActive(mount, function () {
    fetch("/api/git-config")
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        note("Could not read the git config. Check that the board is still running.");
      });
  });
})();

// ---------- config ----------
// The board describing itself: the effective configuration that shapes every
// other Section. Its one distinctive idea is provenance — every value carries
// where it came from (default, file, or env), shown the wkx way, by weight and a
// small mono label, never by hue: a computed default reads recessive, a value the
// operator set through the file or the environment reads at full weight, so a
// glance down the Source column separates what is customised from what runs on
// defaults. Colour stays reserved for the Flag layer. The discovery Excludes, Off
// Sections, and Mutes each get their own table here beside system tools.
(function () {
  "use strict";

  const U = window.wkxUI;
  const mount = document.getElementById("config");
  if (!mount) return;

  function note(message) {
    mount.replaceChildren(U.summaryLine([message]));
  }

  // The provenance marker: "default" recessive, "file"/"env" at full weight, so a
  // customised value stands out from a computed default without any colour.
  function sourceCell(source) {
    const known = source === "file" || source === "env";
    const span = U.el("span", "src src--" + (known ? source : "default"), source);
    return U.td(span);
  }

  function settingsTable(values) {
    const built = window.wkxTables.mount(
      [{ label: "Setting" }, { label: "Value" }, { label: "Source" }],
      "config-settings",
    );
    values.forEach(function (item) {
      built.tbody.append(
        U.tr([
          U.td(U.el("span", "t-name", item.key)),
          U.td(U.el("span", "ver", item.value)),
          sourceCell(item.source),
          U.flagCell(),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  // The discovery Exclude globs, the list-shaped setting that shapes which repos
  // reach the board at all. Each glob is the ~-relative pattern the operator wrote;
  // a matching directory is pruned from discovery, so an excluded repo is absent
  // and raises no Flags (Exclude, not a mute). A path-like value, shown the wkx way.
  function excludesTable(globs) {
    const built = window.wkxTables.mount([{ label: "Exclude glob" }], "config-excludes");
    globs.forEach(function (glob) {
      built.tbody.append(U.tr([U.td(U.el("span", "ver", glob)), U.flagCell()]));
    });
    built.equip();
    return built.wrap;
  }

  // The system-tools probe list, the first list-shaped setting to get its own
  // table. Each tool name is a token of kind "tool", so it lights up with the same
  // tool wherever it appears in the system Section and beyond.
  function toolsTable(tools) {
    const built = window.wkxTables.mount(
      [{ label: "Tool" }, { label: "Version probe" }],
      "config-tools",
    );
    tools.forEach(function (tool) {
      const probe = (tool.version_args && tool.version_args.length ? tool.version_args : ["--version"]).join(" ");
      built.tbody.append(
        U.tr([
          U.td(U.token("tool", tool.name, "t-name")),
          U.td(U.el("span", "q", probe)),
          U.flagCell(),
        ]),
      );
    });
    built.equip();
    return built.wrap;
  }

  // The Off Sections, the second list-shaped setting to get its own table. Each is
  // a Section the operator switched off, so its panel and route are gone and it
  // raises no Flags; naming them here is the one place the board still accounts for
  // a Section it otherwise drops entirely.
  function offTable(sections) {
    const built = window.wkxTables.mount([{ label: "Section" }], "config-off");
    sections.forEach(function (name) {
      built.tbody.append(U.tr([U.td(U.el("span", "t-name", name)), U.flagCell()]));
    });
    built.equip();
    return built.wrap;
  }

  // The Mute rules, read from the View now (ADR 0004): Mute moved out of the
  // configuration into the board's own file. Each rule names a Flag Category to
  // silence; a target narrows it to one item's exact wire value, an empty target
  // mutes the whole Category. Muting is a view preference, so a muted Flag is
  // dropped from the badges and the tally but stays on /api/flags — this table is
  // where the operator sees what they silenced.
  function mutesTable(rules) {
    const built = window.wkxTables.mount(
      [{ label: "Category" }, { label: "Target" }],
      "config-mutes",
    );
    rules.forEach(function (rule) {
      const target = rule.target ? U.el("span", "ver", rule.target) : U.quiet("whole category");
      built.tbody.append(
        U.tr([U.td(U.el("span", "t-name", rule.category)), U.td(target), U.flagCell()]),
      );
    });
    built.equip();
    return built.wrap;
  }

  // The View-file line: where the board writes its View, and whether the file is
  // loaded, absent, or not writable. It is the host for the two View Flags
  // (view-not-saved, view-unknown-key), so it carries a data-flag-key the Flag
  // layer badges — the flag key is set on a <p>, never on a table element.
  function viewFileLine(state) {
    let parts;
    if (!state.file) {
      parts = ["The board writes its View to its own file; none is configured here."];
    } else if (state.found && state.writable) {
      parts = ["The board writes its View to ", U.el("span", "ver", state.file), "."];
    } else if (state.found && !state.writable) {
      parts = [
        U.el("span", "ver", state.file),
        " is not writable; a change cannot be saved until it is.",
      ];
    } else if (!state.found && state.writable) {
      parts = [
        "No View file yet; it appears at ",
        U.el("span", "ver", state.file),
        " on your first change.",
      ];
    } else {
      parts = [
        U.el("span", "ver", state.file),
        " is absent and its directory is not writable; a change cannot be saved.",
      ];
    }
    const line = U.summaryLine(parts);
    line.dataset.flagKey = "config:view-file";
    return line;
  }

  function render(data) {
    const values = data.values || [];
    if (window.wkxCollapse) {
      window.wkxCollapse.count("config", window.wkxCollapse.label(values.length, "setting"));
    }
    const tools = (data.system_tools && data.system_tools.tools) || [];
    const toolsSource = (data.system_tools && data.system_tools.source) || "default";
    const excludes = (data.exclude && data.exclude.globs) || [];
    const excludeSource = (data.exclude && data.exclude.source) || "default";
    const off = (data.sections_off && data.sections_off.sections) || [];
    const offSource = (data.sections_off && data.sections_off.source) || "default";
    // Mutes and the View-file state come from the View, not the configuration.
    const mutes = window.wkxView ? window.wkxView.mute() : [];
    const viewState = window.wkxView
      ? window.wkxView.fileState()
      : { file: null, found: false, writable: false, unknown_keys: [] };
    // Customised and From-environment count the scalar settings AND every
    // list-shaped block (system tools, Excludes, Off Sections), so a config that
    // customises only, say, sections_off is never reported as nothing changed.
    const blockSources = [toolsSource, excludeSource, offSource];
    const customised =
      values.filter(function (item) {
        return item.source !== "default";
      }).length +
      blockSources.filter(function (source) {
        return source !== "default";
      }).length;
    const envCount =
      values.filter(function (item) {
        return item.source === "env";
      }).length +
      blockSources.filter(function (source) {
        return source === "env";
      }).length;

    const summary = U.tiles([
      { value: data.found ? "loaded" : "defaults", label: "Config file" },
      { value: String(customised), label: "Customised" },
      { value: String(envCount), label: "From environment" },
      { value: String(tools.length), label: "System tools" },
      { value: String(off.length), label: "Off Sections" },
      { value: String(mutes.length), label: "Mutes" },
    ]);

    // Name the file and whether it was found, so the operator knows exactly which
    // file the board read (or that it is running entirely on computed defaults).
    const fileLine = data.file
      ? data.found
        ? U.summaryLine(["Read from ", U.el("span", "ver", data.file), "."])
        : U.summaryLine([
            "No ",
            U.el("span", "ver", data.file),
            " found; every value below is a computed default.",
          ])
      : U.summaryLine(["Running on computed defaults; no configuration file is in use."]);

    const nodes = [
      summary,
      fileLine,
      viewFileLine(viewState),
      U.el("p", "sub-head", "Settings"),
      settingsTable(values),
    ];
    if (excludes.length > 0) {
      nodes.push(
        U.el("p", "sub-head", "Excludes (" + excludes.length + ") · " + excludeSource),
        excludesTable(excludes),
      );
    } else {
      nodes.push(
        U.el("p", "sub-head", "Excludes · " + excludeSource),
        U.summaryLine(["No discovery Excludes are configured; every repository under the scan roots is shown."]),
      );
    }
    nodes.push(U.el("p", "sub-head", "System tools (" + tools.length + ") · " + toolsSource), toolsTable(tools));
    nodes.push(U.el("p", "sub-head", "Off Sections (" + off.length + ") · " + offSource));
    nodes.push(
      off.length > 0
        ? offTable(off)
        : U.summaryLine(["No Sections are off; every Section is on the board."]),
    );
    nodes.push(U.el("p", "sub-head", "Mutes (" + mutes.length + ") · from the View"));
    nodes.push(
      mutes.length > 0
        ? mutesTable(mutes)
        : U.summaryLine(["No Flags are muted; every Flag badges its row and counts in the tally."]),
    );

    mount.replaceChildren.apply(mount, nodes);
  }

  // The boot gate already fetched /api/config to learn the Off Sections, so this
  // panel renders from that one body rather than fetching the same endpoint again;
  // the Mutes and the View-file line come from the View wkxView already read.
  window.wkxSections.whenActive(mount, function () {
    const data = window.wkxSections.config();
    if (data) {
      render(data);
    } else {
      note("Could not read the configuration. Check that the board is still running.");
    }
  });
})();
