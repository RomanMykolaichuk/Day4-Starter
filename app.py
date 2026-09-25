from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import (
    AgentError,
    compare_prompt_similarity,
    evaluate_user_turn,
    generate_bbb_explanation,
    local_bbb_explanation,
    material_hash,
    read_course_material,
    run_agent_turn,
    validate_course_material,
)

APP_VERSION = "0.4.0"
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DEFAULT_INSTRUCTION_PATH = BASE_DIR / "defaults" / "agent_instruction.md"
DEFAULT_MATERIAL_PATH = BASE_DIR / "materials" / "course_card.json"
DATA_DIR = BASE_DIR / "data"
SAVED_INSTRUCTION_PATH = DATA_DIR / "agent_instruction.md"
SAVED_MATERIAL_PATH = DATA_DIR / "course_card.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def text_version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_example_instruction() -> str:
    return DEFAULT_INSTRUCTION_PATH.read_text(encoding="utf-8").strip()


def load_example_material() -> dict[str, Any]:
    return json.loads(DEFAULT_MATERIAL_PATH.read_text(encoding="utf-8"))


def load_applied_instruction() -> str:
    if SAVED_INSTRUCTION_PATH.exists():
        saved = SAVED_INSTRUCTION_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return load_example_instruction()


def load_applied_material() -> dict[str, Any]:
    example = load_example_material()
    if not SAVED_MATERIAL_PATH.exists():
        return example
    try:
        saved = json.loads(SAVED_MATERIAL_PATH.read_text(encoding="utf-8"))
        validate_course_material(saved)
        return saved
    except (OSError, json.JSONDecodeError, AgentError):
        return example


def atomic_save_text(target: Path, text: str) -> None:
    temp_path = DATA_DIR / (target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(target)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def atomic_save_json(target: Path, payload: dict[str, Any]) -> None:
    atomic_save_text(
        target,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def new_session_id() -> str:
    return "s_" + uuid.uuid4().hex[:16]


def git_metadata() -> dict[str, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        return {
            "source_commit": commit or "Unknown",
            "working_tree": "Clean" if not status else "Modified",
        }
    except Exception:
        return {"source_commit": "Unknown", "working_tree": "Unknown"}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable


class InstructionRequest(BaseModel):
    session_id: str
    instruction: str


class MaterialRequest(BaseModel):
    session_id: str
    learning_goal: str
    guided_supporting_points: str
    guided_limitation: str
    instructor_supporting_points: str
    instructor_limitation: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ModeRequest(BaseModel):
    session_id: str
    mode: str


class SessionRequest(BaseModel):
    session_id: str


class BBBExplainRequest(BaseModel):
    session_id: str
    choice: str = ""
    instruction_change: str = ""
    material_change: str = ""
    observation: str = ""


app = FastAPI(title="Day 4 Agent Starter", version=APP_VERSION)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR), name="assets")


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        },
    )


example_instruction = load_example_instruction()
example_material = load_example_material()
applied_instruction = load_applied_instruction()
applied_material = load_applied_material()

state_lock = threading.Lock()
state: dict[str, Any] = {
    "session_id": new_session_id(),
    "session_started": now_iso(),
    "instruction": applied_instruction,
    "instruction_version": text_version(applied_instruction),
    "material": applied_material,
    "material_version": material_hash(applied_material),
    "public_history": [],
    "internal_history": [],
    "events": [],
    "turn_count": 0,
    "busy": False,
    "mode": "single",
    "last_similarity": None,
    "evaluations": [],
    "last_instruction_comparison": None,
    "last_material_comparison": None,
}


def assert_current_session(session_id: str) -> None:
    if session_id != state["session_id"]:
        raise AppError(
            409,
            "stale_session",
            "This page has an old session. Reload the current state and try again.",
        )


def reset_conversation() -> None:
    state["session_id"] = new_session_id()
    state["session_started"] = now_iso()
    state["public_history"] = []
    state["internal_history"] = []
    state["events"] = []
    state["turn_count"] = 0
    state["last_similarity"] = None
    state["evaluations"] = []


