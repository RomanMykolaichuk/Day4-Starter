"use strict";

var ui = {
  serverStatus: document.getElementById("serverStatus"),
  configStatus: document.getElementById("configStatus"),
  modelStatus: document.getElementById("modelStatus"),
  versionStatus: document.getElementById("versionStatus"),
  instructionEditor: document.getElementById("instructionEditor"),
  changeBadge: document.getElementById("changeBadge"),
  draftNote: document.getElementById("draftNote"),
  applyBtn: document.getElementById("applyBtn"),
  restoreBtn: document.getElementById("restoreBtn"),
  discardBtn: document.getElementById("discardBtn"),
  clearBtn: document.getElementById("clearBtn"),
  chatLog: document.getElementById("chatLog"),
  emptyState: document.getElementById("emptyState"),
  errorBox: document.getElementById("errorBox"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  sendHint: document.getElementById("sendHint"),
  samplePromptBtn: document.getElementById("samplePromptBtn"),
  sourceCards: document.getElementById("sourceCards"),
  materialMeta: document.getElementById("materialMeta"),
  activityList: document.getElementById("activityList"),
  toolSummary: document.getElementById("toolSummary"),
  exportBtn: document.getElementById("exportBtn")
};

var appState = {
  sessionId: null,
  appliedInstruction: "",
  exampleInstruction: "",
  instructionVersion: "",
  busy: false,
  events: [],
  history: []
};

var samplePrompt = "My choice is guided dialogue. Help me find two supporting points and one limitation in the course card so I can justify my choice.";

function safeErrorMessage(payload, fallback) {
  if (payload && payload.error && payload.error.message) {
    return payload.error.message;
  }
  if (payload && payload.detail) {
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail.error && payload.detail.error.message) {
      return payload.detail.error.message;
    }
    if (Array.isArray(payload.detail) && payload.detail.length) {
      return "Please check the submitted values.";
    }
  }
  return fallback;
}

async function api(path, options) {
  var response;
  try {
    response = await fetch(path, options || {});
  } catch (networkError) {
    setServerStatus(false);
    throw new Error("Cannot reach the local backend. Check that the server is running.");
  }

  var data = null;
  var type = response.headers.get("content-type") || "";
  if (type.indexOf("application/json") >= 0) {
    data = await response.json();
  }

  if (!response.ok) {
    throw new Error(safeErrorMessage(data, "The request failed."));
  }
  return data;
}

function setServerStatus(ok) {
  ui.serverStatus.classList.remove("good", "warn", "bad");
  ui.serverStatus.classList.add(ok ? "good" : "bad");
  ui.serverStatus.firstChild.nextSibling.textContent = ok ? "Server ready" : "Server offline";
}

function setConfigurationStatus(configured) {
  ui.configStatus.classList.remove("good", "warn", "bad");
  ui.configStatus.classList.add(configured ? "good" : "warn");
  ui.configStatus.firstChild.nextSibling.textContent = configured ? "Groq configured" : "Groq setup needed";
}

function setError(message) {
  if (!message) {
    ui.errorBox.hidden = true;
    ui.errorBox.textContent = "";
    return;
  }
  ui.errorBox.textContent = message;
  ui.errorBox.hidden = false;
}

function isDirty() {
  return ui.instructionEditor.value !== appState.appliedInstruction;
}

function updateControls() {
  var dirty = isDirty();
  ui.changeBadge.textContent = dirty ? "Draft changes" : "Applied";
  ui.changeBadge.classList.toggle("dirty", dirty);
  ui.changeBadge.classList.toggle("clean", !dirty);
  ui.draftNote.hidden = !dirty;

  ui.sendBtn.disabled = appState.busy || dirty;
  ui.clearBtn.disabled = appState.busy;
  ui.applyBtn.disabled = appState.busy || !dirty;
  ui.restoreBtn.disabled = appState.busy;
  ui.discardBtn.disabled = appState.busy || !dirty;
  ui.exportBtn.disabled = appState.busy;
  ui.messageInput.disabled = appState.busy || dirty;

  if (appState.busy) {
    ui.sendHint.textContent = "Agent is working…";
  } else if (dirty) {
    ui.sendHint.textContent = "Apply or discard instruction changes before chatting.";
  } else {
    ui.sendHint.textContent = "Enter to send · Shift+Enter for a new line";
  }
}

