from __future__ import annotations

import asyncio
from typing import List

from rich.panel import Panel
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from miguel_lm.models import ClientMetadata
from miguel_lm.remote import RemoteClientRuntime


HELP_TEXT = """Commands:
/help                 show this help
/privacy              show the memory/privacy note
/memory on            enable durable memories on the remote service
/memory off           disable durable memories on the remote service
/memory list          list memories
/memory delete <id>   delete one memory
/memory clear         delete all memories
/voice test           synthesize and play a short voice test
/quit                 exit

Shortcuts:
Ctrl+R                push-to-talk recording
Ctrl+L                clear transcript
"""


class TerminalClientApp(App):
    CSS = """
    Screen {
        background: #050906;
        color: #b9ffb4;
    }

    Header, Footer {
        background: #08240f;
        color: #b9ffb4;
    }

    #layout {
        height: 100%;
    }

    #status {
        dock: top;
        height: 5;
        padding: 1 2;
        border: heavy #2cff70;
        background: #07150a;
        color: #b9ffb4;
    }

    #transcript {
        height: 1fr;
        padding: 1 2;
        border: round #1bb14b;
        background: #020503;
        color: #b9ffb4;
    }

    #input {
        dock: bottom;
        height: 3;
        border: tall #2cff70;
        background: #061107;
        color: #d3ffd0;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "record", "Push-to-talk"),
        Binding("ctrl+l", "clear_log", "Clear"),
        Binding("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self, runtime: RemoteClientRuntime, text_only: bool = False) -> None:
        super().__init__()
        self.runtime = runtime
        self.text_only = text_only
        self._busy = False
        self.metadata: ClientMetadata = runtime.metadata

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="layout"):
            yield Static("", id="status")
            yield RichLog(id="transcript", wrap=True, highlight=True, markup=True)
            with Horizontal():
                yield Input(placeholder="Type a message, or /help", id="input")
        yield Footer()

    async def on_mount(self) -> None:
        self.metadata = await self.runtime.refresh_metadata()
        self.title = self.metadata.app_name
        self.sub_title = self.metadata.subtitle
        self._update_status("Ready")
        log = self.query_one("#transcript", RichLog)
        log.write(Panel(self.metadata.intro_text, title=self.metadata.app_name, border_style="green"))
        if not self.runtime.status().memory_enabled:
            log.write(Panel(self._privacy_text(), title="Memory Is Off", border_style="yellow"))

    async def on_unmount(self) -> None:
        await self.runtime.close()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#input", Input).value = ""
        if not text:
            return
        if text.startswith("/"):
            await self._handle_command(text)
            return
        asyncio.create_task(self._handle_message(text, source="You"))

    async def action_record(self) -> None:
        if self.text_only:
            self._system("Voice input is disabled for this run.")
            return
        if self._busy:
            self._system("Wait for the current turn to finish first.")
            return
        self._busy = True
        self._update_status("Recording %.1fs..." % self.runtime.config.input_audio.record_seconds)
        try:
            text = await self.runtime.listen_once()
            self._busy = False
            await self._handle_message(text, source="You (voice)")
        except Exception as exc:
            self._system("Voice input failed: %s" % exc)
        finally:
            self._busy = False
            self._update_status("Ready")

    def action_clear_log(self) -> None:
        self.query_one("#transcript", RichLog).clear()

    async def _handle_message(self, text: str, source: str = "You") -> None:
        if self._busy:
            self._system("Wait for the current turn to finish first.")
            return
        self._busy = True
        log = self.query_one("#transcript", RichLog)
        log.write(Panel(text, title=source, border_style="bright_green"))
        self._update_status("Thinking...")
        try:
            response = await self.runtime.answer(text)
        except Exception as exc:
            self._system("Dialogue failed: %s" % exc)
            self._busy = False
            self._update_status("Ready")
            return
        log.write(Panel(response.spoken_text, title=self.metadata.assistant_label, border_style="green"))
        self._busy = False
        self._update_status("Speaking...")
        asyncio.create_task(self._speak(response.spoken_text))

    async def _speak(self, text: str) -> None:
        try:
            await self.runtime.speak(text)
        except Exception as exc:
            self._system("Voice offline: %s" % exc)
        finally:
            self._update_status("Ready")

    async def _handle_command(self, command: str) -> None:
        parts = command.split()
        verb = parts[0].lower()
        if verb in {"/quit", "/exit"}:
            await self.runtime.close()
            self.exit()
            return
        if verb == "/help":
            self._system(HELP_TEXT)
            return
        if verb == "/privacy":
            self._system(self._privacy_text())
            return
        if verb == "/voice" and len(parts) > 1 and parts[1] == "test":
            await self._voice_test()
            return
        if verb == "/memory":
            await self._memory_command(parts)
            return
        self._system("Unknown command. Type /help.")

    async def _memory_command(self, parts: List[str]) -> None:
        if len(parts) == 1 or parts[1] == "list":
            rows = self.runtime.memory_summary()
            self._system("\n".join(rows) if rows else "No memories stored.")
            return
        action = parts[1].lower()
        if action == "on":
            self.runtime.set_memory_enabled(True)
            self._system("Durable memory is now ON on the remote service.")
            self._update_status("Ready")
            return
        if action == "off":
            self.runtime.set_memory_enabled(False)
            self._system("Durable memory is now OFF on the remote service.")
            self._update_status("Ready")
            return
        if action == "delete" and len(parts) >= 3:
            deleted = self.runtime.delete_memory(parts[2])
            self._system("Deleted." if deleted else "No memory with that id.")
            return
        if action == "clear":
            count = self.runtime.clear_memory()
            self._system("Deleted %d memories." % count)
            return
        self._system("Usage: /memory on|off|list|delete <id>|clear")

    async def _voice_test(self) -> None:
        self._system("Testing voice...")
        try:
            await self.runtime.speak(self.metadata.voice_test_text)
            self._system("Voice test finished.")
        except Exception as exc:
            self._system("Voice test failed: %s" % exc)

    def _privacy_text(self) -> str:
        return self.metadata.privacy_text

    def _system(self, text: str) -> None:
        self.query_one("#transcript", RichLog).write(Panel(text, title="System", border_style="yellow"))

    def _update_status(self, activity: str) -> None:
        status = self.runtime.status()
        voice = "voice:online" if status.tts_healthy else "voice:offline"
        memory = "memory:on" if status.memory_enabled else "memory:off"
        player = status.player or "no-player"
        text = Text()
        text.append(" %s " % self.metadata.status_label, style="bold #2cff70")
        text.append("| %s " % activity, style="#b9ffb4")
        text.append("| %s " % voice, style="#2cff70" if status.tts_healthy else "yellow")
        text.append("| %s " % memory, style="#2cff70" if status.memory_enabled else "yellow")
        text.append("| audio:%s " % player, style="#b9ffb4")
        if status.tts_endpoint:
            text.append("| %s" % status.tts_endpoint, style="dim #83d983")
        self.query_one("#status", Static).update(text)
