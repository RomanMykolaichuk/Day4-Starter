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

from agent import AgentError, material_hash, read_course_material, run_agent_turn

APP_VERSION = "0.1.0"
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DEFAULT_INSTRUCTION_PATH = BASE_DIR / "defaults" / "agent_instruction.md"
DATA_DIR = BASE_DIR / "data"
SAVED_INSTRUCTION_PATH = DATA_DIR / "agent_instruction.md"

DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def instruction_version(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_example_instruction() -> str:
    return DEFAULT_INSTRUCTION_PATH.read_text(encoding="utf-8").strip()


def load_applied_instruction() -> str:
    if SAVED_INSTRUCTION_PATH.exists():
        saved = SAVED_INSTRUCTION_PATH.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return load_example_instruction()


def atomic_save_instruction(text: str) -> None:
    temp_path = DATA_DIR / ("agent_instruction." + uuid.uuid4().hex + ".tmp")
    try:
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(SAVED_INSTRUCTION_PATH)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


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


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SessionRequest(BaseModel):
    session_id: str


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


state_lock = threading.Lock()
applied_instruction = load_applied_instruction()
state: dict[str, Any] = {
    "session_id": new_session_id(),
    "session_started": now_iso(),
    "instruction": applied_instruction,
    "instruction_version": instruction_version(applied_instruction),
    "public_history": [],
    "internal_history": [],
    "events": [],
    "turn_count": 0,
    "busy": False,
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
        "note": (
            "Configuration present does not prove that a Groq request succeeds."
        ),
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
            "example_instruction": load_example_instruction(),
            "history": list(state["public_history"]),
            "events": list(state["events"]),
            "turn_count": state["turn_count"],
            "busy": state["busy"],
        }


@app.post("/api/instructions")
async def apply_instruction(payload: InstructionRequest) -> dict[str, Any]:
    instruction = payload.instruction.strip()
    if not instruction:
        raise AppError(400, "instruction_empty", "Instruction cannot be empty.")
    if len(instruction) > 8000:
        raise AppError(
            400,
            "instruction_too_long",
            "Instruction must be 8,000 characters or fewer.",
        )

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(
                409,
                "turn_in_progress",
                "Wait for the current agent turn to finish before applying changes.",
            )
        try:
            atomic_save_instruction(instruction)
        except OSError as exc:
            raise AppError(
                500,
                "instruction_save_failed",
                "The new instruction could not be saved. The previous instruction is still active.",
            ) from exc

        state["instruction"] = instruction
        state["instruction_version"] = instruction_version(instruction)
        reset_conversation()
        return {
            "session_id": state["session_id"],
            "instruction_version": state["instruction_version"],
            "instruction": state["instruction"],
        }


@app.post("/api/chat")
async def chat(payload: ChatRequest) -> dict[str, Any]:
    message = payload.message.strip()
    if not message:
        raise AppError(400, "message_empty", "Write a message before sending.")
    if len(message) > 4000:
        raise AppError(
            400,
            "message_too_long",
            "Message must be 4,000 characters or fewer.",
        )

    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(
                409,
                "turn_in_progress",
                "One agent turn is already running.",
            )
        if state["turn_count"] >= 20:
            raise AppError(
                409,
                "conversation_limit",
                "This conversation reached 20 completed turns. Start a new chat.",
            )
        state["busy"] = True
        session_id = state["session_id"]
        instruction = state["instruction"]
        instruction_ver = state["instruction_version"]
        history = list(state["internal_history"])
        turn_id = "turn_" + str(state["turn_count"] + 1).zfill(2)

    try:
        result = await asyncio.to_thread(
            run_agent_turn,
            instruction,
            history,
            message,
            turn_id,
        )
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
        status_code = 503 if exc.retryable else 400
        raise AppError(status_code, exc.code, exc.message, exc.retryable)
    finally:
        with state_lock:
            state["busy"] = False

    timestamp = now_iso()
    stamped_events = []
    for event in result["events"]:
        stamped_events.append(
            {
                "session_id": session_id,
                "timestamp": timestamp,
                **event,
            }
        )

    with state_lock:
        if state["session_id"] != session_id:
            raise AppError(
                409,
                "stale_session",
                "The session changed before the agent response could be saved.",
            )
        state["public_history"].extend(
            [
                {"role": "user", "content": message, "turn_id": turn_id},
                {
                    "role": "assistant",
                    "content": result["reply"],
                    "turn_id": turn_id,
                },
            ]
        )
        state["internal_history"].extend(result["committed_messages"])
        state["events"].extend(stamped_events)
        state["turn_count"] += 1

    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "reply": result["reply"],
        "model": result["model"],
        "instruction_version": instruction_ver,
        "events": stamped_events,
    }


@app.post("/api/chat/clear")
async def clear_chat(payload: SessionRequest) -> dict[str, Any]:
    with state_lock:
        assert_current_session(payload.session_id)
        if state["busy"]:
            raise AppError(
                409,
                "turn_in_progress",
                "Wait for the current agent turn to finish before clearing the chat.",
            )
        reset_conversation()
        return {
            "session_id": state["session_id"],
            "instruction_version": state["instruction_version"],
        }


@app.get("/api/material")
async def material() -> dict[str, Any]:
    return read_course_material("course_card")


@app.get("/api/export")
async def export_session(
    session_id: str = Query(..., min_length=3),
) -> Response:
    with state_lock:
        assert_current_session(session_id)
        if state["busy"]:
            raise AppError(
                409,
                "turn_in_progress",
                "Wait for the current turn to finish before exporting.",
            )
        snapshot = {
            "session_id": state["session_id"],
            "session_started": state["session_started"],
            "instruction": state["instruction"],
            "instruction_version": state["instruction_version"],
            "history": list(state["public_history"]),
            "events": list(state["events"]),
        }

    git = git_metadata()
    model = os.getenv("GROQ_MODEL", "").strip() or "Not configured"

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
        "- Course-card version: " + material_hash(),
        "- Source commit: " + git["source_commit"],
        "- Working tree: " + git["working_tree"],
        "",
        "## Applied instruction",
        "",
        snapshot["instruction"],
        "",
        "## Conversation",
        "",
    ]

    if snapshot["history"]:
        for item in snapshot["history"]:
            lines.extend(
                [
                    "### " + item["role"].title() + " — " + item["turn_id"],
                    "",
                    item["content"],
                    "",
                ]
            )
    else:
        lines.extend(["_No completed turns in this session._", ""])

    lines.extend(["## Tool and execution activity", ""])
    if snapshot["events"]:
        for event in snapshot["events"]:
            lines.extend(
                [
                    "### "
                    + event.get("turn_id", "turn")
                    + " — "
                    + event.get("event_type", "event"),
                    "",
                    "~~~json",
                    json.dumps(event, ensure_ascii=False, indent=2),
                    "~~~",
                    "",
                ]
            )
    else:
        lines.extend(["_No activity recorded._", ""])

    lines.extend(
        [
            "## Participant observation",
            "",
            "What changed after I edited the instruction?",
            "",
            "",
            "What will I change or test next?",
            "",
            "",
        ]
    )

    markdown = "\n".join(lines)
    headers = {
        "Content-Disposition": (
            'attachment; filename="day4-session-' + session_id + '.md"'
        )
    }
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )
