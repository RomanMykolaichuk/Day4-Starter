"use strict";

var ui = {
  serverStatus: document.getElementById("serverStatus"),
  configStatus: document.getElementById("configStatus"),
  modelStatus: document.getElementById("modelStatus"),
  versionStatus: document.getElementById("versionStatus"),
  materialVersionStatus: document.getElementById("materialVersionStatus"),
  decisionQuestionText: document.getElementById("decisionQuestionText"),

  instructionEditor: document.getElementById("instructionEditor"),
  changeBadge: document.getElementById("changeBadge"),
  draftNote: document.getElementById("draftNote"),
  applyBtn: document.getElementById("applyBtn"),
  restoreBtn: document.getElementById("restoreBtn"),
  discardBtn: document.getElementById("discardBtn"),

  learningGoalInput: document.getElementById("learningGoalInput"),
  guidedSupportingInput: document.getElementById("guidedSupportingInput"),
  guidedLimitationInput: document.getElementById("guidedLimitationInput"),
  instructorSupportingInput: document.getElementById("instructorSupportingInput"),
  instructorLimitationInput: document.getElementById("instructorLimitationInput"),
  materialChangeBadge: document.getElementById("materialChangeBadge"),
  materialDraftNote: document.getElementById("materialDraftNote"),
  applyMaterialBtn: document.getElementById("applyMaterialBtn"),
  restoreMaterialBtn: document.getElementById("restoreMaterialBtn"),
  discardMaterialBtn: document.getElementById("discardMaterialBtn"),

  chooseGuidedBtn: document.getElementById("chooseGuidedBtn"),
  chooseInstructorBtn: document.getElementById("chooseInstructorBtn"),
  clearBtn: document.getElementById("clearBtn"),
  chatLog: document.getElementById("chatLog"),
  errorBox: document.getElementById("errorBox"),
  messageInput: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  sendHint: document.getElementById("sendHint"),

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
  appliedMaterial: null,
  exampleMaterial: null,
  materialVersion: "",
  busy: false,
  events: [],
  history: []
};

function safeErrorMessage(payload, fallback) {
  if (payload && payload.error && payload.error.message) return payload.error.message;
  if (payload && payload.detail && typeof payload.detail === "string") return payload.detail;
  return fallback;
}

async function api(path, options) {
  var response;
  try {
    response = await fetch(path, options || {});
  } catch (error) {
    setServerStatus(false);
    throw new Error("Cannot reach the local backend. Check that the server is running.");
  }

  var data = null;
  if ((response.headers.get("content-type") || "").indexOf("application/json") >= 0) {
    data = await response.json();
  }
  if (!response.ok) throw new Error(safeErrorMessage(data, "The request failed."));
  return data;
}

function setServerStatus(ok) {
  ui.serverStatus.classList.remove("good", "warn", "bad");
  ui.serverStatus.classList.add(ok ? "good" : "bad");
  ui.serverStatus.lastElementChild.textContent = ok ? "Server ready" : "Server offline";
}

function setConfigurationStatus(configured) {
  ui.configStatus.classList.remove("good", "warn", "bad");
  ui.configStatus.classList.add(configured ? "good" : "warn");
  ui.configStatus.lastElementChild.textContent = configured ? "Groq configured" : "Groq setup needed";
}

function setError(message) {
  ui.errorBox.hidden = !message;
  ui.errorBox.textContent = message || "";
}

function currentMaterialForm() {
  return {
    decision_question: appState.appliedMaterial ? appState.appliedMaterial.decision_question : "",
    learning_goal: ui.learningGoalInput.value,
    guided_supporting_points: ui.guidedSupportingInput.value,
    guided_limitation: ui.guidedLimitationInput.value,
    instructor_supporting_points: ui.instructorSupportingInput.value,
    instructor_limitation: ui.instructorLimitationInput.value
  };
}

