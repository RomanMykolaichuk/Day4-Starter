# Day 4 Agent Starter

A visual local starter for **AI Agents for Defence Education**.

Participants change two parts of the application without editing Python:

- the **agent instruction**;
- the **learning card** available through the agent's tool.

They then use one fixed decision task in Chat and compare the results.

## Core participant question

> **Which approach would you choose to help a learner improve an incomplete justification: Guided dialogue or Working with an instructor? Justify your choice with two supporting points and one limitation.**

The web interface presents two choice buttons:

- **A — Guided dialogue**
- **B — Working with an instructor**

Selecting a choice loads a ready-to-send Chat request. Participants should keep the same choice and request when comparing different configurations.

## Day 4 exercise

### Test 1 — Baseline

1. Keep the example agent instruction and learning card.
2. Choose **Guided dialogue** or **Working with an instructor**.
3. Send the loaded request.
4. Inspect the answer and **Tool Activity**.
5. Confirm whether `read_course_material` was actually used.

### Test 2 — Change the agent

1. Change one instruction rule.
2. Select **Apply Instruction & Start New Chat**.
3. Choose the same option as before.
4. Repeat the same request.
5. Compare the response with Test 1.

### Test 3 — Change the learning card

The learning card is edited through dedicated form fields, not Markdown.

Editable fields are:

- **Learning goal**
- **Guided dialogue — Supporting points**
- **Guided dialogue — Limitation**
- **Working with an instructor — Supporting points**
- **Working with an instructor — Limitation**

Change one field, select **Apply Card & Start New Chat**, then repeat exactly the same choice/request.

## Why the decision question is fixed

The decision question is part of the exercise design rather than an editable source field. This keeps the comparison stable while participants change:

1. **how the agent behaves** through its instruction;
2. **what evidence the agent can retrieve** through its learning card.

## Learning-card storage

The example structured learning card is:

`materials/course_card.json`

A participant's applied local card is saved as:

`data/course_card.json`

The browser shows separate input fields, while the backend stores one structured object and returns that object through:

~~~text
read_course_material(material_id="course_card")
~~~

The tool result contains the current decision question, learning goal, and evidence/limitation for both options.

## Draft / apply behaviour

Instruction edits and learning-card edits remain drafts until explicitly applied.

~~~text
Edit → Draft → Apply → Fresh chat → Test
~~~

While either editor has unapplied changes, Chat is disabled. This prevents a participant from accidentally testing a configuration different from the one shown as applied.

## Requirements and launch

- Python 3.12
- Internet access
- personal Groq API key
- instructor-provided Groq model ID with tool calling available

Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8004
~~~

Then open:

http://127.0.0.1:8004/

Never commit or share a real API key.

## Export

**Download Session** records the decision question, applied instruction, applied structured learning card, conversation, tool activity, versions, and participant reflection prompts.

Live Groq success still depends on the local key, current model availability, network access, and the selected model's tool-calling behaviour.
