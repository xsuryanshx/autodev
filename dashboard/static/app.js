/* AutoDev Dashboard — vanilla JS + SSE client */
(function () {
  "use strict";

  // ── Constants ──────────────────────────────────────────
  var PHASES = [
    { num: 1, name: "Parse" },
    { num: 2, name: "Validate" },
    { num: 3, name: "Explore" },
    { num: 4, name: "Plan" },
    { num: 5, name: "Implement" },
    { num: 6, name: "Merge" },
    { num: 7, name: "Review" },
    { num: 8, name: "Report" },
  ];

  var AGENT_COLORS = ["tag-0", "tag-1", "tag-2", "tag-3", "tag-4"];
  var DOT_COLORS = ["#42a5f5", "#66bb6a", "#ce93d8", "#ffb74d", "#f48fb1"];

  // ── State ──────────────────────────────────────────────
  var state = {
    sessionId: null,
    issueTitle: null,
    startedAt: null,
    currentPhase: 0,
    completedPhases: {},
    agents: {},
    files: {},
    cost: { total_tokens: 0, total_cost: 0, by_model: {} },
    agentIndex: {},
  };

  // ── DOM helpers ────────────────────────────────────────
  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "className") node.className = attrs[k];
        else if (k === "textContent") node.textContent = attrs[k];
        else if (k === "title") node.title = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (children) {
      children.forEach(function (c) {
        if (typeof c === "string") node.appendChild(document.createTextNode(c));
        else if (c) node.appendChild(c);
      });
    }
    return node;
  }

  function clearChildren(parent) {
    while (parent.firstChild) parent.removeChild(parent.firstChild);
  }

  // ── Init ───────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    buildStepper();
    connectSSE();
    startElapsedTimer();
  });

  // ── Pipeline Stepper ───────────────────────────────────
  function buildStepper() {
    var container = $("stepper");
    clearChildren(container);

    PHASES.forEach(function (p, i) {
      var step = el("div", { className: "step", "data-phase": String(p.num) }, [
        el("span", { className: "step-num", textContent: String(p.num) }),
        el("span", { className: "step-label", textContent: p.name }),
      ]);
      container.appendChild(step);

      if (i < PHASES.length - 1) {
        container.appendChild(el("span", { className: "step-arrow", textContent: "\u203a" }));
      }
    });
  }

  function updateStepper() {
    var steps = document.querySelectorAll(".step");
    steps.forEach(function (stepEl) {
      var num = parseInt(stepEl.getAttribute("data-phase"), 10);
      stepEl.classList.remove("completed", "active");

      if (state.completedPhases[num]) {
        stepEl.classList.add("completed");
        stepEl.querySelector(".step-num").textContent = "\u2713";
      } else if (num === state.currentPhase) {
        stepEl.classList.add("active");
      }
    });
  }

  // ── SSE Connection ─────────────────────────────────────
  function connectSSE() {
    var badge = $("connection-status");
    var source = new EventSource("/events");

    source.onopen = function () {
      badge.textContent = "Connected";
      badge.className = "badge badge-connected";
    };

    source.onerror = function () {
      badge.textContent = "Reconnecting\u2026";
      badge.className = "badge badge-error";
    };

    source.onmessage = function (e) {
      try {
        var event = JSON.parse(e.data);
        handleEvent(event);
      } catch (err) {
        // Ignore malformed events
      }
    };
  }

  // ── Event Router ───────────────────────────────────────
  function handleEvent(event) {
    var type = event.event_type || "";

    if (type === "snapshot") {
      applySnapshot(event.data);
      return;
    }

    addEventToFeed(event);

    switch (type) {
      case "session.start":
        state.sessionId = (event.data || {}).session_id || event.session_id;
        state.issueTitle = (event.data || {}).issue || "";
        state.startedAt = event.timestamp;
        updateHeader();
        break;
      case "phase.enter":
        state.currentPhase = event.phase || (event.data || {}).phase || 0;
        updateStepper();
        break;
      case "phase.exit":
        state.completedPhases[event.phase || (event.data || {}).phase || 0] = true;
        updateStepper();
        break;
      case "agent.dispatch":
        upsertAgent(event, "running");
        break;
      case "agent.progress":
        updateAgentProgress(event);
        break;
      case "agent.complete":
        upsertAgent(event, "completed");
        break;
      case "agent.error":
        upsertAgent(event, "error");
        break;
      case "file.write":
        recordFileWrite(event);
        break;
      case "token.usage":
        recordTokenUsage(event);
        break;
    }
  }

  // ── Snapshot ───────────────────────────────────────────
  function applySnapshot(snap) {
    if (!snap) return;
    state.sessionId = snap.session_id;
    state.issueTitle = snap.issue;
    state.startedAt = snap.started_at;
    state.currentPhase = snap.phase || 0;

    if (snap.agents) {
      Object.keys(snap.agents).forEach(function (id) {
        state.agents[id] = snap.agents[id];
      });
    }
    if (snap.files) state.files = snap.files;
    if (snap.cost) state.cost = snap.cost;

    updateHeader();
    updateStepper();
    renderAgentCards();
    renderFileHeatmap();
    renderCost();
  }

  // ── Header ─────────────────────────────────────────────
  function updateHeader() {
    $("session-id").textContent = state.sessionId || "\u2014";
    $("issue-title").textContent = state.issueTitle || "\u2014";
  }

  // ── Elapsed Timer ──────────────────────────────────────
  function startElapsedTimer() {
    setInterval(function () {
      if (!state.startedAt) return;
      var start = new Date(state.startedAt).getTime();
      var diff = Math.floor((Date.now() - start) / 1000);
      var h = Math.floor(diff / 3600);
      var m = Math.floor((diff % 3600) / 60);
      var s = diff % 60;
      var parts = [];
      if (h > 0) parts.push(h + "h");
      if (m > 0 || h > 0) parts.push(m + "m");
      parts.push(s + "s");
      $("elapsed-time").textContent = parts.join(" ");
    }, 1000);
  }

  // ── Agent Cards ────────────────────────────────────────
  function getAgentColorIdx(agentId) {
    if (!(agentId in state.agentIndex)) {
      state.agentIndex[agentId] = Object.keys(state.agentIndex).length;
    }
    return state.agentIndex[agentId] % AGENT_COLORS.length;
  }

  function upsertAgent(event, status) {
    var data = event.data || {};
    var agentId = data.agent_id || data.task_id || event.source || "unknown";

    if (!state.agents[agentId]) {
      state.agents[agentId] = {
        agent_id: agentId,
        status: status,
        feature: data.feature || data.feature_id || "",
        subtasks_done: 0,
        subtasks_total: data.subtasks_total || 0,
        started_at: event.timestamp,
      };
    }
    state.agents[agentId].status = status;
    if (data.error) state.agents[agentId].error = data.error;
    renderAgentCards();
  }

  function updateAgentProgress(event) {
    var data = event.data || {};
    var agentId = data.agent_id || data.task_id || event.source || "unknown";
    if (state.agents[agentId]) {
      state.agents[agentId].subtasks_done = data.subtasks_done || 0;
      state.agents[agentId].subtask = data.subtask || "";
      renderAgentCards();
    }
  }

  function renderAgentCards() {
    var container = $("agent-cards");
    clearChildren(container);
    var ids = Object.keys(state.agents);

    if (ids.length === 0) {
      container.appendChild(el("div", { className: "empty-state", textContent: "No agents dispatched yet." }));
      return;
    }

    ids.forEach(function (id) {
      var a = state.agents[id];
      var done = a.subtasks_done || 0;
      var total = a.subtasks_total || 0;
      var pct = total > 0 ? Math.round((done / total) * 100) : (a.status === "completed" ? 100 : 0);

      var fill = el("div", { className: "progress-fill" });
      fill.style.width = pct + "%";

      var card = el("div", { className: "agent-card" }, [
        el("div", { className: "agent-card-header" }, [
          el("span", { className: "agent-name", textContent: a.feature || id }),
          el("span", { className: "agent-status status-" + (a.status || "waiting"), textContent: a.status || "waiting" }),
        ]),
        el("div", { className: "agent-meta", textContent: done + "/" + total + " subtasks" }),
        el("div", { className: "progress-bar" }, [fill]),
        el("div", { className: "agent-time", textContent: id }),
      ]);

      container.appendChild(card);
    });
  }

  // ── Event Feed ─────────────────────────────────────────
  function addEventToFeed(event) {
    var feed = $("event-feed");
    var empty = feed.querySelector(".empty-state");
    if (empty) empty.remove();

    var source = event.source || "system";
    var colorIdx = source === "orchestrator" ? -1 : getAgentColorIdx(source);
    var tagClass = colorIdx === -1 ? "tag-orchestrator" : AGENT_COLORS[colorIdx];
    var ts = (event.timestamp || "").substring(11, 19) || "--:--:--";
    var msg = formatEventMessage(event);

    var line = el("div", { className: "event-line" }, [
      el("span", { className: "event-time", textContent: ts }),
      el("span", { className: "event-source " + tagClass, textContent: source }),
      el("span", { className: "event-msg", textContent: msg }),
    ]);

    feed.insertBefore(line, feed.firstChild);

    // Keep max 200 entries
    while (feed.children.length > 200) {
      feed.removeChild(feed.lastChild);
    }
  }

  function formatEventMessage(event) {
    var type = event.event_type || "";
    var data = event.data || {};
    switch (type) {
      case "phase.enter": return "Entering phase " + event.phase + ": " + (data.phase_name || "");
      case "phase.exit": return "Phase " + event.phase + " complete (" + (data.duration_seconds || 0).toFixed(1) + "s)";
      case "agent.dispatch": return "Dispatched: " + (data.feature_id || data.task_id || "");
      case "agent.start": return "Started working";
      case "agent.progress": return "Progress: " + (data.subtask || "") + " (" + (data.subtasks_done || 0) + "/" + (data.subtasks_total || "?") + ")";
      case "agent.complete": return "Completed";
      case "agent.error": return "Error: " + (data.error || "unknown");
      case "file.write": return "Wrote " + (data.path || "");
      case "file.read": return "Read " + (data.path || "");
      case "test.pass": return "Tests passed (" + (data.count || 0) + ")";
      case "test.fail": return "Tests failed (" + (data.count || 0) + ")";
      case "merge.conflict": return "Conflict: " + (data.path || "");
      case "review.verdict": return "Verdict: " + (data.verdict || "");
      default: return type;
    }
  }

  // ── File Heatmap ───────────────────────────────────────
  function recordFileWrite(event) {
    var data = event.data || {};
    var path = data.path || "unknown";
    var agentId = data.agent_id || event.source || "unknown";
    if (!state.files[path]) state.files[path] = [];
    if (state.files[path].indexOf(agentId) === -1) {
      state.files[path].push(agentId);
    }
    renderFileHeatmap();
  }

  function renderFileHeatmap() {
    var container = $("file-heatmap");
    clearChildren(container);
    var paths = Object.keys(state.files).sort();

    if (paths.length === 0) {
      container.appendChild(el("div", { className: "empty-state", textContent: "No file writes yet." }));
      return;
    }

    paths.forEach(function (path) {
      var agents = state.files[path];
      var isConflict = agents.length > 1;

      var dots = agents.map(function (aid) {
        var ci = getAgentColorIdx(aid);
        var dot = el("span", { className: "file-agent-dot", title: aid });
        dot.style.background = DOT_COLORS[ci];
        return dot;
      });

      var label = path + (isConflict ? " \u26a0\ufe0f" : "");
      var row = el("div", { className: "file-row" + (isConflict ? " conflict" : "") }, [
        el("span", { className: "file-path", textContent: label }),
        el("span", { className: "file-agents" }, dots),
      ]);
      container.appendChild(row);
    });
  }

  // ── Cost Tracker ───────────────────────────────────────
  function recordTokenUsage(event) {
    var data = event.data || {};
    var model = data.model || "unknown";
    var tokens = (data.input_tokens || 0) + (data.output_tokens || 0);
    var cost = data.cost || 0;

    state.cost.total_tokens += tokens;
    state.cost.total_cost += cost;
    if (!state.cost.by_model[model]) {
      state.cost.by_model[model] = { tokens: 0, cost: 0 };
    }
    state.cost.by_model[model].tokens += tokens;
    state.cost.by_model[model].cost += cost;
    renderCost();
  }

  function renderCost() {
    $("total-tokens").textContent = state.cost.total_tokens.toLocaleString();
    $("total-cost").textContent = "$" + state.cost.total_cost.toFixed(4);

    var bd = $("cost-breakdown");
    clearChildren(bd);
    var models = Object.keys(state.cost.by_model);

    models.forEach(function (m) {
      var info = state.cost.by_model[m];
      bd.appendChild(el("div", { className: "cost-row" }, [
        el("span", { className: "cost-model", textContent: m }),
        el("span", { className: "cost-amount", textContent: info.tokens.toLocaleString() + " tok \u2014 $" + info.cost.toFixed(4) }),
      ]));
    });
  }
})();
