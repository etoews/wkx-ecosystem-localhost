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

// Workspace Section: fetch /api/workspace and render the discovered repos, then
// open an SSE stream that fills each repo's ahead/behind in as its background
// fetch lands. Values arrive already redacted and home-relative; the only
// sensitive value on the page is each email's raw form, revealed on demand.
(function () {
  "use strict";

  const mount = document.getElementById("workspace");
  if (!mount) return;

  // Each repo's ahead/behind chip, keyed by its home-relative path, so an SSE
  // event can fill the right row once its background fetch lands.
  const abChips = new Map();

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

    row.append(aheadBehindChip(repo));
    return row;
  }

  function aheadBehindChip(repo) {
    // Starts as a quiet placeholder and is filled when the repo's background
    // fetch lands over SSE. Colour stays reserved for M6 Flags, so the counts
    // read by glyph and weight (the stat-tile idiom), never by hue.
    const chip = el("span", "ws-chip ws-chip--ab ws-chip--muted");
    chip.append(el("span", "num", "↕"), " ", el("span", "lbl", "fetching…"));
    chip.title = "Ahead/behind arrives from a background fetch, streamed over SSE.";
    abChips.set(repo.path, chip);
    return chip;
  }

  function setChip(chip, glyph, label, muted) {
    chip.classList.toggle("ws-chip--muted", muted);
    chip.replaceChildren(el("span", "num", glyph), " ", el("span", "lbl", label));
  }

  function fillAheadBehind(event) {
    const chip = abChips.get(event.repo);
    if (!chip) return;
    chip.classList.add("ws-chip--filled");
    if (event.unknown) {
      setChip(chip, "↕", "fetch unknown", true);
      chip.title = "The background fetch could not reach the remote; it may need credentials.";
      return;
    }
    if (event.ahead == null && event.behind == null) {
      setChip(chip, "↕", "no upstream", true);
      chip.title = "This branch has no upstream to compare against.";
      return;
    }
    if (event.ahead === 0 && event.behind === 0) {
      setChip(chip, "↕", "level since last fetch", false);
    } else {
      const parts = [];
      if (event.ahead > 0) parts.push("↑" + event.ahead);
      if (event.behind > 0) parts.push("↓" + event.behind);
      setChip(chip, parts.join(" "), "since last fetch", false);
    }
    chip.title = "Commits ahead of and behind the upstream, since the last background fetch.";
  }

  function startFetchStream() {
    // Native EventSource only: no library. The server closes the stream with a
    // "done" event once every repo has reported, so this runs exactly once per
    // load rather than reconnecting in a loop.
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/workspace/fetch");
    source.addEventListener("message", function (message) {
      try {
        fillAheadBehind(JSON.parse(message.data));
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
    card.dataset.repo = repo.path;
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
    abChips.clear();
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
    startFetchStream();
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

// Submodules Section: fetch /api/submodules and render each submodule with its
// locally-resolved pin, then open an SSE stream that fills each row's latest
// release and tags-behind as its remote tag listing lands. Values arrive
// home-relative; drift reads by weight and count, never colour, which stays
// reserved for the M6 Flag layer.
(function () {
  "use strict";

  const mount = document.getElementById("submodules");
  if (!mount) return;

  // Per submodule, the chips the SSE probe fills, keyed by home-relative path so
  // an event settles into the right row once its remote tag listing lands.
  const rows = new Map();

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "sm-note", message));
  }

  function countChip(n, label) {
    // Stat-tile idiom (dataviz skill): the magnitude is the loud element, the
    // label stays recessive, and no hue is spent here.
    const chip = el("span", "sm-chip");
    chip.append(el("span", "num", String(n)), " ", el("span", "lbl", label));
    return chip;
  }

  function pinnedChip(sub) {
    const chip = el("span", "sm-chip");
    if (sub.pinned) {
      chip.append(el("span", "lbl", "pinned"), " ", el("span", "num", sub.pinned));
      chip.title = "The version the parent repo pins this submodule at.";
    } else {
      chip.classList.add("sm-chip--muted");
      chip.append(el("span", "lbl", "pinned"), " ", el("span", "num", "untagged"));
      chip.title = "The pinned commit is not on or after any tag.";
    }
    return chip;
  }

  function latestChip() {
    // Quiet placeholder until the remote tag listing lands over SSE.
    const chip = el("span", "sm-chip sm-chip--latest sm-chip--muted");
    chip.append(el("span", "lbl", "latest"), " ", el("span", "num", "listing…"));
    chip.title = "The latest release arrives from a remote tag listing, streamed over SSE.";
    return chip;
  }

  function setLatest(chip, value, muted, title) {
    chip.classList.toggle("sm-chip--muted", muted);
    chip.replaceChildren(el("span", "lbl", "latest"), " ", el("span", "num", value));
    chip.title = title;
  }

  function fill(event) {
    const row = rows.get(event.submodule);
    if (!row) return;
    row.chips.classList.add("sm-chips--filled");
    // Drop any prior drift chip so a repeated event stays idempotent.
    if (row.behind && row.behind.parentNode) row.behind.remove();
    row.behind = null;

    if (event.unknown) {
      setLatest(row.latest, "listing unknown", true, "The remote tags could not be listed; it may need credentials.");
      return;
    }
    if (event.latest == null) {
      setLatest(row.latest, "no releases", true, "The remote lists no version tags.");
      return;
    }
    setLatest(row.latest, event.latest, false, "The highest stable release the remote lists.");

    if (event.behind == null) {
      // Latest is known, but the pin is untagged so a distance cannot be computed.
      return;
    }
    if (event.behind === 0) {
      row.behind = el("span", "sm-chip sm-chip--behind sm-chip--muted");
      row.behind.append(el("span", "num", "on latest"));
      row.behind.title = "The pinned commit is the latest release.";
    } else {
      const label = event.behind === 1 ? "release behind" : "releases behind";
      row.behind = countChip(event.behind, label);
      row.behind.classList.add("sm-chip--behind");
      row.behind.title = "How many releases the pinned commit sits below the latest.";
    }
    row.chips.append(row.behind);
  }

  function subCard(sub) {
    const card = el("div", "sm-card");
    card.dataset.sub = sub.path;
    const head = el("div", "sm-head");
    head.append(el("span", "sm-name", sub.name), el("span", "sm-path", sub.path));
    const ctx = el("div", "sm-ctx");
    ctx.append(el("span", "sm-eyebrow", "in"), el("span", "sm-repo", sub.repo));
    const chips = el("div", "sm-chips");
    const latest = latestChip();
    chips.append(pinnedChip(sub), latest);
    rows.set(sub.path, { chips: chips, latest: latest, behind: null });
    card.append(head, ctx, chips);
    return card;
  }

  function startProbeStream() {
    // Native EventSource only, matching the workspace fetch stream. The server
    // closes with a "done" event once every submodule has reported, so this runs
    // once per load rather than reconnecting.
    if (typeof EventSource === "undefined") return;
    const source = new EventSource("/api/submodules/probe");
    source.addEventListener("message", function (message) {
      try {
        fill(JSON.parse(message.data));
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

  function render(data) {
    const subs = data.submodules;
    if (!subs || subs.length === 0) {
      note("No submodules in the discovered repositories.");
      return;
    }
    rows.clear();
    const summary = el("p", "sm-note");
    summary.append(
      el("span", "sm-count", String(subs.length)),
      subs.length === 1 ? " submodule across the workspace" : " submodules across the workspace",
    );
    const grid = el("div", "sm-grid");
    subs.forEach(function (sub) {
      grid.append(subCard(sub));
    });
    mount.replaceChildren(summary, grid);
    startProbeStream();
  }

  fetch("/api/submodules")
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(render)
    .catch(function () {
      note("Could not load submodules. Check that the board is still running.");
    });
})();

// Toolchains Section: fetch /api/toolchains and render the Python and the
// Node/TypeScript facts side by side. Facts only, no judgement: drift between a
// declared and an installed version reads by weight and adjacency, and an absent
// tool reads as a plain "absent" fact. Colour stays reserved for the M6 Flag
// layer, so nothing here is told apart by hue.
(function () {
  "use strict";

  const mount = document.getElementById("toolchains");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "tc-note", message));
  }

  // Stat-tile idiom (dataviz skill): the version is the loud element and its
  // label stays recessive. No hue is spent — that channel is the M6 Flag layer's.
  function valueChip(label, value, opts) {
    const options = opts || {};
    const chip = el("span", "tc-chip");
    if (options.muted) chip.classList.add("tc-chip--muted");
    if (options.labelFirst) {
      chip.append(el("span", "lbl", label), " ", el("span", "num", value));
    } else {
      chip.append(el("span", "num", value), " ", el("span", "lbl", label));
    }
    if (options.title) chip.title = options.title;
    return chip;
  }

  function toolChip(tool) {
    if (tool.present && tool.version) {
      return valueChip(tool.name, tool.version, { labelFirst: true });
    }
    return valueChip(tool.name, "absent", {
      labelFirst: true,
      muted: true,
      title: tool.name + " is not installed on this machine.",
    });
  }

  function group(title, body) {
    const wrap = el("div", "tc-group");
    wrap.append(el("p", "tc-group-head", title));
    wrap.append(body);
    return wrap;
  }

  function chipRow(children) {
    const row = el("div", "tc-chips");
    children.forEach(function (child) {
      row.append(child);
    });
    return row;
  }

  function mutedLine(text) {
    return el("p", "tc-muted", text);
  }

  function pinRows(pins) {
    const rows = el("div", "tc-rows");
    pins.forEach(function (pin) {
      const row = el("div", "tc-row");
      row.append(el("span", "tc-repo", pin.repo), valueChip("pin", pin.version, { labelFirst: true }));
      rows.append(row);
    });
    return rows;
  }

  function tsRows(repos) {
    const rows = el("div", "tc-rows");
    repos.forEach(function (repo) {
      const row = el("div", "tc-row");
      row.append(el("span", "tc-repo", repo.repo));
      const chips = el("span", "tc-chips");
      chips.append(
        repo.declared
          ? valueChip("declared", repo.declared, { labelFirst: true })
          : valueChip("declared", "none", { labelFirst: true, muted: true }),
      );
      chips.append(
        repo.installed
          ? valueChip("installed", repo.installed, { labelFirst: true })
          : valueChip("installed", "not installed", {
              labelFirst: true,
              muted: true,
              title: "This repo declares TypeScript but has not installed it.",
            }),
      );
      row.append(chips);
      rows.append(row);
    });
    return rows;
  }

  function pythonLane(python) {
    const lane = el("div", "tc-lane");
    lane.append(el("p", "tc-lane-head", "python"));

    const interpreters =
      python.interpreters.length > 0
        ? chipRow(
            python.interpreters.map(function (interp) {
              return valueChip(interp.implementation, interp.version, {
                title: interp.path || undefined,
              });
            }),
          )
        : mutedLine("No uv-managed interpreters.");
    lane.append(group("uv interpreters", interpreters));

    const pins = chipRow([
      python.global_pin
        ? valueChip("global pin", python.global_pin, { labelFirst: true })
        : valueChip("global pin", "unset", { labelFirst: true, muted: true }),
      toolChip(python.system),
    ]);
    lane.append(group("global pin · system", pins));

    lane.append(
      group(
        "repo pins",
        python.repo_pins.length > 0 ? pinRows(python.repo_pins) : mutedLine("No repo pins a version."),
      ),
    );
    return lane;
  }

  function nodeLane(node) {
    const lane = el("div", "tc-lane");
    lane.append(el("p", "tc-lane-head", "node · typescript"));

    lane.append(group("global", chipRow([toolChip(node.node), toolChip(node.npm), toolChip(node.tsc)])));

    lane.append(
      group(
        "package managers",
        node.package_managers.length > 0
          ? chipRow(node.package_managers.map(toolChip))
          : mutedLine("None present besides npm."),
      ),
    );

    lane.append(
      group(
        "typescript per repo",
        node.repos.length > 0 ? tsRows(node.repos) : mutedLine("No repo declares TypeScript."),
      ),
    );
    return lane;
  }

  function render(data) {
    const lanes = el("div", "tc-lanes");
    lanes.append(pythonLane(data.python), nodeLane(data.node));
    mount.replaceChildren(lanes);
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

// System Section: fetch /api/system and render each configured developer CLI as
// present-with-version or missing. The tools shown are whatever the machine
// configured, in order, so the panel grows with configuration alone. Facts only:
// a missing tool reads as a plain "missing" fact, told apart by weight and label,
// never by hue, which stays reserved for the M6 Flag layer.
(function () {
  "use strict";

  const mount = document.getElementById("system");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "sy-note", message));
  }

  // Stat-tile idiom (dataviz skill): the tool name labels, the version is the
  // loud element. A missing tool is the same tile, quietened and reading
  // "missing" in place of a version, so presence tells by weight, not colour.
  function toolChip(tool) {
    const present = tool.present && tool.version;
    const chip = el("span", "sy-chip");
    if (!present) chip.classList.add("sy-chip--muted");
    chip.append(
      el("span", "lbl", tool.name),
      " ",
      el("span", "num", present ? tool.version : "missing"),
    );
    chip.title = present
      ? tool.name + " " + tool.version
      : tool.name + " is not installed on this machine.";
    return chip;
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
    const summary = el("p", "sy-note");
    summary.append(
      el("span", "sy-count", String(present)),
      " of ",
      el("span", "sy-count", String(tools.length)),
      " present",
    );
    const grid = el("div", "sy-chips");
    tools.forEach(function (tool) {
      grid.append(toolChip(tool));
    });
    mount.replaceChildren(summary, grid);
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

// Claude Section: fetch /api/claude and render skills, plugins, and MCP servers,
// each grouped by the one fact that ties this Section together — its Origin. Every
// asset installed is shown; enabled/disabled and auth-needed are quiet facts told
// apart by weight, an eyebrow, and a muted tag, never by hue, which stays reserved
// for the M6 Flag layer. Values arrive already home-relative and carry no secrets:
// an MCP server is a name, an Origin, a transport, and an auth flag, never its
// command, URL, headers, or environment.
(function () {
  "use strict";

  const mount = document.getElementById("claude");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "cl-note", message));
  }

  function count(n, ...rest) {
    const p = el("p", "cl-lane-count");
    p.append(el("span", "cl-count", String(n)), " " + rest.join(""));
    return p;
  }

  function lane(title, subtitle) {
    const wrap = el("div", "cl-lane");
    const head = el("div", "cl-lane-head");
    head.append(el("span", "cl-lane-name", title));
    wrap.append(head, subtitle);
    return wrap;
  }

  // The Origin is the structural spine: an eyebrow that reads "user", "project",
  // or the "<plugin>@<marketplace>" pair verbatim.
  function origin(text) {
    return el("span", "cl-origin", text);
  }

  function tag(label, muted) {
    return el("span", "cl-tag" + (muted ? " cl-tag--muted" : ""), label);
  }

  // Group a list by a key so each Origin's assets cluster under one heading.
  function groupBy(items, keyOf) {
    const order = [];
    const map = new Map();
    items.forEach(function (item) {
      const key = keyOf(item);
      if (!map.has(key)) {
        map.set(key, []);
        order.push(key);
      }
      map.get(key).push(item);
    });
    return order.map(function (key) {
      return { key: key, items: map.get(key) };
    });
  }

  function skillsLane(skills) {
    const body = el("div", "cl-groups");
    groupBy(skills, function (s) {
      return s.origin;
    }).forEach(function (grp) {
      const block = el("div", "cl-group");
      const head = el("div", "cl-group-head");
      head.append(origin(grp.key));
      // Skills share their owning plugin's enabled state, so a disabled origin is
      // marked once on the group rather than on every skill.
      if (grp.items.length > 0 && !grp.items[0].enabled) head.append(tag("disabled", true));
      block.append(head);
      const names = el("div", "cl-chips");
      grp.items.forEach(function (skill) {
        const chip = el("span", "cl-chip", skill.name);
        if (skill.description) chip.title = skill.description;
        names.append(chip);
      });
      block.append(names);
      body.append(block);
    });
    const enabled = skills.filter(function (s) {
      return s.enabled;
    }).length;
    const summary =
      enabled === skills.length
        ? count(skills.length, skills.length === 1 ? " skill" : " skills")
        : count(enabled, " of " + skills.length + " active");
    const wrap = lane("skills", summary);
    wrap.append(body);
    return wrap;
  }

  function pluginRow(plugin) {
    const row = el("div", "cl-row");
    const line = el("div", "cl-row-main");
    line.append(el("span", "cl-name", plugin.name));
    line.append(el("span", "cl-ver", plugin.version));
    if (!plugin.enabled) line.append(tag("disabled", true));
    row.append(line);
    const meta = el("div", "cl-row-meta");
    meta.append(origin(plugin.marketplace));
    if (plugin.repo) {
      const repo = el("span", "cl-repo", plugin.repo);
      repo.title = "Marketplace GitHub repo";
      meta.append(repo);
    }
    row.append(meta);
    return row;
  }

  function pluginsLane(plugins) {
    const body = el("div", "cl-rows");
    plugins.forEach(function (plugin) {
      body.append(pluginRow(plugin));
    });
    const enabled = plugins.filter(function (p) {
      return p.enabled;
    }).length;
    const wrap = lane("plugins", count(enabled, " of " + plugins.length + " enabled"));
    wrap.append(body);
    return wrap;
  }

  function mcpRow(server) {
    const row = el("div", "cl-row");
    const line = el("div", "cl-row-main");
    line.append(el("span", "cl-name", server.name));
    line.append(el("span", "cl-transport", server.transport));
    if (server.needs_auth) line.append(tag("auth needed", true));
    row.append(line);
    const meta = el("div", "cl-row-meta");
    meta.append(origin(server.origin));
    row.append(meta);
    return row;
  }

  function mcpLane(servers) {
    const body = el("div", "cl-rows");
    servers.forEach(function (server) {
      body.append(mcpRow(server));
    });
    const auth = servers.filter(function (s) {
      return s.needs_auth;
    }).length;
    const summary =
      auth > 0
        ? count(servers.length, servers.length === 1 ? " server, " : " servers, ", auth + " need auth")
        : count(servers.length, servers.length === 1 ? " server" : " servers");
    const wrap = lane("mcp servers", summary);
    wrap.append(body);
    return wrap;
  }

  function emptyLane(title, message) {
    const wrap = lane(title, el("p", "cl-muted", message));
    return wrap;
  }

  function render(data) {
    const skills = data.skills || [];
    const plugins = data.plugins || [];
    const servers = data.mcp_servers || [];
    if (skills.length === 0 && plugins.length === 0 && servers.length === 0) {
      note("No Claude skills, plugins, or MCP servers found.");
      return;
    }
    const lanes = el("div", "cl-lanes");
    lanes.append(
      skills.length > 0 ? skillsLane(skills) : emptyLane("skills", "No skills installed."),
      plugins.length > 0 ? pluginsLane(plugins) : emptyLane("plugins", "No plugins installed."),
      servers.length > 0 ? mcpLane(servers) : emptyLane("mcp servers", "No MCP servers configured."),
    );
    mount.replaceChildren(lanes);
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

// Homebrew Section: fetch /api/homebrew and render the outdated formulae and casks
// as two grouped lists with a headline count. Facts only: an outdated package is a
// version bump (installed → current), told apart by weight and adjacency, never by
// hue, which stays reserved for the M6 Flag layer. Homebrew's absence is a plain
// fact, not an error.
(function () {
  "use strict";

  const mount = document.getElementById("homebrew");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "hb-note", message));
  }

  // One outdated package: its name, then the bump from the installed version to
  // the current one. The current version is the loud element (the target of the
  // upgrade); the installed version stays recessive.
  function pkgRow(pkg) {
    const row = el("div", "hb-row");
    row.append(el("span", "hb-name", pkg.name));
    const bump = el("span", "hb-bump");
    bump.append(
      el("span", "hb-from", pkg.installed || "—"),
      el("span", "hb-arrow", "→"),
      el("span", "hb-to", pkg.current || "—"),
    );
    row.append(bump);
    return row;
  }

  function group(label, packages) {
    const wrap = el("div", "hb-group");
    const head = el("p", "hb-group-head");
    head.append(el("span", "hb-count", String(packages.length)), " " + label);
    wrap.append(head);
    const rows = el("div", "hb-rows");
    packages.forEach(function (pkg) {
      rows.append(pkgRow(pkg));
    });
    wrap.append(rows);
    return wrap;
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
      note("Every formula and cask is up to date.");
      return;
    }
    const summary = el("p", "hb-note");
    summary.append(
      el("span", "hb-count", String(total)),
      total === 1 ? " package outdated" : " packages outdated",
    );
    const groups = el("div", "hb-groups");
    if (formulae.length > 0) groups.append(group("formulae", formulae));
    if (casks.length > 0) groups.append(group("casks", casks));
    mount.replaceChildren(summary, groups);
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

// Docker Section: fetch /api/docker and render the daemon state with a small row
// of stat tiles — containers, images, and reclaimable disk. A daemon that cannot
// be reached renders as a fact, never an error: the down state is stated plainly
// and the meaningless zero counts are withheld rather than shown as real. Colour
// stays reserved for the M6 Flag layer, so reachable and down are told apart by
// weight and label, never by hue.
(function () {
  "use strict";

  const mount = document.getElementById("docker");
  if (!mount) return;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function note(message) {
    mount.replaceChildren(el("p", "dk-note", message));
  }

  // Stat-tile idiom (dataviz skill): the figure is the loud element, its label
  // recessive. No hue is spent — that channel is the M6 Flag layer's.
  function tile(value, label, title) {
    const cell = el("div", "dk-tile");
    cell.append(el("span", "dk-num", value), el("span", "dk-lbl", label));
    if (title) cell.title = title;
    return cell;
  }

  // The daemon fact as an eyebrow pill: reachable or unreachable, told apart by
  // weight and word, not colour.
  function daemon(reachable) {
    const pill = el("div", "dk-daemon" + (reachable ? "" : " dk-daemon--down"));
    pill.append(
      el("span", "dk-daemon-lbl", "daemon"),
      el("span", "dk-daemon-state", reachable ? "reachable" : "unreachable"),
    );
    return pill;
  }

  function render(data) {
    const reachable = data.daemon_reachable;
    const wrap = el("div", "dk-wrap");
    wrap.append(daemon(reachable));
    if (!reachable) {
      wrap.append(
        el(
          "p",
          "dk-muted",
          "The Docker daemon is not reachable. Start Docker to see containers, images, and reclaimable disk.",
        ),
      );
      mount.replaceChildren(wrap);
      return;
    }
    const tiles = el("div", "dk-tiles");
    tiles.append(
      tile(
        data.containers_running + " / " + data.containers_total,
        "containers running / total",
        data.containers_running + " running of " + data.containers_total + " total",
      ),
      tile(String(data.images), data.images === 1 ? "image" : "images"),
      tile(
        data.reclaimable != null ? data.reclaimable : "unknown",
        "reclaimable",
        data.reclaimable != null
          ? "Disk that pruning could reclaim, summed across images, containers, volumes, and build cache."
          : "The reclaimable disk could not be read.",
      ),
    );
    wrap.append(tiles);
    mount.replaceChildren(wrap);
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
