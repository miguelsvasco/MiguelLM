"""Persona-free ASCII/ANSI faces for the terminal client.

A stylized RobCo-terminal face that swaps expression per emotion and animates its
mouth while speaking. No personal data — purely generic art, so it ships in the
public package and needs nothing from the server. Mirrors the desktop app's
emotion vocabulary so both front-ends react the same way.
"""
from __future__ import annotations

from typing import List

EMOTIONS: List[str] = ["warm", "amused", "confused", "serious", "speaking"]

_W = 15  # inner width of the face frame

# Per-emotion facial features (pure ASCII so monospace columns always line up).
_BROW = {
    "warm": "",
    "amused": "/         \\",
    "confused": "?",
    "serious": "___     ___",
    "speaking": "",
}
_EYES = {
    "warm": "o         o",
    "amused": "^         ^",
    "confused": "o         O",
    "serious": "=         =",
    "speaking": "o         o",
}
_MOUTH_REST = {
    "warm": "\\_______/",
    "amused": "\\__ ___/",
    "confused": "o",
    "serious": "/-------\\",
    "speaking": "---------",
}
_MOUTH_TALK = ["---------", "(  ___  )"]  # closed / open, toggled while speaking
_NOSE = "L"


def _row(text: str) -> str:
    return "|" + text[:_W].center(_W) + "|"


def _frame(lines: List[str]) -> str:
    top = "." + "-" * _W + "."
    bot = "'" + "-" * _W + "'"
    return "\n".join([top] + [_row(line) for line in lines] + [bot])


def render(emotion: str, frame: int = 0, speaking: bool = False) -> str:
    """Return the ASCII face for ``emotion``.

    While ``speaking`` the mouth alternates between closed/open based on ``frame``
    (a simple rhythmic lip-sync). Unknown emotions fall back to ``warm``.
    """
    key = emotion if emotion in _EYES else "warm"
    if speaking:
        mouth = _MOUTH_TALK[frame % len(_MOUTH_TALK)]
    else:
        mouth = _MOUTH_REST[key]
    return _frame([_BROW[key], _EYES[key], _NOSE, mouth, ""])


def width() -> int:
    return _W + 2
