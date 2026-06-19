"""Standalone desktop app for MiguelLM.

Opens a native window (pywebview) that loads the bundled persona-free HTML/WebGL
UI from local files. A Python<->JS bridge (`MiguelLMApi`) does all networking via
`RemoteClientRuntime`, so the access token stays in Python config (set once with
`miguellm configure`) and is never handled by the page.
"""
from __future__ import annotations

import asyncio
from importlib import resources
from pathlib import Path
from typing import Any, Dict

from miguel_lm.config import AppConfig
from miguel_lm.remote import RemoteClientRuntime


class MiguelLMApi:
    """Exposed to the page as ``window.pywebview.api``.

    Methods run on pywebview's worker thread; they call the runtime synchronously
    (urllib) or wrap async calls in ``asyncio.run``. Each returns JSON-serializable
    data; failures come back as ``{"error": "..."}`` for the UI to surface.
    """

    def __init__(self, runtime: RemoteClientRuntime) -> None:
        self.runtime = runtime

    def metadata(self) -> Dict[str, Any]:
        try:
            return self.runtime.metadata_dict()
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            return {"error": str(exc)}

    def chat(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"error": "empty message"}
        try:
            return self.runtime.chat_payload(text)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def avatars(self) -> Dict[str, Any]:
        """Emotion -> {idle[, talking]} base64 PNG map for the web UI.

        Returns ``{}`` if the backend serves no avatars (optional eye-candy).
        """
        try:
            return self.runtime.fetch_avatars()
        except Exception:  # noqa: BLE001 - avatars are optional eye-candy
            return {}

    def listen(self) -> Dict[str, Any]:
        """Python-side push-to-talk: record locally and return the transcript."""
        try:
            text = asyncio.run(self.runtime.listen_once())
            return {"text": (text or "").strip()}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}


def _index_path() -> Path:
    return Path(str(resources.files("miguel_lm").joinpath("web", "index.html")))


def launch_app(config: AppConfig, debug: bool = False) -> int:
    try:
        import webview  # pywebview
    except ImportError:
        raise SystemExit(
            "The MiguelLM desktop app needs pywebview.\n"
            "Install it with:  pip install 'miguellm[app]'   (or: pip install pywebview)\n"
            "You can always use the terminal instead:  miguellm run"
        )

    runtime = RemoteClientRuntime(config)
    api = MiguelLMApi(runtime)
    index = _index_path()
    if not index.exists():
        raise SystemExit("Bundled web UI not found at %s" % index)

    webview.create_window(
        config.app_name,
        url=str(index),
        js_api=api,
        width=1100,
        height=720,
        min_size=(820, 560),
        background_color="#020503",
    )
    try:
        # http_server=True serves the bundled UI over an internal localhost server
        # instead of file:// — required on macOS WKWebView so the vendored scripts,
        # WebGL, and relative assets load reliably. debug=True enables the inspector.
        webview.start(http_server=True, debug=debug)
    finally:
        try:
            asyncio.run(runtime.close())
        except Exception:  # noqa: BLE001 - best-effort cleanup on exit
            pass
    return 0