def material_from_request(payload: MaterialRequest) -> dict[str, Any]:
    decision_question = example_material["decision_question"]
    material = {
        "decision_question": decision_question,
        "learning_goal": payload.learning_goal.strip(),
        "guided_dialogue": {
            "supporting_points": payload.guided_supporting_points.strip(),
            "limitation": payload.guided_limitation.strip(),
        },
        "working_with_instructor": {
            "supporting_points": payload.instructor_supporting_points.strip(),
            "limitation": payload.instructor_limitation.strip(),
        },
    }
    try:
        validate_course_material(material)
    except AgentError as exc:
        raise AppError(400, exc.code, exc.message, exc.retryable) from exc
    return material


def material_for_browser(material: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_question": material["decision_question"],
        "learning_goal": material["learning_goal"],
        "guided_supporting_points": material["guided_dialogue"]["supporting_points"],
        "guided_limitation": material["guided_dialogue"]["limitation"],
        "instructor_supporting_points": material["working_with_instructor"]["supporting_points"],
        "instructor_limitation": material["working_with_instructor"]["limitation"],
        "version": material_hash(material),
    }


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    key_present = bool(os.getenv("GROQ_API_KEY", "").strip())
    model = os.getenv("GROQ_MODEL", "").strip()
    return {
        "status": "ok",
        "server": "ready",
        "configuration": {
            "groq_api_key_present": key_present,
            "groq_model_present": bool(model),
            "configured": bool(key_present and model),
        },
        "model": model or None,
        "note": "Configuration present does not prove that a Groq request succeeds.",
    }


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    with state_lock:
        return {
            "app_version": APP_VERSION,
            "session_id": state["session_id"],
            "session_started": state["session_started"],
            "instruction": state["instruction"],
            "instruction_version": state["instruction_version"],
            "example_instruction": example_instruction,
            "material_version": state["material_version"],
            "history": list(state["public_history"]),
            "events": list(state["events"]),
            "turn_count": state["turn_count"],
            "busy": state["busy"],
            "mode": state["mode"],
            "last_similarity": (
                json.loads(json.dumps(state["last_similarity"]))
                if state["last_similarity"]
                else None
            ),
            "evaluations": json.loads(json.dumps(state["evaluations"])),
        }


@app.post("/api/instructions")
async def apply_instruction(payload: InstructionRequest) -> dict[str, Any]:
    instruction = payload.instruction.strip()
    if not instruction:
        raise AppError(400, "instruction_empty", "Instruction cannot be empty.")
    if len(instruction) > 8000:
        raise AppError(400, "instruction_too_long", "Instruction must be 8,000 characters or fewer.")

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "Wait for the current turn to finish.")
        try:
            atomic_save_text(SAVED_INSTRUCTION_PATH, instruction)
        except OSError as exc:
            raise AppError(500, "instruction_save_failed", "The instruction could not be saved.") from exc

        old_instruction = state["instruction"]
        old_version = state["instruction_version"]
        new_version = text_version(instruction)

        state["last_instruction_comparison"] = {
            "old": old_instruction,
            "new": instruction,
            "old_version": old_version,
            "new_version": new_version,
        }
        state["instruction"] = instruction
        state["instruction_version"] = new_version
        reset_conversation()
        return {
            "session_id": state["session_id"],
            "instruction_version": state["instruction_version"],
            "instruction": state["instruction"],
        }


@app.get("/api/material")
async def get_material() -> dict[str, Any]:
    with state_lock:
        current = json.loads(json.dumps(state["material"]))
    return {
        "material_id": "course_card",
        **material_for_browser(current),
        "example": material_for_browser(example_material),
    }


@app.post("/api/material")
async def apply_material(payload: MaterialRequest) -> dict[str, Any]:
    material = material_from_request(payload)

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "Wait for the current turn to finish.")
        try:
            atomic_save_json(SAVED_MATERIAL_PATH, material)
        except OSError as exc:
            raise AppError(500, "material_save_failed", "The learning card could not be saved.") from exc

        old_material = json.loads(json.dumps(state["material"]))
        old_version = state["material_version"]
        new_version = material_hash(material)

        state["last_material_comparison"] = {
            "old": old_material,
            "new": json.loads(json.dumps(material)),
            "old_version": old_version,
            "new_version": new_version,
        }
        state["material"] = material
        state["material_version"] = new_version
        reset_conversation()
        return {
            "session_id": state["session_id"],
            "material_version": state["material_version"],
            "material": material_for_browser(material),
        }


