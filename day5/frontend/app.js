"use strict";

var ui = {
  serverStatus: document.getElementById("serverStatus"),
  configStatus: document.getElementById("configStatus"),
  modelStatus: document.getElementById("modelStatus"),
  versionStatus: document.getElementById("versionStatus"),
  materialVersionStatus: document.getElementById("materialVersionStatus"),
  decisionQuestionText: document.getElementById("decisionQuestionText"),
  singleModeBtn: document.getElementById("singleModeBtn"),
  multiModeBtn: document.getElementById("multiModeBtn"),
  modeDescription: document.getElementById("modeDescription"),

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
  similarityScore: document.getElementById("similarityScore"),
  similarityBar: document.getElementById("similarityBar"),
  similarityLevel: document.getElementById("similarityLevel"),
  similarityTurn: document.getElementById("similarityTurn"),
  similarityExcerpt: document.getElementById("similarityExcerpt"),
  evaluatorPanel: document.getElementById("evaluatorPanel"),
  evaluatorScore: document.getElementById("evaluatorScore"),
  evaluatorSummary: document.getElementById("evaluatorSummary"),
  evaluatorStrength: document.getElementById("evaluatorStrength"),
  evaluatorImprove: document.getElementById("evaluatorImprove"),
  evaluatorSimilarity: document.getElementById("evaluatorSimilarity"),
  participantNameInput: document.getElementById("participantNameInput"),
  observationInput: document.getElementById("observationInput"),
  bbbPreview: document.getElementById("bbbPreview"),
  bbbStatus: document.getElementById("bbbStatus"),
  copyBbbBtn: document.getElementById("copyBbbBtn"),
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
  history: [],
  mode: "single",
  lastSimilarity: null,
  lastEvaluation: null,
  currentChoice: "",
  lastInstructionChange: "Not changed in this run",
  lastMaterialChange: "Not changed in this run",
  agentExplanation: "",
  bbbExplanationSource: "",
  bbbExplanationWarning: ""
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
  ui.copyBbbBtn.disabled = appState.busy || anyDirty;
  ui.chooseGuidedBtn.disabled = appState.busy || anyDirty;
  ui.chooseInstructorBtn.disabled = appState.busy || anyDirty;
  ui.singleModeBtn.disabled = appState.busy || anyDirty;
  ui.multiModeBtn.disabled = appState.busy || anyDirty;

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

  renderBbbPreview();
}

function setBusy(value) {
  appState.busy = value;
  updateControls();
}

function loadChoice(option) {
  if (hasDraftChanges()) return;
  appState.currentChoice = option;
  ui.messageInput.value =
    "I choose " + option + ". Help me justify this choice with two supporting points and one limitation using the learning card.";
  ui.messageInput.focus();
  renderBbbPreview();
}

function inferChoiceFromMessage(message) {
  var lower = (message || "").toLowerCase();
  if (lower.indexOf("guided dialogue") >= 0) return "Guided dialogue";
  if (lower.indexOf("working with an instructor") >= 0) return "Working with an instructor";
  return "";
}

function toolCallCount() {
  return appState.events.filter(function(event) {
    return event.event_type === "tool_call" && event.status === "completed";
  }).length;
}

function summarizeMaterialChanges(before, after) {
  if (!before || !after) return "Learning card applied";

  var labels = [];
  if (before.learning_goal !== after.learning_goal) labels.push("Learning goal");
  if (before.guided_supporting_points !== after.guided_supporting_points) labels.push("Guided dialogue — supporting points");
  if (before.guided_limitation !== after.guided_limitation) labels.push("Guided dialogue — limitation");
  if (before.instructor_supporting_points !== after.instructor_supporting_points) labels.push("Working with an instructor — supporting points");
  if (before.instructor_limitation !== after.instructor_limitation) labels.push("Working with an instructor — limitation");

  return labels.length ? labels.join("; ") : "No content change";
}

function buildBbbResult() {
  var participant = ui.participantNameInput ? ui.participantNameInput.value.trim() : "";
  var observation = ui.observationInput ? ui.observationInput.value.trim() : "";
  var tools = toolCallCount();
  var completedTurns = appState.history.filter(function(item) {
    return item.role === "assistant";
  }).length;

  return [
    "DAY 5 RESULT",
    "",
    "Participant: " + (participant || "Not entered"),
    "Choice: " + (appState.currentChoice || "Not recorded"),
    "Agent mode: " + (appState.mode === "multi" ? "Multi-Agent" : "Single Agent"),
    "",
    "Tool used: " + (tools > 0 ? "Yes" : "No"),
    "Tool calls: " + tools,
    "Completed chat turns: " + completedTurns,
    "Latest prompt similarity: " + (
      appState.lastSimilarity
        ? appState.lastSimilarity.score + "% (" + appState.lastSimilarity.level + ")"
        : "Not compared yet"
    ),
    "",
    "Instruction change: " + appState.lastInstructionChange,
    "Instruction version: " + (appState.instructionVersion || "—"),
    "",
    "Learning-card change: " + appState.lastMaterialChange,
    "Card version: " + (appState.materialVersion || "—"),
    "",
    "Observation: " + (observation || "Not entered"),
    "",
    appState.mode === "multi"
      ? "Evaluator Agent: " + (
          appState.lastEvaluation && appState.lastEvaluation.score !== undefined
            ? "Score " + (appState.lastEvaluation.score === null ? "—" : appState.lastEvaluation.score + "/100") +
              "; " + (appState.lastEvaluation.summary || "No summary")
            : "No completed evaluation yet"
        )
      : "Evaluator Agent: Off (Single Agent mode)",
    "",
    "Agent explanation:",
    appState.agentExplanation || "Generated when you press Copy Result for BBB.",
    "Explanation source: " + (appState.bbbExplanationSource || "Not generated yet"),
    appState.bbbExplanationWarning ? "Fallback reason: " + appState.bbbExplanationWarning : "",
    "",
    "Evidence: technical fields are generated from the currently applied/tested state; the explanation is generated by Groq when available, otherwise by the local evidence fallback."
  ].join("\n");
}

