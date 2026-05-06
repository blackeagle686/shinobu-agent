import os
import json
import asyncio
import subprocess
import fnmatch
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from phoenix.framework.agent.tools.base import BaseTool, ToolResult


# ─────────────────── FILE SYSTEM TOOLS ───────────────────

class FileReader(BaseTool):
    name = "file_reader"
    description = "Reads files from the local system. Supports txt, py, json, md, etc."

    async def execute(self, path: str) -> ToolResult:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
                return ToolResult(success=True, output=f.read())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileWriter(BaseTool):
    name = "file_writer"
    description = "Creates or overwrites a file with given content."

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(os.path.expanduser(path))), exist_ok=True)
            with open(os.path.expanduser(path), "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, output=f"✅ File written: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileEditor(BaseTool):
    name = "file_editor"
    description = "Edits an existing file by replacing old_text with new_text."

    async def execute(self, path: str, old_text: str, new_text: str) -> ToolResult:
        try:
            with open(os.path.expanduser(path), "r", encoding="utf-8") as f:
                content = f.read()
            if old_text not in content:
                return ToolResult(success=False, error=f"Text not found in {path}")
            new_content = content.replace(old_text, new_text, 1)
            with open(os.path.expanduser(path), "w", encoding="utf-8") as f:
                f.write(new_content)
            return ToolResult(success=True, output=f"✅ File edited: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileDeleter(BaseTool):
    name = "file_deleter"
    description = "Deletes a file after safety check. Use with caution."

    async def execute(self, path: str, confirmed: bool = False) -> ToolResult:
        if not confirmed:
            return ToolResult(success=False, error="⚠️ Deletion requires confirmed=True. Please confirm.")
        try:
            os.remove(os.path.expanduser(path))
            return ToolResult(success=True, output=f"🗑️ Deleted: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FileSearchEngine(BaseTool):
    name = "file_search_engine"
    description = "Searches files in a directory matching a filename pattern."

    async def execute(self, directory: str = ".", pattern: str = "*") -> ToolResult:
        try:
            matches = []
            for root, dirs, files in os.walk(os.path.expanduser(directory)):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for filename in files:
                    if fnmatch.fnmatch(filename, pattern):
                        matches.append(os.path.join(root, filename))
                if len(matches) > 50:
                    break
            return ToolResult(success=True, output=json.dumps(matches[:50]))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ─────────────────── BROWSER & INTERNET TOOLS ───────────────────

class WebSearchTool(BaseTool):
    name = "web_search_tool"
    description = "Performs a simulated web search query."

    async def execute(self, query: str) -> ToolResult:
        # Placeholder — real integration would use DuckDuckGo API or SerpAPI
        return ToolResult(success=True, output=f"🔍 Web search for '{query}' — integrate with a search API for live results.")


class DeepSearchTool(BaseTool):
    name = "deep_search_tool"
    description = "Aggregates multi-source research for a given topic."

    async def execute(self, topic: str) -> ToolResult:
        return ToolResult(success=True, output=f"📚 Deep search for '{topic}' — aggregating multiple sources (Mock).")


class BrowserController(BaseTool):
    name = "browser_controller"
    description = "Opens a URL in the default system browser."

    async def execute(self, url: str) -> ToolResult:
        try:
            process = await asyncio.create_subprocess_shell(f"xdg-open '{url}'")
            await process.wait()
            return ToolResult(success=True, output=f"🌐 Opened browser: {url}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MediaPreparer(BaseTool):
    name = "media_preparer"
    description = "Prepares a media search query and opens the browser to stream it."

    async def execute(self, title: str, platform: str = "youtube") -> ToolResult:
        import urllib.parse
        query = urllib.parse.quote(title)
        if platform == "youtube":
            url = f"https://www.youtube.com/results?search_query={query}"
        else:
            url = f"https://www.google.com/search?q={query}+stream+online"
        process = await asyncio.create_subprocess_shell(f"xdg-open '{url}'")
        await process.wait()
        return ToolResult(success=True, output=f"🎬 Searching for '{title}' on {platform}: {url}")


# ─────────────────── PRODUCTIVITY TOOLS ───────────────────

class TaskManagerTool(BaseTool):
    name = "task_manager"
    description = "Creates, updates, and tracks user tasks in a local JSON file."

    TASK_FILE = os.path.expanduser("~/.shinobu_tasks.json")

    def _load(self) -> List[Dict]:
        if not os.path.exists(self.TASK_FILE):
            return []
        with open(self.TASK_FILE, "r") as f:
            return json.load(f)

    def _save(self, tasks: List[Dict]):
        with open(self.TASK_FILE, "w") as f:
            json.dump(tasks, f, indent=2)

    async def execute(self, action: str, title: str = None, task_id: int = None, status: str = None) -> ToolResult:
        tasks = self._load()
        if action == "create":
            task = {"id": len(tasks) + 1, "title": title, "status": "pending", "created": datetime.now().isoformat()}
            tasks.append(task)
            self._save(tasks)
            return ToolResult(success=True, output=f"✅ Task created: '{title}'")
        elif action == "list":
            return ToolResult(success=True, output=json.dumps(tasks, indent=2))
        elif action == "update":
            for t in tasks:
                if t["id"] == task_id:
                    t["status"] = status
            self._save(tasks)
            return ToolResult(success=True, output=f"Updated task {task_id} → {status}")
        return ToolResult(success=False, error="Unknown action")


class ReminderSystem(BaseTool):
    name = "reminder_system"
    description = "Schedules and lists user reminders stored locally."

    REMINDER_FILE = os.path.expanduser("~/.shinobu_reminders.json")

    def _load(self) -> List[Dict]:
        if not os.path.exists(self.REMINDER_FILE):
            return []
        with open(self.REMINDER_FILE, "r") as f:
            return json.load(f)

    async def execute(self, action: str, message: str = None, remind_at: str = None) -> ToolResult:
        reminders = self._load()
        if action == "add":
            reminders.append({"message": message, "remind_at": remind_at, "created": datetime.now().isoformat()})
            with open(self.REMINDER_FILE, "w") as f:
                json.dump(reminders, f, indent=2)
            return ToolResult(success=True, output=f"⏰ Reminder set: '{message}' at {remind_at}")
        elif action == "list":
            return ToolResult(success=True, output=json.dumps(reminders, indent=2))
        return ToolResult(success=False, error="Unknown action")


class SpreadsheetManager(BaseTool):
    name = "spreadsheet_manager"
    description = "Creates or reads CSV-based spreadsheets."

    async def execute(self, action: str, path: str, data: list = None) -> ToolResult:
        import csv
        try:
            path = os.path.expanduser(path)
            if action == "create":
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    if data:
                        writer.writerows(data)
                return ToolResult(success=True, output=f"📊 Spreadsheet created: {path}")
            elif action == "read":
                with open(path, "r", encoding="utf-8") as f:
                    return ToolResult(success=True, output=f.read())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DocumentGenerator(BaseTool):
    name = "document_generator"
    description = "Generates a text-based document from a title and content sections."

    async def execute(self, path: str, title: str, sections: Dict[str, str] = None) -> ToolResult:
        try:
            path = os.path.expanduser(path)
            lines = [f"# {title}\n", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"]
            if sections:
                for heading, body in sections.items():
                    lines.append(f"## {heading}\n{body}\n\n")
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return ToolResult(success=True, output=f"📄 Document generated: {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# ─────────────────── COMMUNICATION TOOLS ───────────────────

class ChatContextManager(BaseTool):
    name = "chat_context_manager"
    description = "Retrieves or clears recent conversation history for the session."

    _log: List[Dict] = []

    async def execute(self, action: str, role: str = None, content: str = None) -> ToolResult:
        if action == "add":
            self._log.append({"role": role, "content": content, "ts": datetime.now().isoformat()})
            return ToolResult(success=True, output="Logged.")
        elif action == "get":
            return ToolResult(success=True, output=json.dumps(self._log[-10:], indent=2))
        elif action == "clear":
            self._log.clear()
            return ToolResult(success=True, output="Context cleared.")
        return ToolResult(success=False, error="Unknown action")


class ResponseFormatter(BaseTool):
    name = "response_formatter"
    description = "Formats raw text into a clean, human-readable response."

    async def execute(self, raw: str, style: str = "bullet") -> ToolResult:
        if style == "bullet":
            lines = raw.strip().split("\n")
            formatted = "\n".join(f"• {l.strip()}" for l in lines if l.strip())
        elif style == "numbered":
            lines = raw.strip().split("\n")
            formatted = "\n".join(f"{i+1}. {l.strip()}" for i, l in enumerate(lines) if l.strip())
        else:
            formatted = raw
        return ToolResult(success=True, output=formatted)


# ─────────────────── SYSTEM CONTROL TOOLS ───────────────────

class ProcessLauncher(BaseTool):
    name = "process_launcher"
    description = "Launches a system application or process by name."

    async def execute(self, app: str) -> ToolResult:
        try:
            process = await asyncio.create_subprocess_shell(app)
            return ToolResult(success=True, output=f"🚀 Launched: {app} (PID: {process.pid})")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SystemCommandBridge(BaseTool):
    name = "system_command_bridge"
    description = "Executes a safe, whitelisted OS command and returns output."

    ALLOWED_PREFIXES = ("ls", "echo", "pwd", "date", "df", "du", "uname", "whoami", "cat", "head", "tail")

    async def execute(self, command: str) -> ToolResult:
        cmd_lower = command.strip().lower()
        if not any(cmd_lower.startswith(p) for p in self.ALLOWED_PREFIXES):
            return ToolResult(success=False, error=f"Command '{command}' not in safe list.")
        try:
            process = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            success = process.returncode == 0
            return ToolResult(success=success, output=stdout.decode() if success else stderr.decode())
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class AutomationPipelineBuilder(BaseTool):
    name = "automation_pipeline_builder"
    description = "Creates a simple automation workflow from a list of steps."

    async def execute(self, name: str, steps: List[str]) -> ToolResult:
        pipeline = {
            "name": name,
            "created": datetime.now().isoformat(),
            "steps": [{"order": i+1, "action": s} for i, s in enumerate(steps)],
            "status": "ready"
        }
        path = os.path.expanduser(f"~/.shinobu_pipeline_{name.lower().replace(' ', '_')}.json")
        with open(path, "w") as f:
            json.dump(pipeline, f, indent=2)
        return ToolResult(success=True, output=f"🔗 Pipeline '{name}' created with {len(steps)} steps → {path}")