function sameMaterial(a, b) {
  if (!a || !b) return false;
  return a.learning_goal === b.learning_goal &&
    a.guided_supporting_points === b.guided_supporting_points &&
    a.guided_limitation === b.guided_limitation &&
    a.instructor_supporting_points === b.instructor_supporting_points &&
    a.instructor_limitation === b.instructor_limitation;
}

function isInstructionDirty() {
  return ui.instructionEditor.value !== appState.appliedInstruction;
}

function isMaterialDirty() {
  return !sameMaterial(currentMaterialForm(), appState.appliedMaterial);
}

function hasDraftChanges() {
  return isInstructionDirty() || isMaterialDirty();
}

function setBadge(element, dirty) {
  element.textContent = dirty ? "Draft changes" : "Applied";
  element.classList.toggle("dirty", dirty);
  element.classList.toggle("clean", !dirty);
}

function updateControls() {
  var instructionDirty = isInstructionDirty();
  var materialDirty = isMaterialDirty();
  var anyDirty = instructionDirty || materialDirty;

  setBadge(ui.changeBadge, instructionDirty);
  setBadge(ui.materialChangeBadge, materialDirty);
  ui.draftNote.hidden = !instructionDirty;
  ui.materialDraftNote.hidden = !materialDirty;

  ui.sendBtn.disabled = appState.busy || anyDirty;
  ui.messageInput.disabled = appState.busy || anyDirty;
  ui.clearBtn.disabled = appState.busy || anyDirty;
  ui.exportBtn.disabled = appState.busy || anyDirty;
  ui.chooseGuidedBtn.disabled = appState.busy || anyDirty;
  ui.chooseInstructorBtn.disabled = appState.busy || anyDirty;

  ui.applyBtn.disabled = appState.busy || !instructionDirty;
  ui.restoreBtn.disabled = appState.busy;
  ui.discardBtn.disabled = appState.busy || !instructionDirty;

  ui.applyMaterialBtn.disabled = appState.busy || !materialDirty;
  ui.restoreMaterialBtn.disabled = appState.busy;
  ui.discardMaterialBtn.disabled = appState.busy || !materialDirty;

  if (appState.busy) {
    ui.sendHint.textContent = "Agent is working…";
  } else if (instructionDirty && materialDirty) {
    ui.sendHint.textContent = "Apply or discard both drafts before chatting.";
  } else if (instructionDirty) {
    ui.sendHint.textContent = "Apply or discard instruction changes before chatting.";
  } else if (materialDirty) {
    ui.sendHint.textContent = "Apply or discard learning-card changes before chatting.";
  } else {
    ui.sendHint.textContent = "Enter to send · Shift+Enter for a new line";
  }
}

function setBusy(value) {
  appState.busy = value;
  updateControls();
}

function loadChoice(option) {
  if (hasDraftChanges()) return;
  ui.messageInput.value =
    "I choose " + option + ". Help me justify this choice with two supporting points and one limitation using the learning card.";
  ui.messageInput.focus();
}

