"""Tab completion for the mudale console."""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from mudale_core.modules import MODULE_REGISTRY


class MudaleCompleter(Completer):
    """Context-aware tab completer for the mudale REPL."""

    def __init__(self, console):
        self._console = console

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        word_count = len(words)

        if not text or (word_count == 1 and not text.endswith(" ")):
            prefix = words[0] if words else ""
            yield from self._complete_commands(prefix)
            return

        cmd = words[0].lower()

        if cmd == "use" and word_count <= 2:
            prefix = words[1] if word_count == 2 and not text.endswith(" ") else ""
            yield from self._complete_modules(prefix)

        elif cmd == "set" and self._console.current_module:
            if word_count == 2 and not text.endswith(" "):
                prefix = words[1]
                yield from self._complete_options(prefix)
            elif word_count == 3 and not text.endswith(" "):
                opt_name = words[1].upper()
                prefix = words[2]
                yield from self._complete_option_values(opt_name, prefix)
            elif word_count == 2 and text.endswith(" "):
                yield from self._complete_options("")

        elif cmd == "unset" and self._console.current_module:
            prefix = words[1] if word_count == 2 and not text.endswith(" ") else ""
            yield from self._complete_options(prefix)

        elif cmd == "show":
            prefix = words[1] if word_count == 2 and not text.endswith(" ") else ""
            for sub in ("options", "modules", "tunnels", "scans", "services"):
                if sub.startswith(prefix.lower()):
                    yield Completion(sub, start_position=-len(prefix))

        elif cmd == "workspace":
            prefix = words[1] if word_count == 2 and not text.endswith(" ") else ""
            for sub in ("list", "use", "add", "show"):
                if sub.startswith(prefix.lower()):
                    yield Completion(sub, start_position=-len(prefix))

        elif cmd == "kill":
            prefix = words[1] if word_count == 2 and not text.endswith(" ") else ""
            for t in self._console.engine.db.list_tunnels(active_only=True):
                tid = str(t.id)
                if tid.startswith(prefix):
                    yield Completion(tid, start_position=-len(prefix), display_meta=f"{t.kind}")

    def _complete_commands(self, prefix: str):
        commands = [
            ("use", "Select a module"),
            ("set", "Set a module option"),
            ("unset", "Clear a module option"),
            ("run", "Execute the current module"),
            ("back", "Deselect current module"),
            ("show", "Show options/modules/tunnels/scans"),
            ("jobs", "List active tunnels and scans"),
            ("kill", "Stop a tunnel or scan"),
            ("sessions", "List active SSH sessions"),
            ("services", "List discovered services"),
            ("forward", "Quick local forward to a service"),
            ("sync", "Sync state to web dashboard"),
            ("workspace", "Manage workspaces"),
            ("status", "Engine status"),
            ("history", "Command history"),
            ("help", "Show help"),
            ("banner", "Show banner"),
            ("exit", "Exit console"),
            ("quit", "Exit console"),
        ]
        for cmd, desc in commands:
            if cmd.startswith(prefix.lower()):
                yield Completion(cmd, start_position=-len(prefix), display_meta=desc)

    def _complete_modules(self, prefix: str):
        for name in MODULE_REGISTRY:
            if name.startswith(prefix.lower()):
                yield Completion(name, start_position=-len(prefix))

    def _complete_options(self, prefix: str):
        mod = self._console.current_module
        if mod is None:
            return
        for opt in mod.options:
            if opt.name.upper().startswith(prefix.upper()):
                yield Completion(
                    opt.name,
                    start_position=-len(prefix),
                    display_meta=f"{'*' if opt.required else ''}{opt.description[:40]}",
                )

    def _complete_option_values(self, opt_name: str, prefix: str):
        mod = self._console.current_module
        if mod is None:
            return
        for opt in mod.options:
            if opt.name.upper() == opt_name.upper() and opt.choices:
                for choice in opt.choices:
                    if choice.startswith(prefix.lower()):
                        yield Completion(choice, start_position=-len(prefix))
