# Day 4 Agent Starter

A small, visual local starter for **AI Agents for Defence Education**.

The participant edits an agent instruction in the browser, applies it to a fresh conversation, chats through Groq, inspects a real local tool call, and exports the session as Markdown.

## What this starter teaches

**LLM + instruction + conversation state + tool + application rules = an agentic application.**

The starter intentionally keeps the implementation surface small:

- one participant;
- one active local conversation;
- one editable teaching instruction;
- one read-only course card;
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

## Day 4 exercise

1. Start the starter and check that the header shows the local server as ready.
2. Use the example instruction and start a fresh chat.
3. Ask: **My choice is guided dialogue. Help me find two supporting points and one limitation in the course card so I can justify my choice.**
4. Open **Tool Activity** and confirm that `read_course_material` was actually requested and returned the course card.
5. Download the baseline session.
6. Change only one rule in the instruction, for example the response format.
7. Select **Apply & Start New Chat**.
8. Repeat exactly the same user request.
9. Compare the two responses and export the second session.
10. Write one sentence explaining what changed.

## Interface logic

The instruction editor is a **draft** until **Apply & Start New Chat** succeeds. While unapplied edits exist, Send is disabled. Applying an instruction saves it locally and creates a fresh conversation. **Clear Chat** creates a fresh conversation using the currently applied instruction.

The browser never sends an arbitrary system message or authoritative conversation history. The backend owns the active instruction, session ID, history, and tool records.

## Course material and tool

The approved source is stored in `materials/course_card.md`.

The only tool is:

~~~text
read_course_material(material_id="course_card")
~~~

The model receives the course-card content only when it requests this tool. The browser also displays the card for the participant, but browser display does not count as a model tool call.

## Configuration and privacy

- `.env` is ignored by Git.
- `.env.example` contains placeholders only.
- credentials are never returned by the API or included in exports;
- frontend rendering uses text-only DOM operations for user/model/tool content;
- only the `frontend/` directory is mounted as static assets.

## Restart behaviour

The applied instruction is saved under ignored local runtime data and survives a server restart. Conversation history does **not** survive a server restart; a new empty session is created.

## Safe update

Before a workshop session:

~~~powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8004
~~~

Do not use auto-reload during the participant exercise.

## Current implementation scope

This repository is the Day 4 reference starter. Live Groq success still depends on the participant's local API key, current model availability, network access, and the selected model's actual tool-calling behaviour.