function setBusy(value) {
  appState.busy = value;
  updateControls();
}

function renderMessages() {
  ui.chatLog.textContent = "";

  if (!appState.history.length) {
    var empty = document.createElement("div");
    empty.className = "empty-state";

    var icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "↗";

    var title = document.createElement("h4");
    title.textContent = "Test the current instruction";

    var paragraph = document.createElement("p");
    paragraph.textContent = "Ask for help with a teaching decision. For a source-based request, the agent can use the approved course card.";

    var chip = document.createElement("button");
    chip.className = "prompt-chip";
    chip.textContent = "Use sample request";
    chip.addEventListener("click", fillSamplePrompt);

    empty.appendChild(icon);
    empty.appendChild(title);
    empty.appendChild(paragraph);
    empty.appendChild(chip);
    ui.chatLog.appendChild(empty);
    return;
  }

  appState.history.forEach(function(item) {
    var wrapper = document.createElement("div");
    wrapper.className = "message " + item.role;

    var meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = item.role === "user" ? "You" : "Agent";

    var bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = item.content;

    wrapper.appendChild(meta);
    wrapper.appendChild(bubble);

    if (item.role === "assistant" && turnUsedTool(item.turn_id)) {
      var tag = document.createElement("span");
      tag.className = "tool-tag";
      tag.textContent = "Tool used · course_card";
      wrapper.appendChild(tag);
    }

    ui.chatLog.appendChild(wrapper);
  });

  ui.chatLog.scrollTop = ui.chatLog.scrollHeight;
}

function turnUsedTool(turnId) {
  return appState.events.some(function(event) {
    return event.turn_id === turnId &&
      event.event_type === "tool_call" &&
      event.status === "completed";
  });
}

function renderActivity() {
  ui.activityList.textContent = "";
  var relevant = appState.events.filter(function(event) {
    return event.event_type === "tool_call" ||
      event.event_type === "turn_failure" ||
      event.event_type === "direct_reply";
  });

  var toolCount = relevant.filter(function(event) {
    return event.event_type === "tool_call";
  }).length;

  ui.toolSummary.textContent = toolCount ?
    String(toolCount) + (toolCount === 1 ? " tool call" : " tool calls") :
    "No tool calls yet";

  if (!relevant.length) {
    var empty = document.createElement("div");
    empty.className = "activity-empty";
    empty.textContent = "A real tool request will appear here when the model asks to read the course card.";
    ui.activityList.appendChild(empty);
    return;
  }

  relevant.forEach(function(event) {
    var item = document.createElement("div");
    item.className = "activity-item" + (event.status === "failed" ? " failed" : "");

    var title = document.createElement("b");
    if (event.event_type === "tool_call") {
      title.textContent = "✓ read_course_material";
    } else if (event.event_type === "direct_reply") {
      title.textContent = "Direct response · no tool";
    } else {
      title.textContent = "Turn failed";
    }

    var line = document.createElement("div");
    line.className = "activity-line";
    line.textContent = (event.turn_id || "turn") + " · " + (event.status || "recorded");

    item.appendChild(title);
    item.appendChild(line);

    if (event.event_type === "tool_call") {
      var pre = document.createElement("pre");
      pre.textContent = JSON.stringify({
        call_id: event.call_id,
        tool_name: event.tool_name,
        arguments: event.arguments,
        result: event.result
      }, null, 2);
      item.appendChild(pre);
    }

    if (event.event_type === "turn_failure") {
      var failure = document.createElement("div");
      failure.className = "activity-line";
      failure.textContent = event.message || event.code || "Agent turn failed.";
      item.appendChild(failure);
    }

    ui.activityList.appendChild(item);
  });
}

function renderMaterial(material) {
  ui.sourceCards.textContent = "";
  ui.materialMeta.textContent = material.material_id + " · " + material.version;

  material.sections.forEach(function(section) {
    var card = document.createElement("article");
    card.className = "source-card";

    var letter = document.createElement("div");
    letter.className = "section-letter";
    letter.textContent = section.label;

    var title = document.createElement("h4");
    title.textContent = section.heading;

    var body = document.createElement("p");
    body.textContent = section.content;

    card.appendChild(letter);
    card.appendChild(title);
    card.appendChild(body);
    ui.sourceCards.appendChild(card);
  });
}

