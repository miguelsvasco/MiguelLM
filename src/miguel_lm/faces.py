"""Persona-free ASCII/ANSI faces for the terminal client.

A stylized RobCo-terminal face that swaps expression per emotion and animates its
mouth while speaking. No personal data — purely generic art, so it ships in the
public package and needs nothing from the server. Mirrors the desktop app's
emotion vocabulary so both front-ends react the same way.
"""
from __future__ import annotations

from typing import List

EMOTIONS: List[str] = [
    "normal", "happy", "sad", "grumpy", "love", "scared", "confused", "mischievous", "thinking",
]

_W = 15  # inner width of the face frame
_FALLBACK = "normal"

# Per-emotion facial features (pure ASCII so monospace columns always line up).
_BROW = {
    "normal": "",
    "happy": "",
    "sad": "\\         /",
    "grumpy": "\\         /",
    "love": "",
    "scared": "/         \\",
    "confused": "?",
    "mischievous": "_         _",
    "thinking": "_       ___",
}
_EYES = {
    "normal": "o         o",
    "happy": "^         ^",
    "sad": "u         u",
    "grumpy": ">         <",
    "love": "<         <",
    "scared": "O         O",
    "confused": "o         O",
    "mischievous": "-         ^",
    "thinking": "o         -",
}
_MOUTH_REST = {
    "normal": "\\_______/",
    "happy": "\\__ ___/",
    "sad": "/-------\\",
    "grumpy": "/-------\\",
    "love": "\\__ ___/",
    "scared": "o",
    "confused": "o",
    "mischievous": "\\___ __/",
    "thinking": "  ---",
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
    key = emotion if emotion in _EYES else _FALLBACK
    if speaking:
        mouth = _MOUTH_TALK[frame % len(_MOUTH_TALK)]
    else:
        mouth = _MOUTH_REST[key]
    return _frame([_BROW[key], _EYES[key], _NOSE, mouth, ""])


def width() -> int:
    return _W + 2
