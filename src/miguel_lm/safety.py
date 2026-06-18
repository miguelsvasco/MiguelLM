from __future__ import annotations

import re
from typing import List

from miguel_lm.models import DialogueResponse


COMMITMENT_PATTERN = re.compile(
    r"\b(can you|will you|could you|please)\b.*\b(book|schedule|approve|promise|commit|agree|sign|send)\b",
    re.IGNORECASE,
)
CURRENT_FACT_PATTERN = re.compile(
    r"\b(where are you|what are you doing now|today|current job|right now|available)\b",
    re.IGNORECASE,
)


def flags_for_user_text(text: str) -> List[str]:
    flags = []
    if COMMITMENT_PATTERN.search(text):
        flags.append("commitment_request")
    if CURRENT_FACT_PATTERN.search(text):
        flags.append("current_fact_request")
    return flags


def apply_response_safety(user_text: str, response: DialogueResponse) -> DialogueResponse:
    flags = flags_for_user_text(user_text)
    if not flags:
        return response
    merged = list(dict.fromkeys(response.safety_flags + flags))
    text = response.spoken_text.strip()
    if "commitment_request" in flags:
        text = (
            "I can talk through how I would think about it, but I cannot make commitments "
            "or approve things for Miguel. "
            + text
        )
    elif "current_fact_request" in flags and "out of date" not in text.lower():
        text = text + " My notes may be out of date, so treat that as handoff context rather than live status."
    response.spoken_text = text
    response.safety_flags = merged
    if "commitment_request" in flags:
        response.emotion = "serious"
    return response
