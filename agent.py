from __future__ import annotations

import json
import os
import time
from hashlib import sha256
from typing import Any

import groq
from groq import Groq

TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_course_material",
        "description": (
            "Read the currently applied learning card for this activity. "
            "Use it when feedback needs evidence from the course material."
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


def material_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:12]


def parse_course_material(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise AgentError("material_empty", "The learning card cannot be empty.")

    lines = raw.splitlines()
    title = "Learning Card"
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip() or title
            break

    sections: list[dict[str, str]] = []
    for block in raw.split("\n## ")[1:]:
        heading, _, body = block.partition("\n")
        heading = heading.strip()
        label = heading.split(".", 1)[0].strip()
        sections.append(
            {
                "label": label,
                "heading": heading,
                "content": body.strip(),
            }
        )

    labels = [section["label"] for section in sections]
    if labels != ["A", "B", "C"]:
        raise AgentError(
            "material_structure",
            "Keep exactly three learning-card sections with headings A, B, and C.",
        )

    if any(not section["content"] for section in sections):
        raise AgentError(
            "material_structure",
            "Each learning-card section A, B, and C must contain text.",
        )

    return {
        "material_id": "course_card",
        "title": title,
        "version": material_hash(raw),
        "sections": sections,
    }


def read_course_material(material_id: str, material_text: str) -> dict[str, Any]:
    if material_id != "course_card":
        raise AgentError(
            "unapproved_material",
            "Only the learning card with material_id 'course_card' can be read.",
        )
    return parse_course_material(material_text)


def _remaining(started: float, limit: float = 60.0) -> float:
    value = limit - (time.monotonic() - started)
    if value <= 1.0:
        raise AgentError(
            "turn_timeout",
            "The agent turn exceeded the 60-second time limit.",
            retryable=True,
        )
    return value


def _client(api_key: str, timeout_seconds: float) -> Groq:
    return Groq(
        api_key=api_key,
        max_retries=0,
        timeout=timeout_seconds,
    )


def run_agent_turn(
    instruction: str,
    history: list[dict[str, Any]],
    user_message: str,
    turn_id: str,
    material_text: str,
) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or not model:
        raise AgentError(
            "configuration_missing",
            "Add GROQ_API_KEY and GROQ_MODEL to .env, then restart the server.",
        )

    # Validate the currently applied card before any provider request.
    parse_course_material(material_text)

    started = time.monotonic()
    events: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instruction},
        *history,
        {"role": "user", "content": user_message},
    ]

    try:
        first_timeout = _remaining(started)
        first = _client(api_key, first_timeout).chat.completions.create(
            model=model,
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
            max_completion_tokens=700,
        )
        first_message = first.choices[0].message
        tool_calls = list(first_message.tool_calls or [])

        events.append(
            {
                "turn_id": turn_id,
                "event_type": "model_request",
                "status": "completed",
                "step": 1,
                "model": model,
                "tool_requested": bool(tool_calls),
            }
        )

        if not tool_calls:
            reply = (first_message.content or "").strip()
            if not reply:
                raise AgentError(
                    "empty_model_output",
                    "The model returned an empty response.",
                    retryable=True,
                )
            events.append(
                {
                    "turn_id": turn_id,
                    "event_type": "direct_reply",
                    "status": "completed",
                    "tool_used": False,
                }
            )
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
            raise AgentError(
                "multiple_tool_calls",
                "This starter allows at most one tool call per turn.",
            )

        call = tool_calls[0]
        if call.function.name != "read_course_material":
            raise AgentError(
                "unknown_tool",
                "The model requested a tool that is not allowed by this starter.",
            )

        try:
            arguments = json.loads(call.function.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AgentError(
                "invalid_tool_arguments",
                "The model returned malformed tool arguments.",
            ) from exc

        if (
            not isinstance(arguments, dict)
            or set(arguments.keys()) != {"material_id"}
            or arguments.get("material_id") != "course_card"
        ):
            raise AgentError(
                "invalid_tool_arguments",
                "The tool accepts only material_id='course_card'.",
            )

        tool_result = read_course_material("course_card", material_text)
        events.append(
            {
                "turn_id": turn_id,
                "event_type": "tool_call",
                "status": "completed",
                "call_id": call.id,
                "tool_name": "read_course_material",
                "arguments": {"material_id": "course_card"},
                "result": tool_result,
            }
        )

        assistant_tool_message = {
            "role": "assistant",
            "content": first_message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
            ],
        }
        tool_result_message = {
            "role": "tool",
            "tool_call_id": call.id,
            "name": "read_course_material",
            "content": json.dumps(tool_result, ensure_ascii=False),
        }

        second_messages = [
            *messages,
            assistant_tool_message,
            tool_result_message,
        ]

        second_timeout = _remaining(started)
        final = _client(api_key, second_timeout).chat.completions.create(
            model=model,
            messages=second_messages,
            tools=[TOOL_SCHEMA],
            tool_choice="none",
            max_completion_tokens=700,
        )
        final_message = final.choices[0].message

        if final_message.tool_calls:
            raise AgentError(
                "tool_limit_exceeded",
                "The model attempted another tool call after the one-tool limit.",
            )

        reply = (final_message.content or "").strip()
        if not reply:
            raise AgentError(
                "empty_model_output",
                "The model returned an empty final response.",
                retryable=True,
            )

        events.append(
            {
                "turn_id": turn_id,
                "event_type": "model_request",
                "status": "completed",
                "step": 2,
                "model": model,
                "tool_choice": "none",
            }
        )

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
        raise AgentError(
            "authentication_failed",
            "Groq rejected the API key. Check the local .env file.",
        ) from exc
    except groq.RateLimitError as exc:
        raise AgentError(
            "rate_limit",
            "Groq rate limit reached. Try again later or ask the instructor.",
            retryable=True,
        ) from exc
    except groq.NotFoundError as exc:
        raise AgentError(
            "model_unavailable",
            "The configured Groq model was not found or is unavailable.",
        ) from exc
    except groq.APITimeoutError as exc:
        raise AgentError(
            "provider_timeout",
            "Groq did not respond before the turn deadline.",
            retryable=True,
        ) from exc
    except groq.APIConnectionError as exc:
        raise AgentError(
            "provider_connection",
            "The starter could not reach Groq. Check the network connection.",
            retryable=True,
        ) from exc
    except groq.BadRequestError as exc:
        raise AgentError(
            "provider_rejected_request",
            "Groq rejected the model request. Check model tool-calling support.",
        ) from exc
    except groq.APIStatusError as exc:
        raise AgentError(
            "provider_error",
            "Groq returned an unexpected API error.",
            retryable=bool(getattr(exc, "status_code", 0) >= 500),
        ) from exc
