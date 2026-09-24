from __future__ import annotations

import json
import os
import threading
import time
from hashlib import sha256
from typing import Any

import groq
from groq import Groq

_CLIENT_LOCK = threading.Lock()
_SHARED_CLIENT: Groq | None = None
_SHARED_API_KEY: str | None = None

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_course_material",
        "description": (
            "Read the currently applied learning card. It contains the decision "
            "question, learning goal, and evidence for two options: Guided dialogue "
            "and Working with an instructor."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "material_id": {
                    "type": "string",
                    "enum": ["course_card"],
                    "description": "Fixed identifier of the applied learning card.",
                }
            },
            "required": ["material_id"],
            "additionalProperties": False,
        },
    },
}


class AgentError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def material_hash(material: dict[str, Any]) -> str:
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True)
    return sha256(canonical.encode("utf-8")).hexdigest()[:12]


def validate_course_material(material: dict[str, Any]) -> dict[str, Any]:
    required_text = ["decision_question", "learning_goal"]
    for key in required_text:
        if not isinstance(material.get(key), str) or not material[key].strip():
            raise AgentError("material_structure", f"Learning card field '{key}' is required.")

    for option in ["guided_dialogue", "working_with_instructor"]:
        value = material.get(option)
        if not isinstance(value, dict):
            raise AgentError("material_structure", f"Learning card option '{option}' is required.")
        for field in ["supporting_points", "limitation"]:
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise AgentError(
                    "material_structure",
                    f"Learning card field '{option}.{field}' is required.",
                )

    return material


def read_course_material(
    material_id: str,
    material: dict[str, Any],
) -> dict[str, Any]:
    if material_id != "course_card":
        raise AgentError(
            "unapproved_material",
            "Only material_id 'course_card' can be read.",
        )

    validate_course_material(material)
    return {
        "material_id": "course_card",
        "version": material_hash(material),
        "decision_question": material["decision_question"],
        "learning_goal": material["learning_goal"],
        "options": {
            "Guided dialogue": material["guided_dialogue"],
            "Working with an instructor": material["working_with_instructor"],
        },
    }


def _remaining(started: float, limit: float = 60.0) -> float:
    value = limit - (time.monotonic() - started)
    if value <= 1.0:
        raise AgentError(
            "turn_timeout",
            "The agent turn exceeded the 60-second time limit.",
            retryable=True,
        )
    return value


def _client(api_key: str) -> Groq:
    """Return one shared Groq client so HTTP connections are reused."""
    global _SHARED_CLIENT, _SHARED_API_KEY

    with _CLIENT_LOCK:
        if _SHARED_CLIENT is None or _SHARED_API_KEY != api_key:
            if _SHARED_CLIENT is not None:
                try:
                    _SHARED_CLIENT.close()
                except Exception:
                    pass

            _SHARED_CLIENT = Groq(
                api_key=api_key,
                max_retries=0,
                timeout=60.0,
            )
            _SHARED_API_KEY = api_key

        return _SHARED_CLIENT


def local_bbb_explanation(
    instruction_change: str,
    material_change: str,
    observation: str,
) -> str:
    instruction_change = (instruction_change or "").strip()
    material_change = (material_change or "").strip()
    observation = (observation or "").strip()

    if instruction_change and instruction_change != "Not changed in this run":
        sentence1 = (
            "The instruction change altered how the agent was configured to respond: "
            + instruction_change.rstrip(".")
            + "."
        )
    else:
        sentence1 = "No agent-instruction change was recorded in this run."

    if material_change and material_change != "Not changed in this run":
        sentence2 = (
            "The learning-card change altered the source information available to the agent tool: "
            + material_change.rstrip(".")
            + "."
        )
    else:
        sentence2 = "No learning-card change was recorded in this run."

    if observation:
        sentence2 += " Participant observation: " + observation.rstrip(".") + "."

    return sentence1 + " " + sentence2