async function loadHealth() {
  try {
    var health = await api("/api/health");
    setServerStatus(true);
    setConfigurationStatus(health.configuration.configured);
    ui.modelStatus.textContent = "Model: " + (health.model || "not configured");
  } catch (error) {
    setConfigurationStatus(false);
    ui.modelStatus.textContent = "Model: —";
  }
}

async function loadState() {
  var data = await api("/api/state");
  appState.sessionId = data.session_id;
  appState.appliedInstruction = data.instruction;
  appState.exampleInstruction = data.example_instruction;
  appState.instructionVersion = data.instruction_version;
  appState.history = data.history || [];
  appState.events = data.events || [];
  appState.busy = Boolean(data.busy);

  ui.instructionEditor.value = data.instruction;
  ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
  renderMessages();
  renderActivity();
  updateControls();
}

async function loadMaterial() {
  try {
    var material = await api("/api/material");
    renderMaterial(material);
  } catch (error) {
    ui.sourceCards.textContent = "";
    var message = document.createElement("div");
    message.className = "activity-empty";
    message.textContent = error.message;
    ui.sourceCards.appendChild(message);
  }
}

async function applyInstruction() {
  if (!isDirty()) return;
  setError("");
  setBusy(true);
  try {
    var data = await api("/api/instructions", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: appState.sessionId,
        instruction: ui.instructionEditor.value
      })
    });
    appState.sessionId = data.session_id;
    appState.appliedInstruction = data.instruction;
    appState.instructionVersion = data.instruction_version;
    appState.history = [];
    appState.events = [];
    ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
    renderMessages();
    renderActivity();
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
  }
}

function restoreExample() {
  ui.instructionEditor.value = appState.exampleInstruction;
  updateControls();
}

function discardChanges() {
  ui.instructionEditor.value = appState.appliedInstruction;
  updateControls();
}

async function sendMessage() {
  var message = ui.messageInput.value.trim();
  if (!message || appState.busy || isDirty()) return;

  setError("");
  setBusy(true);
  try {
    var data = await api("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: appState.sessionId,
        message: message
      })
    });

    appState.events = appState.events.concat(data.events || []);
    appState.history.push({
      role: "user",
      content: message,
      turn_id: data.turn_id
    });
    appState.history.push({
      role: "assistant",
      content: data.reply,
      turn_id: data.turn_id
    });

    ui.messageInput.value = "";
    ui.modelStatus.textContent = "Model: " + data.model;
    ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
    renderMessages();
    renderActivity();
  } catch (error) {
    setError(error.message);
    try {
      await loadState();
    } catch (ignored) {
      setServerStatus(false);
    }
  } finally {
    setBusy(false);
  }
}

async function clearChat() {
  setError("");
  setBusy(true);
  try {
    var data = await api("/api/chat/clear", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session_id: appState.sessionId})
    });
    appState.sessionId = data.session_id;
    appState.history = [];
    appState.events = [];
    renderMessages();
    renderActivity();
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
  }
}

async function downloadSession() {
  setError("");
  setBusy(true);
  try {
    var response = await fetch("/api/export?session_id=" + encodeURIComponent(appState.sessionId));
    if (!response.ok) {
      var payload = null;
      try { payload = await response.json(); } catch (ignored) {}
      throw new Error(safeErrorMessage(payload, "Could not export the session."));
    }
    var blob = await response.blob();
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "day4-session-" + appState.sessionId + ".md";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
  }
}

function fillSamplePrompt() {
  ui.messageInput.value = samplePrompt;
  ui.messageInput.focus();
}

ui.instructionEditor.addEventListener("input", updateControls);
ui.applyBtn.addEventListener("click", applyInstruction);
ui.restoreBtn.addEventListener("click", restoreExample);
ui.discardBtn.addEventListener("click", discardChanges);
ui.sendBtn.addEventListener("click", sendMessage);
ui.clearBtn.addEventListener("click", clearChat);
ui.exportBtn.addEventListener("click", downloadSession);

ui.messageInput.addEventListener("keydown", function(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

if (ui.samplePromptBtn) {
  ui.samplePromptBtn.addEventListener("click", fillSamplePrompt);
}

async function boot() {
  await loadHealth();
  try {
    await Promise.all([loadState(), loadMaterial()]);
  } catch (error) {
    setError(error.message);
  }
}

boot();
