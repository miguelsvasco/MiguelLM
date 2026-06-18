from __future__ import annotations

import json
import re
from typing import Any, Dict

from miguel_lm.models import DialogueResponse


def parse_dialogue_json(text: str, provider: str) -> DialogueResponse:
    data = _extract_json(text)
    return DialogueResponse.from_mapping(data, provider=provider)


def _extract_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {"spoken_text": stripped}
