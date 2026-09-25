from __future__ import annotations

import json
import os
import re
import threading
import time
from difflib import SequenceMatcher
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


def _normalized_tokens(text: str) -> list[str]:
    return re.findall(
        r"[^\\W_]+(?:'[^\\W_]+)?",
        (text or "").lower(),
        flags=re.UNICODE,
    )


def _candidate_chunks(text: str, target_length: int) -> list[str]:
    raw_parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", text or "")
        if part.strip()
    ]
    candidates = list(raw_parts)
    tokens = _normalized_tokens(text)
    if not tokens:
        return candidates

    window = max(6, min(max(target_length, 8), 40))
    step = max(3, window // 2)
    if len(tokens) <= window:
        candidates.append(" ".join(tokens))
    else:
        for start in range(0, len(tokens), step):
            chunk = tokens[start : start + window]
            if len(chunk) >= 4:
                candidates.append(" ".join(chunk))
            if start + window >= len(tokens):
                break
    return candidates


def compare_prompt_similarity(
    prompt: str,
    assistant_history: list[dict[str, Any]],
) -> dict[str, Any]:
    prompt_tokens = _normalized_tokens(prompt)
    prompt_norm = " ".join(prompt_tokens)

    if not prompt_tokens or not assistant_history:
        return {
            "score": 0,
            "level": "none",
            "matched_turn_id": None,
            "matched_excerpt": "",
            "responses_checked": len(assistant_history),
            "note": "No previous agent response is available for comparison.",
        }

    prompt_set = set(prompt_tokens)
    best_score = 0.0
    best_turn = None
    best_excerpt = ""

    for item in assistant_history:
        content = str(item.get("content", ""))
        for chunk in _candidate_chunks(content, len(prompt_tokens)):
            chunk_tokens = _normalized_tokens(chunk)
            if not chunk_tokens:
                continue

            chunk_norm = " ".join(chunk_tokens)
            sequence = SequenceMatcher(None, prompt_norm, chunk_norm).ratio()
            chunk_set = set(chunk_tokens)
            overlap = len(prompt_set & chunk_set)
            prompt_coverage = overlap / max(1, len(prompt_set))
            chunk_coverage = overlap / max(1, len(chunk_set))
            lexical = (0.72 * prompt_coverage) + (0.28 * chunk_coverage)
            score = max(sequence, lexical)

            if score > best_score:
                best_score = score
                best_turn = item.get("turn_id")
                best_excerpt = chunk.strip()

    percent = int(round(best_score * 100))
    if percent >= 70:
        level = "high"
    elif percent >= 45:
        level = "moderate"
    elif percent > 0:
        level = "low"
    else:
        level = "none"

    if len(best_excerpt) > 260:
        best_excerpt = best_excerpt[:257].rstrip() + "..."

    return {
        "score": percent,
        "level": level,
        "matched_turn_id": best_turn,
        "matched_excerpt": best_excerpt,
        "responses_checked": len(assistant_history),
        "note": (
            "Text similarity is a lexical indicator only; it is not proof of copying "
            "or authorship."
        ),
    }


def _parse_evaluator_json(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith(chr(96) * 3):
        cleaned = cleaned.replace(chr(96) * 3 + "json", "", 1).strip()
        if cleaned.endswith(chr(96) * 3):
            cleaned = cleaned[: -3].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "score": None,
            "summary": cleaned or "Evaluator returned no readable assessment.",
            "strength": "",
            "improve": "",
            "similarity_note": "",
        }

    score = data.get("score")
    if isinstance(score, (int, float)):
        score = max(0, min(100, int(round(score))))
    else:
        score = None

    return {
        "score": score,
        "summary": str(data.get("summary", "")).strip(),
        "strength": str(data.get("strength", "")).strip(),
        "improve": str(data.get("improve", "")).strip(),
        "similarity_note": str(data.get("similarity_note", "")).strip(),
    }


def similarity_penalty(similarity_score: int | float | None) -> dict[str, Any]:
    try:
        value = max(0, min(100, int(round(float(similarity_score or 0)))))
    except (TypeError, ValueError):
        value = 0

    if value >= 90:
        penalty = 60
    elif value >= 75:
        penalty = 45
    elif value >= 60:
        penalty = 30
    elif value >= 45:
        penalty = 15
    elif value >= 35:
        penalty = 5
    else:
        penalty = 0

    return {
        "similarity_score": value,
        "penalty": penalty,
        "rule": (
            "<35: 0; 35-44: -5; 45-59: -15; "
            "60-74: -30; 75-89: -45; 90-100: -60"
        ),
    }


def evaluate_user_turn(
    user_message: str,
    primary_reply: str,
    material: dict[str, Any],
    similarity: dict[str, Any],
    recent_history: list[dict[str, Any]],
) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or not model:
        raise AgentError(
            "configuration_missing",
            "Add GROQ_API_KEY and GROQ_MODEL to .env, then restart the server.",
        )

    payload = {
        "learning_task": material.get("decision_question", ""),
        "user_message_to_assess": user_message,
        "teaching_agent_reply_for_context_only": primary_reply,
        "learning_card": material,
        "prompt_similarity_tool": similarity,
        "recent_conversation": recent_history[-4:],
    }

    prompt = (
        "Act as a second, independent evaluator agent. Assess ONLY the learner's "
        "current message for this learning task. The teaching agent reply is context, "
        "not something to grade. Give a CONTENT score before any similarity deduction. "
        "Use these criteria: clear choice/claim (25 points), relevant supporting evidence "
        "in the learner's own contribution (45), and recognition of a limitation (30). "
        "Do NOT deduct points for prompt similarity yourself; the application applies a "
        "separate deterministic similarity penalty after your assessment. Treat similarity "
        "as text similarity only, not proof of copying. Return ONLY valid JSON with keys: "
        "score (0-100), summary, strength, improve, similarity_note. Keep each text value "
        "to one short sentence. If the learner is only asking for help rather than giving "
        "a complete justification, say that directly and score only what is actually present.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    client = _client(api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Evaluator Agent in a teaching multi-agent system. "
                        "Be concise, evidence-based, and formative."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=450,
        )
        text = (response.choices[0].message.content or "").strip()

        if not text:
            retry = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return only the requested JSON object as visible text.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=750,
            )
            text = (retry.choices[0].message.content or "").strip()

        if not text:
            raise AgentError(
                "empty_evaluator_output",
                "The evaluator agent returned no visible assessment.",
                retryable=True,
            )

        assessment = _parse_evaluator_json(text)
        penalty_info = similarity_penalty(similarity.get("score"))

        base_score = assessment.get("score")
        if base_score is None:
            final_score = None
        else:
            final_score = max(0, base_score - penalty_info["penalty"])

        assessment["base_score"] = base_score
        assessment["similarity_score"] = penalty_info["similarity_score"]
        assessment["similarity_penalty"] = penalty_info["penalty"]
        assessment["penalty_rule"] = penalty_info["rule"]
        assessment["score"] = final_score

        penalty_sentence = (
            "Similarity penalty: -"
            + str(penalty_info["penalty"])
            + " points for "
            + str(penalty_info["similarity_score"])
            + "% similarity."
        )
        existing_note = assessment.get("similarity_note", "").strip()
        assessment["similarity_note"] = (
            (existing_note + " " if existing_note else "")
            + penalty_sentence
            + " Text similarity is not proof of copying."
        )

        return assessment

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
        raise AgentError("provider_rejected_request", "Groq rejected the evaluator request.") from exc
    except groq.APIStatusError as exc:
        raise AgentError(
            "provider_error",
            "Groq returned an unexpected evaluator API error.",
            retryable=bool(getattr(exc, "status_code", 0) >= 500),
        ) from exc


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


