from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


VALID_DECISIONS = {"VIOLATION", "NO_VIOLATION", "UNCERTAIN"}


def is_llm_configured() -> bool:
    return bool(_api_key())


def review_with_configured_llm(evidence: dict[str, Any]) -> dict[str, Any] | None:
    api_key = _api_key()
    if not api_key:
        return None

    endpoint = _chat_endpoint()
    model = os.environ.get("LLM_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30"))
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a video governance machine-review assistant. "
                    "Return only strict JSON. Do not include CSAM or critical escalation labels."
                ),
            },
            {"role": "user", "content": _build_prompt(evidence)},
        ],
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None

    try:
        completion = json.loads(raw)
        content = completion["choices"][0]["message"]["content"]
        result = _parse_json_object(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None

    decision = str(result.get("decision", "UNCERTAIN")).upper()
    if decision not in VALID_DECISIONS:
        decision = "UNCERTAIN"

    confidence = _coerce_confidence(result.get("confidence"))
    evidence_refs = result.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        evidence_refs = []

    return {
        "decision": decision,
        "confidence": confidence,
        "reason": str(result.get("reason", "")).strip() or "LLM returned no rationale.",
        "evidence_refs": [str(item) for item in evidence_refs[:8]],
        "model": model,
        "endpoint": endpoint,
    }


def _api_key() -> str:
    return os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()


def _chat_endpoint() -> str:
    base_url = os.environ.get("LLM_BASE_URL", os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    base_url = base_url.rstrip("/")
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _build_prompt(evidence: dict[str, Any]) -> str:
    compact = {
        "review_scope": {
            "jurisdiction": evidence.get("jurisdiction", "global"),
            "human_final_states": ["pass", "block"],
            "disabled_features": ["CSAM", "critical_escalation", "seven_level_disposition", "need_more_context"],
        },
        "metadata": evidence.get("metadata", {}),
        "video_meta": evidence.get("video_meta", {}),
        "pre_filter_results": evidence.get("pre_filter_results", {}),
        "asr_transcript": evidence.get("asr_transcript", [])[:5],
        "ocr_results": evidence.get("ocr_results", [])[:5],
        "scene_tags": evidence.get("scene_tags", [])[:8],
        "extraction_notes": evidence.get("extraction_notes", [])[:8],
    }
    return (
        "Review this evidence package for general platform policy risk.\n"
        "Return JSON with keys: decision, confidence, reason, evidence_refs.\n"
        "decision must be one of VIOLATION, NO_VIOLATION, UNCERTAIN.\n"
        "confidence must be a number from 0 to 1.\n"
        "evidence_refs should cite fields such as metadata.title, asr_transcript[0].text, or pre_filter_results.rule_hits.\n\n"
        f"Evidence:\n{json.dumps(compact, ensure_ascii=False)[:12000]}"
    )


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("LLM JSON payload is not an object", text, 0)
    return payload


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(max(confidence, 0.0), 1.0)
