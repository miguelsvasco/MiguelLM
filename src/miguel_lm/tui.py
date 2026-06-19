from __future__ import annotations

import asyncio
import random
from typing import List, Optional

from rich.panel import Panel
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from miguel_lm import faces
from miguel_lm.models import AudioClip, ClientMetadata
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


class Viewport(Static):
    """ASCII face floating in an animated hyperspace starfield."""

    COLS = 42
    ROWS = 16

    def __init__(self) -> None:
        super().__init__("", id="viewport", markup=False)
        self._emotion = "warm"
        self._speaking = False
        self._frame = 0
        self._stars: List[list] = []

    def on_mount(self) -> None:
        self._stars = [
            [random.uniform(0, self.COLS), random.randint(0, self.ROWS - 1), random.choice(".:+*")]
            for _ in range(46)
        ]
        self.set_interval(0.12, self._tick)

    def set_emotion(self, emotion: str) -> None:
        self._emotion = emotion

    def set_speaking(self, on: bool) -> None:
        self._speaking = on

    def _tick(self) -> None:
        self._frame += 1
        speed = 1.8 if self._speaking else 0.7
        for star in self._stars:
            star[0] += speed
            if star[0] >= self.COLS:
                star[0] = 0.0
                star[1] = random.randint(0, self.ROWS - 1)
                star[2] = random.choice(".:+*")
        self.update(self._build_frame())

    def _build_frame(self) -> str:
        grid = [[" "] * self.COLS for _ in range(self.ROWS)]
        for x, y, ch in self._stars:
            xi = int(x)
            if 0 <= xi < self.COLS and 0 <= y < self.ROWS:
                grid[int(y)][xi] = ch
        face = faces.render(self._emotion, self._frame, self._speaking).splitlines()
        fh = len(face)
        fw = max((len(line) for line in face), default=0)
        oy = max(0, (self.ROWS - fh) // 2)
        ox = max(0, (self.COLS - fw) // 2)
        for i, line in enumerate(face):
            for j, ch in enumerate(line):
                if ch != " ":
                    yy, xx = oy + i, ox + j
                    if 0 <= yy < self.ROWS and 0 <= xx < self.COLS:
                        grid[yy][xx] = ch
        return "\n".join("".join(row) for row in grid)


class TerminalClientApp(App):
    CSS = """
    Screen {
        layers: base overlay;
        background: #050906;
        color: #b9ffb4;
    }

    Header, Footer {
        background: #08240f;
        color: #b9ffb4;
    }

    #stage-row { height: 1fr; }

    #viewport {
        width: 46;
        height: 100%;
        padding: 1 1;
        border: heavy #2cff70;
        background: #010301;
        color: #2cff70;
    }

    #chat { width: 1fr; }

    #status {
        height: 1;
        padding: 0 1;
        color: #2cff70;
    }

    #transcript {
        height: 1fr;
        padding: 1 2;
        border: round #1bb14b;
        background: #020503;
        color: #b9ffb4;
    }

    #reply {
        height: auto;
        max-height: 8;
        padding: 0 2;
        color: #d3ffd0;
    }

    #thinking {
        height: 1;
        padding: 0 2;
        color: #4f8f5a;
    }

    #input {
        dock: bottom;
        height: 3;
        border: tall #2cff70;
        background: #061107;
        color: #d3ffd0;
    }

    #boot {
        layer: overlay;
        width: 100%;
        height: 100%;
        padding: 2 4;
        background: #020503;
        color: #2cff70;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "record", "Push-to-talk"),
        Binding("ctrl+l", "clear_log", "Clear"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("escape", "skip_boot", "Skip", show=False),
    ]

    def __init__(self, runtime: RemoteClientRuntime, text_only: bool = False) -> None:
        super().__init__()
        self.runtime = runtime
        self.text_only = text_only
        self._busy = False
        self.metadata: ClientMetadata = runtime.metadata
        self._booting = True
        self._thinking = False
        self._think_dots = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="stage-row"):
            yield Viewport()
            with Vertical(id="chat"):
                yield Static("", id="status")
                yield RichLog(id="transcript", wrap=True, highlight=True, markup=True)
                yield Static("", id="reply", markup=False)
                yield Static("", id="thinking", markup=False)
                yield Input(placeholder="Type a message, or /help", id="input")
        yield Static("", id="boot", markup=False)
        yield Footer()

    async def on_mount(self) -> None:
        self.metadata = await self.runtime.refresh_metadata()
        self.title = self.metadata.app_name
        self.sub_title = self.metadata.subtitle
        self._update_status("Booting")
        self.set_interval(0.5, self._blink_thinking)
        await self._run_boot()

    async def on_unmount(self) -> None:
        await self.runtime.close()

    # ---------------- boot screen ----------------
    async def _run_boot(self) -> None:
        boot = self.query_one("#boot", Static)
        lines = self.metadata.boot_lines or []
        shown = ""
        for line in lines:
            if not self._booting:
                break
            for ch in line:
                if not self._booting:
                    break
                shown += ch
                boot.update(shown + "█")
                await asyncio.sleep(0.012)
            shown += "\n"
            boot.update(shown + "█")
            await asyncio.sleep(0.06)
        if self._booting:
            await asyncio.sleep(0.5)
        self._finish_boot()

    def action_skip_boot(self) -> None:
        self._finish_boot()

    def _finish_boot(self) -> None:
        if not self._booting:
            return
        self._booting = False
        self.query_one("#boot", Static).display = False
        self._update_status("Ready")
        log = self.query_one("#transcript", RichLog)
        log.write(Panel(self.metadata.intro_text, title=self.metadata.app_name, border_style="green"))
        if not self.runtime.status().memory_enabled:
            log.write(Panel(self._privacy_text(), title="Memory Is Off", border_style="yellow"))
        self.query_one("#input", Input).focus()

    # ---------------- input handling ----------------
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.query_one("#input", Input).value = ""
        if not text or self._booting:
            return
        if text.startswith("/"):
            await self._handle_command(text)
            return
        asyncio.create_task(self._handle_message(text, source="You"))

    async def action_record(self) -> None:
        if self.text_only:
            self._system("Voice input is disabled for this run.")
            return
        if self._busy or self._booting:
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

    # ---------------- conversation ----------------
    async def _handle_message(self, text: str, source: str = "You") -> None:
        if self._busy:
            return
        self._busy = True
        log = self.query_one("#transcript", RichLog)
        log.write(Panel(text, title=source, border_style="bright_green"))
        self._set_thinking(True)
        self.query_one("Viewport", Viewport).set_emotion("confused")
        try:
            response = await self.runtime.answer(text)
        except Exception as exc:
            self._set_thinking(False)
            self._system("Dialogue failed: %s" % exc)
            self.query_one("Viewport", Viewport).set_emotion("serious")
            self._busy = False
            self._update_status("Ready")
            return
        self._set_thinking(False)
        viewport = self.query_one("Viewport", Viewport)
        viewport.set_emotion(response.emotion or "warm")
        await self._deliver(response.spoken_text, response.emotion or "warm")
        self._busy = False
        self._update_status("Ready")

    async def _deliver(self, text: str, emotion: str) -> None:
        viewport = self.query_one("Viewport", Viewport)
        clip = await self._safe_synthesize(text)
        duration = self._clip_duration(clip)
        self._update_status("Speaking")
        viewport.set_speaking(True)
        play_task = asyncio.create_task(self._play(clip)) if clip is not None else None
        await self._typewrite(text, duration)
        if play_task is not None:
            try:
                await play_task
            except Exception:
                pass
        viewport.set_speaking(False)
        viewport.set_emotion("warm" if emotion == "speaking" else emotion)
        # Commit the finished line to the transcript and clear the live reply area.
        self.query_one("#transcript", RichLog).write(
            Panel(text, title=self.metadata.assistant_label, border_style="green")
        )
        self.query_one("#reply", Static).update("")

    async def _typewrite(self, text: str, duration: Optional[float]) -> None:
        reply = self.query_one("#reply", Static)
        per = max(0.012, min(0.06, duration / len(text))) if (duration and text) else 0.028
        shown = ""
        for ch in text:
            shown += ch
            reply.update(shown + "█")
            await asyncio.sleep(per)
        reply.update(shown)

    async def _safe_synthesize(self, text: str) -> Optional[AudioClip]:
        try:
            return await self.runtime.synthesize(text)
        except Exception:
            return None

    async def _play(self, clip: AudioClip) -> None:
        try:
            await self.runtime.player.play(clip)
        except Exception as exc:
            self._system("Voice offline: %s" % exc)

    @staticmethod
    def _clip_duration(clip: Optional[AudioClip]) -> Optional[float]:
        if clip is None or not clip.sample_rate:
            return None
        return (len(clip.pcm) // 2) / float(clip.sample_rate)

    # ---------------- thinking indicator ----------------
    def _set_thinking(self, on: bool) -> None:
        self._thinking = on
        if not on:
            self.query_one("#thinking", Static).update("")
        else:
            self._update_status("Thinking")

    def _blink_thinking(self) -> None:
        if not self._thinking:
            return
        self._think_dots = (self._think_dots + 1) % 4
        dots = "." * self._think_dots
        self.query_one("#thinking", Static).update(
            "%s is thinking%s" % (self.metadata.assistant_label, dots)
        )

    # ---------------- commands ----------------
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
        voice_color = "#2cff70" if status.tts_healthy else "yellow"
        memory_color = "#2cff70" if status.memory_enabled else "yellow"
        voice = "voice:online" if status.tts_healthy else "voice:offline"
        memory = "memory:on" if status.memory_enabled else "memory:off"
        markup = (
            "[bold #2cff70] %s [/]"
            "[#b9ffb4]| %s [/]"
            "[%s]| %s [/]"
            "[%s]| %s [/]"
        ) % (self.metadata.status_label, activity, voice_color, voice, memory_color, memory)
        self.query_one("#status", Static).update(markup)