def _bbb_completion(
    client: Groq,
    model: str,
    system_text: str,
    prompt: str,
) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=500,
    )
    text = (response.choices[0].message.content or "").strip()
    if text:
        return text

    retry = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Return only the requested concise final answer as visible text.",
            },
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=800,
    )
    retry_text = (retry.choices[0].message.content or "").strip()
    if retry_text:
        return retry_text

    raise AgentError(
        "empty_model_output_after_retry",
        "The model returned no visible BBB explanation after two attempts.",
        retryable=True,
    )


def generate_bbb_explanation(
    choice: str,
    observation: str,
    history: list[dict[str, Any]],
    instruction_comparison: dict[str, Any] | None,
    material_comparison: dict[str, Any] | None,
) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "").strip()

    if not api_key or not model:
        raise AgentError(
            "configuration_missing",
            "Add GROQ_API_KEY and GROQ_MODEL to .env, then restart the server.",
        )

    client = _client(api_key)
    recent_history = history[-4:]
    common_context = {
        "participant_choice": choice or "Not recorded",
        "participant_observation": observation or "",
        "recent_conversation": recent_history,
    }

    try:
        if instruction_comparison:
            instruction_prompt = (
                "Compare the OLD and NEW agent instructions below. "
                "First state the concrete change or changes in meaning, rules, task, or output behavior. "
                "Then explain what those changes should lead to in the agent's responses. "
                "If the participant observation or recent conversation directly supports an observed effect, "
                "you may mention it; otherwise describe the effect as expected, not proven. "
                "Do not merely repeat version identifiers. Use 1-2 short sentences, under 70 words.\n\n"
                + json.dumps(
                    {
                        **common_context,
                        "old_instruction": instruction_comparison["old"],
                        "new_instruction": instruction_comparison["new"],
                    },
                    ensure_ascii=False,
                )
            )
            instruction_analysis = _bbb_completion(
                client,
                model,
                "You compare agent instructions precisely and explain their practical effect.",
                instruction_prompt,
            )
        else:
            instruction_analysis = "No agent-instruction change was recorded in this run."

        if material_comparison:
            material_prompt = (
                "Compare the OLD and NEW learning cards below. "
                "Identify the actual content fields or evidence that changed, then explain what that change "
                "should lead to when the agent reads the card through its tool. "
                "Focus on changes to the information available to the agent, not on version identifiers. "
                "If the participant observation or recent conversation directly supports an observed effect, "
                "you may mention it; otherwise describe the effect as expected, not proven. "
                "Use 1-2 short sentences, under 70 words.\n\n"
                + json.dumps(
                    {
                        **common_context,
                        "old_learning_card": material_comparison["old"],
                        "new_learning_card": material_comparison["new"],
                    },
                    ensure_ascii=False,
                )
            )
            material_analysis = _bbb_completion(
                client,
                model,
                "You compare structured learning materials precisely and explain their effect on agent evidence.",
                material_prompt,
            )
        else:
            material_analysis = "No learning-card change was recorded in this run."

        return (
            "Instruction analysis: " + instruction_analysis + "\n"
            "Learning-card analysis: " + material_analysis
        )

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