@app.post("/api/mode")
async def set_mode(payload: ModeRequest) -> dict[str, Any]:
    mode = payload.mode.strip().lower()
    if mode not in {"single", "multi"}:
        raise AppError(400, "invalid_mode", "Mode must be 'single' or 'multi'.")

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "Wait for the current turn to finish.")
        if state["mode"] != mode:
            state["mode"] = mode
            reset_conversation()

        return {
            "session_id": state["session_id"],
            "mode": state["mode"],
        }


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> dict[str, Any]:
    message = payload.message.strip()
    if not message:
        raise AppError(400, "message_empty", "Write a message before sending.")
    if len(message) > 4000:
        raise AppError(400, "message_too_long", "Message must be 4,000 characters or fewer.")

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "One agent turn is already running.")
        if state["turn_count"] >= 20:
            raise AppError(409, "conversation_limit", "Start a new chat after 20 completed turns.")

        state["busy"] = True
        session_id = state["session_id"]
        instruction = state["instruction"]
        instruction_ver = state["instruction_version"]
        material = json.loads(json.dumps(state["material"]))
        material_ver = state["material_version"]
        history = list(state["internal_history"])
        public_history = list(state["public_history"])
        mode = state["mode"]
        turn_id = "turn_" + str(state["turn_count"] + 1).zfill(2)

    assistant_history = [
        item for item in public_history if item.get("role") == "assistant"
    ]
    similarity = compare_prompt_similarity(message, assistant_history)
    similarity_event = {
        "turn_id": turn_id,
        "event_type": "prompt_similarity",
        "status": "completed",
        "tool_name": "compare_prompt_similarity",
        "result": similarity,
    }

    evaluation = None
    evaluator_event = None

    try:
        result = await asyncio.to_thread(
            run_agent_turn,
            instruction,
            history,
            message,
            turn_id,
            material,
        )

        if mode == "multi":
            try:
                evaluation = await asyncio.to_thread(
                    evaluate_user_turn,
                    message,
                    result["reply"],
                    material,
                    similarity,
                    public_history,
                )
                evaluator_event = {
                    "turn_id": turn_id,
                    "event_type": "evaluator_agent",
                    "status": "completed",
                    "result": evaluation,
                }
            except AgentError as exc:
                evaluation = {
                    "available": False,
                    "error": exc.code,
                    "message": exc.message,
                }
                evaluator_event = {
                    "turn_id": turn_id,
                    "event_type": "evaluator_agent",
                    "status": "failed",
                    "code": exc.code,
                    "message": exc.message,
                }

    except AgentError as exc:
        failure_event = {
            "session_id": session_id,
            "turn_id": turn_id,
            "timestamp": now_iso(),
            "event_type": "turn_failure",
            "status": "failed",
            "code": exc.code,
            "message": exc.message,
        }
        with state_lock:
            state["events"].append(failure_event)
        raise AppError(
            503 if exc.retryable else 400,
            exc.code,
            exc.message,
            exc.retryable,
        )
    finally:
        with state_lock:
            state["busy"] = False

    timestamp = now_iso()
    turn_events = [similarity_event, *result["events"]]
    if evaluator_event:
        turn_events.append(evaluator_event)

    stamped_events = [
        {"session_id": session_id, "timestamp": timestamp, **event}
        for event in turn_events
    ]

    with state_lock:
        if state["session_id"] != session_id:
            raise AppError(
                409,
                "stale_session",
                "The session changed before the response was saved.",
            )

        state["public_history"].extend([
            {"role": "user", "content": message, "turn_id": turn_id},
            {"role": "assistant", "content": result["reply"], "turn_id": turn_id},
        ])
        state["internal_history"].extend(result["committed_messages"])
        state["events"].extend(stamped_events)
        state["last_similarity"] = similarity
        if mode == "multi" and evaluation is not None:
            state["evaluations"].append({
                "turn_id": turn_id,
                **evaluation,
            })
        state["turn_count"] += 1

    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "reply": result["reply"],
        "model": result["model"],
        "mode": mode,
        "instruction_version": instruction_ver,
        "material_version": material_ver,
        "similarity": similarity,
        "evaluation": evaluation,
        "events": stamped_events,
    }


@app.post("/api/chat/clear")
async def clear_chat(payload: SessionRequest) -> dict[str, Any]:
    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "Wait for the current turn to finish.")
        reset_conversation()
        return {
            "session_id": state["session_id"],
            "instruction_version": state["instruction_version"],
            "material_version": state["material_version"],
        }


