# Day 4 Agent Starter

A small, visual local starter for **AI Agents for Defence Education**.

The participant can now change **two parts of the agentic application in the browser**:

1. the agent's teaching instruction;
2. the learning card that the agent can retrieve through its tool.

They then test those changes in Chat using the same baseline request, inspect the real tool activity, and export evidence for comparison.

## What this starter teaches

**LLM + instruction + conversation state + learning material + tool + application rules = an agentic application.**

The starter intentionally keeps the implementation surface small:

- one participant;
- one active local conversation;
- one editable teaching instruction;
- one editable learning card with sections A, B and C;
- one local tool: `read_course_material`;
- one model provider: Groq;
- no database, login, uploads, vector search, React, or multi-agent framework.

## Requirements

- Python 3.12
- Internet access
- personal Groq API key
- instructor-provided Groq model ID with tool calling available

Never paste a real API key into ChatGPT, GitHub issues, commits, or screenshots.

## Windows PowerShell — first launch

Run from the repository root:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8004
~~~

In `.env`, replace only the placeholders:

~~~text
GROQ_API_KEY=your_real_key_here
GROQ_MODEL=the_model_id_provided_by_the_instructor
~~~

Then open:

http://127.0.0.1:8004/

Stop the server with **Ctrl+C**.

## Participant task in Chat

The task is visible directly above the Chat area.

Use the same baseline request for all comparisons:

> My choice is guided dialogue. Help me find two supporting points and one limitation in the course card so I can justify my choice.

### Test 1 — Baseline

1. Keep the example instruction and example learning card.
2. Load or type the baseline request.
3. Send it.
4. Inspect **Tool Activity**.
5. Confirm whether the model actually requested `read_course_material`.
6. Export the baseline session if it is useful.

### Test 2 — Change the agent instruction

1. Change one clear instruction rule, for example the response format.
2. Select **Apply Instruction & Start New Chat**.
3. Repeat exactly the same baseline request.
4. Compare the answer with Test 1.

Example change:

~~~text
Give your feedback as:
1. Strength
2. Missing evidence
3. One question
~~~

### Test 3 — Change the learning card

1. Edit one point in the learning card, for example add, replace, or remove one supporting point or limitation.
2. Keep the required sections **A, B and C**.
3. Select **Apply Card & Start New Chat**.
4. Repeat exactly the same baseline request.
5. Inspect Tool Activity and confirm that the returned card contains your applied change.
6. Compare the answer with Tests 1 and 2.

### Participant outcome

At the end, the participant should be able to explain:

- what changed because of the **agent instruction**;
- what changed because of the **learning card**;
- whether the agent actually used the tool;
- which evidence in Tool Activity supports that explanation.

## Draft and apply logic

Both the instruction and learning card have the same lifecycle:

~~~text
Edit
  ↓
Draft only
  ↓
Apply
  ↓
Persist locally
  ↓
Start fresh chat
  ↓
Test
~~~

Unapplied changes never silently affect a chat request. While either editor has unapplied changes, Chat is disabled. Participants must apply or discard the draft first.

**Restore Example** loads the original example into the editor as a draft. It does not become active until the participant selects Apply.

## Learning card

The immutable example is stored in:

`materials/course_card.md`

The participant's applied local version is stored under ignored runtime data:

`data/course_card.md`

The current card must keep these three headings:

~~~text
## A. ...
## B. ...
## C. ...
~~~

The wording and content inside those sections can be changed during the exercise.

The only tool is:

~~~text
read_course_material(material_id="course_card")
~~~

When the model requests that tool, the backend returns the **currently applied learning card**, not the original repository example and not an unapplied browser draft.

## Agent instruction

The immutable example is stored in:

`defaults/agent_instruction.md`

The participant's applied local version is stored under:

`data/agent_instruction.md`

Applying a new instruction starts a clean chat while keeping the currently applied learning card.

## Export

**Download Session** records:

- application version;
- configured model name;
- applied instruction and its version;
- applied learning card and its version;
- conversation;
- real tool and failure events;
- source commit when available;
- participant observation prompts.

Draft changes are not exported because they have not been applied or tested.

## Configuration and privacy

- `.env` is ignored by Git.
- `.env.example` contains placeholders only.
- credentials are never returned by the API or included in exports;
- frontend rendering uses text-only DOM operations for user/model/tool content;
- only the `frontend/` directory is mounted as static assets;
- model-supplied paths or URLs are never accepted by the learning-card tool.

## Restart behaviour

The applied instruction and applied learning card survive a server restart. Conversation history does **not** survive a server restart; the server creates an empty conversation using the saved instruction and saved card.

## Safe update

Before a workshop session:

~~~powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8004
~~~

Do not use auto-reload during the participant exercise.

## Current implementation scope

This repository is the Day 4 reference starter. Automated smoke checks validate the local application path and editable-card state transitions. Live Groq success still depends on the participant's local API key, current model availability, network access, and the selected model's actual tool-calling behaviour.
