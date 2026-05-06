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
    description = (
        "Performs a real web search using Shinobu's 3-level search system. "
        "Automatically classifies the query into fast (open browser), "
        "mid (headless search), or deep (scrape + analyze) mode."
    )

    def __init__(self, browser_service=None, search_classifier=None, llm=None):
        self._browser = browser_service
        self._classifier = search_classifier
        self._llm = llm

    async def execute(self, query: str, level: str = "auto") -> ToolResult:
        try:
            from shinobu.services.webbrowser import WebBrowserService
            browser = self._browser or WebBrowserService()

            # ── Determine search level ──
            if level == "auto" and self._classifier:
                classification = await self._classifier.classify(query)
                chosen_level = classification.get("level", "mid")
                reason = classification.get("reason", "")
            elif level in ("fast", "mid", "deep"):
                chosen_level = level
                reason = f"Manually set to {level}"
            else:
                chosen_level = "mid"
                reason = "Default fallback"

            # ── Execute based on level ──
            if chosen_level == "fast":
                result = await browser.fast_search(query)
                output = f"🟢 Fast Search | {reason}\n"
                if result.get("success"):
                    url = result.get("url") or result.get("search_url", "")
                    output += f"🌐 Opened: {url}"
                else:
                    output += f"❌ Failed: {result.get('error', 'Unknown error')}"
                return ToolResult(success=result.get("success", False), output=output)

            elif chosen_level == "mid":
                result = await browser.mid_search(query)
                output = f"🟡 Mid Search | {reason}\n"
                if result.get("success"):
                    results = result.get("results", [])
                    output += f"🔍 Found {len(results)} results (engine: {result.get('engine', '?')})\n\n"
                    for r in results[:5]:
                        output += f"  {r.get('index', '?')}. {r.get('title', 'Untitled')}\n"
                        output += f"     {r.get('display_url') or r.get('url', '')}\n"
                        if r.get("snippet"):
                            output += f"     {r['snippet'][:120]}\n"
                        output += "\n"
                else:
                    output += f"❌ Failed: {result.get('error', 'Unknown error')}"
                return ToolResult(success=result.get("success", False), output=output)

            else:  # deep
                result = await browser.deep_search(query)
                output = f"🔵 Deep Search | {reason}\n"
                if result.get("success"):
                    pages = result.get("pages", [])
                    scraped = result.get("pages_scraped", 0)
                    output += f"📚 Scraped {scraped}/{len(pages)} pages"
                    if result.get("from_cache"):
                        output += " (cached)"
                    output += "\n\n"

                    # Summarize with LLM if available
                    if self._llm and pages:
                        from shinobu.cognition.core.prompts import build_deep_search_summary_prompt
                        prompt = build_deep_search_summary_prompt(query, pages, scraped)
                        summary = await self._llm.generate(prompt, session_id=None, max_tokens=1500)
                        output += summary
                    else:
                        # Fallback: structured text output
                        for p in pages:
                            if p.get("scrape_success"):
                                output += f"📄 {p.get('title', 'Untitled')}\n"
                                output += f"   {p.get('url', '')}\n"
                                content = p.get("content", p.get("snippet", ""))
                                if content:
                                    output += f"   {content[:300]}...\n"
                                output += "\n"
                else:
                    output += f"❌ Failed: {result.get('error', 'Unknown error')}"
                return ToolResult(success=result.get("success", False), output=output)

        except Exception as e:
            return ToolResult(success=False, error=f"Search error: {e}")


class DeepSearchTool(BaseTool):
    name = "deep_search_tool"
    description = (
        "Performs deep web research: searches, scrapes top results, "
        "extracts structured content, and summarizes with LLM analysis. "
        "Use for research, explanations, comparisons, and detailed understanding."
    )

    def __init__(self, browser_service=None, llm=None):
        self._browser = browser_service
        self._llm = llm

    async def execute(self, topic: str, extended: bool = False) -> ToolResult:
        try:
            from shinobu.services.webbrowser import WebBrowserService
            browser = self._browser or WebBrowserService()

            result = await browser.deep_search(topic, extended=extended)
            if not result.get("success"):
                return ToolResult(success=False, error=result.get("error", "Deep search failed"))

            pages = result.get("pages", [])
            scraped = result.get("pages_scraped", 0)
            output = f"📚 Deep Research: \"{topic}\"\n"
            output += f"   Pages scraped: {scraped}/{len(pages)}"
            if result.get("from_cache"):
                output += " (from cache)"
            output += "\n\n"

            # LLM summarization
            if self._llm and pages:
                from shinobu.cognition.core.prompts import build_deep_search_summary_prompt
                prompt = build_deep_search_summary_prompt(topic, pages, scraped)
                summary = await self._llm.generate(prompt, session_id=None, max_tokens=2000)
                output += summary
            else:
                for p in pages:
                    if p.get("scrape_success"):
                        output += f"── {p.get('title', 'Untitled')} ──\n"
                        output += f"URL: {p.get('url', '')}\n"
                        content = p.get("content", p.get("snippet", ""))
                        if content:
                            output += f"{content[:500]}\n"
                        output += "\n"

            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, error=f"Deep search error: {e}")


class BrowserController(BaseTool):
    name = "browser_controller"
    description = (
        "Controls browser actions: opens URLs in system browser, "
        "navigates headless to pages, or extracts page links. "
        "Supports actions: 'open', 'navigate', 'links'."
    )

    def __init__(self, browser_service=None):
        self._browser = browser_service

    async def execute(self, url: str, action: str = "open") -> ToolResult:
        try:
            from shinobu.services.webbrowser import WebBrowserService
            browser = self._browser or WebBrowserService()

            if action == "open":
                result = await browser.open_url(url)
                if result.get("success"):
                    return ToolResult(success=True, output=f"🌐 Opened browser: {url}")
                return ToolResult(success=False, error=result.get("error", "Failed to open"))

            elif action == "navigate":
                result = await browser.navigate_to(url)
                if result.get("success"):
                    output = f"📄 Navigated to: {result.get('title', url)}\n"
                    output += f"   Engine: {result.get('engine', '?')}\n"
                    output += f"   Content length: {result.get('content_length', 0)} bytes\n\n"
                    preview = result.get("text_preview", "")
                    if preview:
                        output += f"Preview:\n{preview[:500]}"
                    return ToolResult(success=True, output=output)
                return ToolResult(success=False, error=result.get("error", "Navigation failed"))

            elif action == "links":
                result = await browser.get_page_links(url)
                if result.get("success"):
                    links = result.get("links", [])
                    output = f"🔗 Found {len(links)} links on {url}\n\n"
                    for link in links:
                        output += f"  • {link.get('text', '')}\n    {link.get('url', '')}\n"
                    return ToolResult(success=True, output=output)
                return ToolResult(success=False, error=result.get("error", "Link extraction failed"))

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}. Use 'open', 'navigate', or 'links'.")

        except Exception as e:
            return ToolResult(success=False, error=f"Browser error: {e}")


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