@app.post("/api/bbb/explain")
async def explain_bbb_result(payload: BBBExplainRequest) -> dict[str, Any]:
    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(
                409,
                "turn_in_progress",
                "Wait for the current agent turn to finish before generating the BBB explanation.",
            )
        state["busy"] = True
        history = list(state["public_history"])
        instruction_comparison = (
            json.loads(json.dumps(state["last_instruction_comparison"]))
            if state["last_instruction_comparison"]
            else None
        )
        material_comparison = (
            json.loads(json.dumps(state["last_material_comparison"]))
            if state["last_material_comparison"]
            else None
        )

    source = "groq"
    warning = None
    try:
        explanation = await asyncio.to_thread(
            generate_bbb_explanation,
            payload.choice.strip(),
            payload.observation.strip(),
            history,
            instruction_comparison,
            material_comparison,
        )
    except AgentError as exc:
        source = "local_fallback"
        warning = exc.code
        explanation = local_bbb_explanation(
            payload.instruction_change.strip(),
            payload.material_change.strip(),
            payload.observation.strip(),
        )
    finally:
        with state_lock:
            state["busy"] = False

    return {
        "session_id": payload.session_id,
        "explanation": explanation,
        "source": source,
        "warning": warning,
        "model": os.getenv("GROQ_MODEL", "").strip() or None,
    }


@app.get("/api/export")
async def export_session(session_id: str = Query(..., min_length=3)) -> Response:
    with state_lock:
        assert_current_session(session_id)
        if state["busy"]:
            raise AppError(409, "turn_in_progress", "Wait for the current turn to finish before exporting.")

        snapshot = {
            "session_id": state["session_id"],
            "session_started": state["session_started"],
            "instruction": state["instruction"],
            "instruction_version": state["instruction_version"],
            "material": json.loads(json.dumps(state["material"])),
            "material_version": state["material_version"],
            "history": list(state["public_history"]),
            "events": list(state["events"]),
        }

    git = git_metadata()
    model = os.getenv("GROQ_MODEL", "").strip() or "Not configured"
    material = snapshot["material"]

    lines = [
        "# Day 4 Agent Session",
        "",
        "## Runtime",
        "",
        "- Application version: " + APP_VERSION,
        "- Model: " + model,
        "- Session: " + snapshot["session_id"],
        "- Session started: " + snapshot["session_started"],
        "- Instruction version: " + snapshot["instruction_version"],
        "- Learning-card version: " + snapshot["material_version"],
        "- Source commit: " + git["source_commit"],
        "- Working tree: " + git["working_tree"],
        "",
        "## Decision question",
        "",
        material["decision_question"],
        "",
        "## Applied instruction",
        "",
        snapshot["instruction"],
        "",
        "## Applied learning card",
        "",
        "### Learning goal",
        material["learning_goal"],
        "",
        "### Guided dialogue — supporting points",
        material["guided_dialogue"]["supporting_points"],
        "",
        "### Guided dialogue — limitation",
        material["guided_dialogue"]["limitation"],
        "",
        "### Working with an instructor — supporting points",
        material["working_with_instructor"]["supporting_points"],
        "",
        "### Working with an instructor — limitation",
        material["working_with_instructor"]["limitation"],
        "",
        "## Conversation",
        "",
    ]

    if snapshot["history"]:
        for item in snapshot["history"]:
            lines.extend([
                "### " + item["role"].title() + " — " + item["turn_id"],
                "",
                item["content"],
                "",
            ])
    else:
        lines.extend(["_No completed turns in this session._", ""])

    lines.extend(["## Tool and execution activity", ""])
    if snapshot["events"]:
        for event in snapshot["events"]:
            lines.extend([
                "### " + event.get("turn_id", "turn") + " — " + event.get("event_type", "event"),
                "",
                "~~~json",
                json.dumps(event, ensure_ascii=False, indent=2),
                "~~~",
                "",
            ])
    else:
        lines.extend(["_No activity recorded._", ""])

    lines.extend([
        "## Participant observation",
        "",
        "Which option did I choose and why?",
        "",
        "",
        "What changed after I edited the agent instruction?",
        "",
        "",
        "What changed after I edited one learning-card field?",
        "",
        "",
    ])

    headers = {
        "Content-Disposition": 'attachment; filename="day4-session-' + session_id + '.md"'
    }
    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