function renderBbbPreview() {
  if (!ui.bbbPreview) return;
  ui.bbbPreview.textContent = buildBbbResult();
}

async function copyResultForBbb() {
  if (hasDraftChanges() || appState.busy) return;

  setError("");
  ui.bbbStatus.textContent = "Generating…";
  appState.agentExplanation = "";
  appState.bbbExplanationSource = "";
  appState.bbbExplanationWarning = "";
  setBusy(true);

  try {
    var explanation = await api("/api/bbb/explain", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: appState.sessionId,
        choice: appState.currentChoice,
        instruction_change: appState.lastInstructionChange,
        material_change: appState.lastMaterialChange,
        observation: ui.observationInput.value.trim()
      })
    });

    appState.agentExplanation = explanation.explanation;
    appState.bbbExplanationSource = explanation.source || "unknown";
    appState.bbbExplanationWarning = explanation.warning || "";
    renderBbbPreview();

    await navigator.clipboard.writeText(buildBbbResult());
    ui.bbbStatus.textContent = explanation.source === "groq"
      ? "Copied + AI explanation"
      : "Copied + local explanation";
    ui.bbbStatus.classList.remove("dirty");
    ui.bbbStatus.classList.add("clean");

    if (explanation.source !== "groq") {
      setError(
        "Groq BBB explanation fallback reason: " +
        (explanation.warning || "unknown_provider_error") +
        ". The local evidence-based explanation was copied instead."
      );
    }
  } catch (error) {
    ui.bbbStatus.textContent = "Copy failed";
    ui.bbbStatus.classList.add("dirty");
    setError("Could not prepare or copy the BBB result. Select the preview text and copy it manually.");
  } finally {
    setBusy(false);
  }
}

function renderMode() {
  var multi = appState.mode === "multi";
  ui.singleModeBtn.classList.toggle("active", !multi);
  ui.multiModeBtn.classList.toggle("active", multi);
  ui.evaluatorPanel.hidden = !multi;
  ui.modeDescription.textContent = multi
    ? "Multi-Agent runs the Teaching Agent, then a separate Evaluator Agent assesses the learner's contribution."
    : "Single Agent runs only the Teaching Agent. Prompt Similarity still runs locally before each turn.";
}

function renderSimilarity() {
  var result = appState.lastSimilarity;
  if (!result) {
    ui.similarityScore.textContent = "—";
    ui.similarityBar.style.width = "0%";
    ui.similarityLevel.textContent = "No comparison yet";
    ui.similarityTurn.textContent = "—";
    ui.similarityExcerpt.textContent = "Send at least a second prompt to compare it with an earlier agent response.";
    return;
  }

  ui.similarityScore.textContent = result.score + "%";
  ui.similarityBar.style.width = Math.max(0, Math.min(100, result.score)) + "%";
  ui.similarityLevel.textContent = result.level;
  ui.similarityTurn.textContent = result.matched_turn_id || "No previous match";
  ui.similarityExcerpt.textContent = result.matched_excerpt || result.note || "No matching fragment.";
}

function renderEvaluation() {
  renderMode();
  var evaluation = appState.lastEvaluation;

  if (appState.mode !== "multi") return;

  if (!evaluation) {
    ui.evaluatorScore.textContent = "—";
    ui.evaluatorSummary.textContent = "No evaluation yet.";
    ui.evaluatorStrength.textContent = "—";
    ui.evaluatorImprove.textContent = "—";
    ui.evaluatorSimilarity.textContent = "—";
    return;
  }

  if (evaluation.available === false) {
    ui.evaluatorScore.textContent = "Unavailable";
    ui.evaluatorSummary.textContent = evaluation.message || evaluation.error || "Evaluator Agent was unavailable.";
    ui.evaluatorStrength.textContent = "—";
    ui.evaluatorImprove.textContent = "—";
    ui.evaluatorSimilarity.textContent = "—";
    return;
  }

  ui.evaluatorScore.textContent = evaluation.score === null || evaluation.score === undefined
    ? "—"
    : evaluation.score + "/100";
  ui.evaluatorSummary.textContent = evaluation.summary || "No summary.";
  ui.evaluatorStrength.textContent = evaluation.strength || "—";
  ui.evaluatorImprove.textContent = evaluation.improve || "—";
  ui.evaluatorSimilarity.textContent = evaluation.similarity_note || "—";
}

