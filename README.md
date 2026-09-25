# AI Agents Workshop · Day 4 and Day 5

This repository contains two self-contained local workshop applications for **AI Agents for Defence Education**.

## Structure

~~~text
Day4-Starter/
├── day4/   # one Teaching Agent + course-material tool
├── day5/   # similarity tool + Single/Multi-Agent + Evaluator Agent
└── .github/workflows/smoke.yml
~~~

The repository name is kept unchanged so existing links and clones continue to work.

## Day 4 · Build and modify one agent

Day 4 focuses on the basic agent workflow:

~~~text
User
  ↓
Teaching Agent
  ↓
read_course_material
  ↓
Learning Card
~~~

Participants edit the agent instruction and learning card, test the same decision task, inspect real tool use, compare the results, and prepare a BBB evidence block.

Start Day 4:

~~~powershell
cd day4
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8004
~~~

Open: http://127.0.0.1:8004/

See day4/README.md.

## Day 5 · From agent to multi-agent workflow

Day 5 extends the same idea:

~~~text
User Prompt
    ↓
Prompt Similarity Tool
    ↓
Teaching Agent
    ↓
Evaluator Agent   (Multi-Agent mode)
~~~

Participants compare Single Agent and Multi-Agent modes, inspect prompt similarity against previous Teaching Agent responses, and observe a separate Evaluator Agent assessing the learner's own contribution.

Start Day 5:

~~~powershell
cd day5
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8005
~~~

Open: http://127.0.0.1:8005/

See day5/README.md.

## Important

Each day reads its own local .env and writes participant changes only inside that day's data/ folder. Real .env files, virtual environments, Python caches, and generated local data are ignored by Git.

Never commit or share a real Groq API key.