function renderMessages() {
  ui.chatLog.textContent = "";

  if (!appState.history.length) {
    var empty = document.createElement("div");
    empty.className = "empty-state";

    var icon = document.createElement("div");
    icon.className = "empty-icon";
    icon.textContent = "A/B";

    var title = document.createElement("h4");
    title.textContent = "Choose one approach above";

    var paragraph = document.createElement("p");
    paragraph.textContent = "Then send the loaded request. Keep the same choice and wording when you compare different instructions and card versions.";

    empty.appendChild(icon);
    empty.appendChild(title);
    empty.appendChild(paragraph);
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
      tag.textContent = "Tool used · applied learning card";
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
    empty.textContent = "A real tool request will appear here when the model asks to read the applied learning card.";
    ui.activityList.appendChild(empty);
    return;
  }

  relevant.forEach(function(event) {
    var item = document.createElement("div");
    item.className = "activity-item" + (event.status === "failed" ? " failed" : "");

    var title = document.createElement("b");
    title.textContent = event.event_type === "tool_call" ?
      "✓ read_course_material" :
      (event.event_type === "direct_reply" ? "Direct response · no tool" : "Turn failed");

    var line = document.createElement("div");
    line.className = "activity-line";
    line.textContent = (event.turn_id || "turn") + " · " + (event.status || "recorded");

    item.appendChild(title);
    item.appendChild(line);

    if (event.event_type === "tool_call") {
      var pre = document.createElement("pre");
      pre.textContent = JSON.stringify(event.result, null, 2);
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

function addPreviewCard(letter, titleText, supporting, limitation) {
  var card = document.createElement("article");
  card.className = "source-card";

  var letterEl = document.createElement("div");
  letterEl.className = "section-letter";
  letterEl.textContent = letter;

  var title = document.createElement("h4");
  title.textContent = titleText;

  var supportLabel = document.createElement("b");
  supportLabel.className = "preview-label";
  supportLabel.textContent = "Supporting points";

  var supportText = document.createElement("p");
  supportText.textContent = supporting;

  var limitationLabel = document.createElement("b");
  limitationLabel.className = "preview-label";
  limitationLabel.textContent = "Limitation";

  var limitationText = document.createElement("p");
  limitationText.textContent = limitation;

  card.appendChild(letterEl);
  card.appendChild(title);
  card.appendChild(supportLabel);
  card.appendChild(supportText);
  card.appendChild(limitationLabel);
  card.appendChild(limitationText);
  ui.sourceCards.appendChild(card);
}

function renderMaterial(material) {
  ui.sourceCards.textContent = "";
  ui.materialMeta.textContent = "course_card · " + material.version;

  var goal = document.createElement("article");
  goal.className = "source-card goal-card";

  var badge = document.createElement("div");
  badge.className = "section-letter";
  badge.textContent = "G";

  var title = document.createElement("h4");
  title.textContent = "Learning goal";

  var text = document.createElement("p");
  text.textContent = material.learning_goal;

  goal.appendChild(badge);
  goal.appendChild(title);
  goal.appendChild(text);
  ui.sourceCards.appendChild(goal);

  addPreviewCard("A", "Guided dialogue", material.guided_supporting_points, material.guided_limitation);
  addPreviewCard("B", "Working with an instructor", material.instructor_supporting_points, material.instructor_limitation);
}

function setMaterialForm(material) {
  ui.learningGoalInput.value = material.learning_goal;
  ui.guidedSupportingInput.value = material.guided_supporting_points;
  ui.guidedLimitationInput.value = material.guided_limitation;
  ui.instructorSupportingInput.value = material.instructor_supporting_points;
  ui.instructorLimitationInput.value = material.instructor_limitation;
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
  appState.materialVersion = data.material_version;
  appState.history = data.history || [];
  appState.events = data.events || [];
  appState.busy = Boolean(data.busy);

  ui.instructionEditor.value = data.instruction;
  ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
  ui.materialVersionStatus.textContent = "Card: " + data.material_version;

  renderMessages();
  renderActivity();
}

async function loadMaterial() {
  var material = await api("/api/material");
  appState.appliedMaterial = {
    decision_question: material.decision_question,
    learning_goal: material.learning_goal,
    guided_supporting_points: material.guided_supporting_points,
    guided_limitation: material.guided_limitation,
    instructor_supporting_points: material.instructor_supporting_points,
    instructor_limitation: material.instructor_limitation
  };
  appState.exampleMaterial = material.example;
  appState.materialVersion = material.version;

  ui.decisionQuestionText.textContent = material.decision_question;
  ui.materialVersionStatus.textContent = "Card: " + material.version;
  setMaterialForm(appState.appliedMaterial);
  renderMaterial(material);
  updateControls();
}

async function applyInstruction() {
  if (!isInstructionDirty()) return;
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

function restoreExampleInstruction() {
  ui.instructionEditor.value = appState.exampleInstruction;
  updateControls();
}

function discardInstructionChanges() {
  ui.instructionEditor.value = appState.appliedInstruction;
  updateControls();
}

async function applyMaterial() {
  if (!isMaterialDirty()) return;
  setError("");
  setBusy(true);

  var form = currentMaterialForm();
  try {
    var data = await api("/api/material", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: appState.sessionId,
        learning_goal: form.learning_goal,
        guided_supporting_points: form.guided_supporting_points,
        guided_limitation: form.guided_limitation,
        instructor_supporting_points: form.instructor_supporting_points,
        instructor_limitation: form.instructor_limitation
      })
    });

    appState.sessionId = data.session_id;
    appState.materialVersion = data.material_version;
    appState.appliedMaterial = {
      decision_question: data.material.decision_question,
      learning_goal: data.material.learning_goal,
      guided_supporting_points: data.material.guided_supporting_points,
      guided_limitation: data.material.guided_limitation,
      instructor_supporting_points: data.material.instructor_supporting_points,
      instructor_limitation: data.material.instructor_limitation
    };
    appState.history = [];
    appState.events = [];

    setMaterialForm(appState.appliedMaterial);
    ui.materialVersionStatus.textContent = "Card: " + data.material_version;
    renderMaterial(data.material);
    renderMessages();
    renderActivity();
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
  }
}

function restoreExampleMaterial() {
  setMaterialForm(appState.exampleMaterial);
  updateControls();
}

function discardMaterialChanges() {
  setMaterialForm(appState.appliedMaterial);
  updateControls();
}

async function sendMessage() {
  var message = ui.messageInput.value.trim();
  if (!message || appState.busy || hasDraftChanges()) return;

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
    appState.history.push({role: "user", content: message, turn_id: data.turn_id});
    appState.history.push({role: "assistant", content: data.reply, turn_id: data.turn_id});

    ui.messageInput.value = "";
    ui.modelStatus.textContent = "Model: " + data.model;
    ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
    ui.materialVersionStatus.textContent = "Card: " + data.material_version;

    renderMessages();
    renderActivity();
  } catch (error) {
    setError(error.message);
    try {
      await loadState();
      await loadMaterial();
    } catch (ignored) {
      setServerStatus(false);
    }
  } finally {
    setBusy(false);
  }
}

async function clearChat() {
  if (hasDraftChanges()) return;
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
  if (hasDraftChanges()) return;
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

[
  ui.learningGoalInput,
  ui.guidedSupportingInput,
  ui.guidedLimitationInput,
  ui.instructorSupportingInput,
  ui.instructorLimitationInput
].forEach(function(element) {
  element.addEventListener("input", updateControls);
});

ui.instructionEditor.addEventListener("input", updateControls);
ui.applyBtn.addEventListener("click", applyInstruction);
ui.restoreBtn.addEventListener("click", restoreExampleInstruction);
ui.discardBtn.addEventListener("click", discardInstructionChanges);

ui.applyMaterialBtn.addEventListener("click", applyMaterial);
ui.restoreMaterialBtn.addEventListener("click", restoreExampleMaterial);
ui.discardMaterialBtn.addEventListener("click", discardMaterialChanges);

ui.chooseGuidedBtn.addEventListener("click", function() { loadChoice("Guided dialogue"); });
ui.chooseInstructorBtn.addEventListener("click", function() { loadChoice("Working with an instructor"); });
ui.sendBtn.addEventListener("click", sendMessage);
ui.clearBtn.addEventListener("click", clearChat);
ui.exportBtn.addEventListener("click", downloadSession);

ui.messageInput.addEventListener("keydown", function(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

async function boot() {
  await loadHealth();
  try {
    await loadState();
    await loadMaterial();
    updateControls();
  } catch (error) {
    setError(error.message);
  }
}

boot();