async function setMode(mode) {
  if (appState.busy || hasDraftChanges() || mode === appState.mode) return;

  setError("");
  setBusy(true);
  try {
    var data = await api("/api/mode", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_id: appState.sessionId,
        mode: mode
      })
    });

    appState.sessionId = data.session_id;
    appState.mode = data.mode;
    appState.history = [];
    appState.events = [];
    appState.lastSimilarity = null;
    appState.lastEvaluation = null;

    renderMessages();
    renderActivity();
    renderSimilarity();
    renderEvaluation();
    renderBbbPreview();
  } catch (error) {
    setError(error.message);
  } finally {
    setBusy(false);
  }
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
      event.event_type === "prompt_similarity" ||
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
    if (event.event_type === "tool_call") {
      title.textContent = "✓ read_course_material";
    } else if (event.event_type === "prompt_similarity") {
      title.textContent = "✓ compare_prompt_similarity";
    } else if (event.event_type === "direct_reply") {
      title.textContent = "Direct response · no model-selected tool";
    } else {
      title.textContent = "Turn failed";
    }

    var line = document.createElement("div");
    line.className = "activity-line";
    line.textContent = (event.turn_id || "turn") + " · " + (event.status || "recorded");

    item.appendChild(title);
    item.appendChild(line);

    if (event.event_type === "tool_call" || event.event_type === "prompt_similarity") {
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
  appState.mode = data.mode || "single";
  appState.lastSimilarity = data.last_similarity || null;
  appState.lastEvaluation = data.evaluations && data.evaluations.length
    ? data.evaluations[data.evaluations.length - 1]
    : null;

  ui.instructionEditor.value = data.instruction;
  ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
  ui.materialVersionStatus.textContent = "Card: " + data.material_version;

  renderMessages();
  renderActivity();
  renderSimilarity();
  renderEvaluation();
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
  var previousVersion = appState.instructionVersion || "—";
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
    appState.lastInstructionChange = "Applied edited instruction (" + previousVersion + " → " + data.instruction_version + ")";
    appState.history = [];
    appState.events = [];
    appState.lastSimilarity = null;
    appState.lastEvaluation = null;
    ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
    renderMessages();
    renderActivity();
    renderSimilarity();
    renderEvaluation();
    renderBbbPreview();
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

  var beforeMaterial = appState.appliedMaterial ? Object.assign({}, appState.appliedMaterial) : null;
  var previousVersion = appState.materialVersion || "—";
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
    appState.lastMaterialChange = summarizeMaterialChanges(beforeMaterial, appState.appliedMaterial) +
      " (" + previousVersion + " → " + data.material_version + ")";
    appState.history = [];
    appState.events = [];
    appState.lastSimilarity = null;
    appState.lastEvaluation = null;

    setMaterialForm(appState.appliedMaterial);
    ui.materialVersionStatus.textContent = "Card: " + data.material_version;
    renderMaterial(data.material);
    renderMessages();
    renderActivity();
    renderSimilarity();
    renderEvaluation();
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

  if (!appState.currentChoice) {
    appState.currentChoice = inferChoiceFromMessage(message);
  }

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
    appState.mode = data.mode || appState.mode;
    appState.lastSimilarity = data.similarity || null;
    appState.lastEvaluation = data.evaluation || null;
    appState.history.push({role: "user", content: message, turn_id: data.turn_id});
    appState.history.push({role: "assistant", content: data.reply, turn_id: data.turn_id});

    ui.messageInput.value = "";
    ui.modelStatus.textContent = "Model: " + data.model;
    ui.versionStatus.textContent = "Instruction: " + data.instruction_version;
    ui.materialVersionStatus.textContent = "Card: " + data.material_version;

    renderMessages();
    renderActivity();
    renderSimilarity();
    renderEvaluation();
    renderBbbPreview();
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
    appState.lastSimilarity = null;
    appState.lastEvaluation = null;
    renderMessages();
    renderActivity();
    renderSimilarity();
    renderEvaluation();
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
    anchor.download = "day5-session-" + appState.sessionId + ".md";
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

ui.singleModeBtn.addEventListener("click", function() { setMode("single"); });
ui.multiModeBtn.addEventListener("click", function() { setMode("multi"); });

ui.chooseGuidedBtn.addEventListener("click", function() { loadChoice("Guided dialogue"); });
ui.chooseInstructorBtn.addEventListener("click", function() { loadChoice("Working with an instructor"); });
ui.sendBtn.addEventListener("click", sendMessage);
ui.clearBtn.addEventListener("click", clearChat);
ui.copyBbbBtn.addEventListener("click", copyResultForBbb);
ui.exportBtn.addEventListener("click", downloadSession);
ui.participantNameInput.addEventListener("input", renderBbbPreview);
ui.observationInput.addEventListener("input", renderBbbPreview);

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
