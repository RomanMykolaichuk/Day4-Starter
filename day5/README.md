# Day 5 Multi-Agent Starter

Day 5 extends the Day 4 Teaching Agent into a small, visible **multi-agent learning workflow**.

## Learning goal

Participants should be able to explain the difference between:

- an **agent** that performs the main teaching task;
- a deterministic **tool** that analyzes the next user prompt;
- a second **Evaluator Agent** that independently assesses the learner's contribution;
- a **multi-agent workflow** in which specialized components have different roles.

## Architecture

### Single Agent mode

~~~text
User Prompt
    ↓
Prompt Similarity Tool
    ↓
Teaching Agent
    ↓
Learning Card Tool
~~~

### Multi-Agent mode

~~~text
User Prompt
    ↓
Prompt Similarity Tool
    ↓
Teaching Agent
    ↓
Evaluator Agent
    ↓
Formative Evaluation
~~~

Switching between Single Agent and Multi-Agent starts a fresh chat while keeping the currently applied Teaching Agent instruction and learning card.

## Prompt Similarity Tool

Before each Teaching Agent turn, the local deterministic tool compares the new user prompt with fragments of **all previous Teaching Agent replies in the current chat**.

It reports:

- similarity score from 0 to 100%;
- level: none / low / moderate / high;
- closest previous turn;
- closest matching fragment.

The comparison is local and does not make another Groq request.

**Important:** text similarity is only an indicator. It is not proof of copying, plagiarism, or authorship.

## Evaluator Agent

In Multi-Agent mode, a second Groq-backed agent runs after the Teaching Agent.

It first assesses only the learner's current contribution and produces a **base content score /100**:

- clear choice / claim — 25 points;
- supporting evidence in the learner's own contribution — 45 points;
- recognition of a limitation — 30 points.

The application then applies a deterministic similarity penalty:

- below 35% similarity — 0 points;
- 35–44% — −5;
- 45–59% — −15;
- 60–74% — −30;
- 75–89% — −45;
- 90–100% — −60.

Final score = base content score − similarity penalty, with a minimum of 0.

The Teaching Agent response is supplied as context, not as the object being graded. The Evaluator Agent does **not** apply the similarity deduction itself, which prevents inconsistent double scoring. Similarity remains a text-similarity indicator, not proof of copying or authorship.

If the Evaluator Agent fails, the Teaching Agent answer remains available.

## Suggested Day 5 procedure

1. Start in **Single Agent** mode.
2. Choose the same A/B decision task used on Day 4.
3. Send a follow-up and inspect **Prompt Similarity**.
4. Switch to **Multi-Agent** mode.
5. Repeat the task.
6. Inspect the separate **Evaluator Agent** panel.
7. Compare the responsibilities of the Teaching Agent, similarity tool, and Evaluator Agent.
8. Optionally change the instruction or learning card and repeat the workflow.
9. Export or copy the final evidence for BBB.

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
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8005
~~~

Then open:

http://127.0.0.1:8005/

Never commit or share a real API key.

## Evidence

The Day 5 BBB/export evidence includes the current mode, tool activity, latest similarity result, Evaluator Agent result when Multi-Agent mode is active, instruction/card versions, and the existing old/new instruction and learning-card comparison.