def generate_bbb_explanation(
    choice: str,
    instruction_change: str,
    material_change: str,
    observation: str,
    history: list[dict[str, Any]],
    instruction_version: str,
    material_version: str,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or not model:
        raise AgentError(
            "configuration_missing",
            "Add GROQ_API_KEY and GROQ_MODEL to .env, then restart the server.",
        )

    recent_history = history[-4:]
    evidence = {
        "choice": choice or "Not recorded",
        "instruction_change": instruction_change or "Not recorded",
        "instruction_version": instruction_version,
        "learning_card_change": material_change or "Not recorded",
        "learning_card_version": material_version,
        "participant_observation": observation or "",
        "recent_conversation": recent_history,
    }

    prompt = (
        "Write exactly two short plain-English sentences for an instructor report. "
        "Sentence 1 must explain what changing the agent instruction means or affected. "
        "Sentence 2 must explain what changing the learning card means or affected. "
        "Use only the supplied evidence. Do not invent a comparison that is not supported. "
        "If a change was not recorded, say that it was not recorded. "
        "Keep the total under 55 words. Do not use bullets, headings, markdown, or scores.\n\n"
        + json.dumps(evidence, ensure_ascii=False)
    )

    try:
        response = _client(api_key).chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You create concise evidence-based workshop result explanations. "
                        "Do not add facts that are absent from the supplied record."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=120,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise AgentError(
                "empty_model_output",
                "The model returned an empty BBB explanation.",
                retryable=True,
            )
        return text
    except AgentError:
        raise
    except groq.AuthenticationError as exc:
        raise AgentError("authentication_failed", "Groq rejected the API key.") from exc
    except groq.RateLimitError as exc:
        raise AgentError("rate_limit", "Groq rate limit reached.", True) from exc
    except groq.NotFoundError as exc:
        raise AgentError("model_unavailable", "The configured Groq model is unavailable.") from exc
    except groq.APITimeoutError as exc:
        raise AgentError("provider_timeout", "Groq did not respond before the deadline.", True) from exc
    except groq.APIConnectionError as exc:
        raise AgentError("provider_connection", "The starter could not reach Groq.", True) from exc
    except groq.BadRequestError as exc:
        raise AgentError("provider_rejected_request", "Groq rejected the BBB explanation request.") from exc
    except groq.APIStatusError as exc:
        raise AgentError(
            "provider_error",
            "Groq returned an unexpected API error.",
            retryable=bool(getattr(exc, "status_code", 0) >= 500),
        ) from exc


def run_agent_turn(
    instruction: str,
    history: list[dict[str, Any]],
    user_message: str,
    turn_id: str,
    material: dict[str, Any],
) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or not model:
        raise AgentError(
            "configuration_missing",
            "Add GROQ_API_KEY and GROQ_MODEL to .env, then restart the server.",
        )

    validate_course_material(material)
    started = time.monotonic()
    events: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instruction},
        *history,
        {"role": "user", "content": user_message},
    ]

    try:
        _remaining(started)
        client = _client(api_key)
        first = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            max_completion_tokens=700,
        )
        first_message = first.choices[0].message
        tool_calls = list(first_message.tool_calls or [])

        events.append({
            "turn_id": turn_id,
            "event_type": "model_request",
            "status": "completed",
            "step": 1,
            "model": model,
            "tool_requested": bool(tool_calls),
        })

        if not tool_calls:
            reply = (first_message.content or "").strip()
            if not reply:
                raise AgentError("empty_model_output", "The model returned an empty response.", True)
            events.append({
                "turn_id": turn_id,
                "event_type": "direct_reply",
                "status": "completed",
                "tool_used": False,
            })
            return {
                "reply": reply,
                "model": model,
                "events": events,
                "committed_messages": [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": reply},
                ],
            }

        if len(tool_calls) != 1:
            raise AgentError("multiple_tool_calls", "This starter allows at most one tool call per turn.")

        call = tool_calls[0]
        if call.function.name != "read_course_material":
            raise AgentError("unknown_tool", "The model requested a tool that is not allowed.")

        try:
            arguments = json.loads(call.function.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentError("invalid_tool_arguments", "The model returned malformed tool arguments.") from exc

        if arguments != {"material_id": "course_card"}:
            raise AgentError(
                "invalid_tool_arguments",
                "The tool accepts only material_id='course_card'.",
            )

        tool_result = read_course_material("course_card", material)
        events.append({
            "turn_id": turn_id,
            "event_type": "tool_call",
            "status": "completed",
            "call_id": call.id,
            "tool_name": "read_course_material",
            "arguments": {"material_id": "course_card"},
            "result": tool_result,
        })

        assistant_tool_message = {
            "role": "assistant",
            "content": first_message.content,
            "tool_calls": [{
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }],
        }
        tool_result_message = {
            "role": "tool",
            "tool_call_id": call.id,
            "name": "read_course_material",
            "content": json.dumps(tool_result, ensure_ascii=False),
        }

        _remaining(started)
        final = client.chat.completions.create(
            model=model,
            messages=[*messages, assistant_tool_message, tool_result_message],
            tools=[TOOL_SCHEMA],
            tool_choice="none",
            max_completion_tokens=700,
        )
        final_message = final.choices[0].message

        if final_message.tool_calls:
            raise AgentError("tool_limit_exceeded", "The model attempted another tool call.")

        reply = (final_message.content or "").strip()
        if not reply:
            raise AgentError("empty_model_output", "The model returned an empty final response.", True)

        events.append({
            "turn_id": turn_id,
            "event_type": "model_request",
            "status": "completed",
            "step": 2,
            "model": model,
            "tool_choice": "none",
        })

        return {
            "reply": reply,
            "model": model,
            "events": events,
            "committed_messages": [
                {"role": "user", "content": user_message},
                assistant_tool_message,
                tool_result_message,
                {"role": "assistant", "content": reply},
            ],
        }

    except AgentError:
        raise
    except groq.AuthenticationError as exc:
        raise AgentError("authentication_failed", "Groq rejected the API key.") from exc
    except groq.RateLimitError as exc:
        raise AgentError("rate_limit", "Groq rate limit reached.", True) from exc
    except groq.NotFoundError as exc:
        raise AgentError("model_unavailable", "The configured Groq model is unavailable.") from exc
    except groq.APITimeoutError as exc:
        raise AgentError("provider_timeout", "Groq did not respond before the deadline.", True) from exc
    except groq.APIConnectionError as exc:
        raise AgentError("provider_connection", "The starter could not reach Groq.", True) from exc
    except groq.BadRequestError as exc:
        raise AgentError(
            "provider_rejected_request",
            "Groq rejected the request. Check model tool-calling support.",
        ) from exc
    except groq.APIStatusError as exc:
        raise AgentError(
            "provider_error",
            "Groq returned an unexpected API error.",
            retryable=bool(getattr(exc, "status_code", 0) >= 500),
        ) from exc
