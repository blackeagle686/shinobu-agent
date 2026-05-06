import os
import asyncio
import subprocess
from typing import Any, Dict


# OS-level action routing table
ACTION_MAP = {
    "file_operation":   "file_reader",
    "web_search":       "web_search_tool",
    "media":            "media_preparer",
    "productivity":     "task_manager",
    "system_control":   "system_command_bridge",
}


class SystemBridge:
    """
    Brain 4: Translates AI-decided actions into OS-level operations.
    Deterministic — NO LLM.
    """

    def translate(self, action_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts a high-level action plan entry into a concrete OS operation descriptor.
        """
        tool = action_plan.get("tool", "system_command_bridge")
        args = action_plan.get("args", {})
        return {
            "resolved_tool": tool,
            "resolved_args": args,
            "execution_type": self._classify(tool),
        }

    def _classify(self, tool: str) -> str:
        if tool in ("file_reader", "file_writer", "file_editor", "file_deleter", "file_search_engine"):
            return "filesystem"
        elif tool in ("web_search_tool", "deep_search_tool", "browser_controller"):
            return "network"
        elif tool in ("process_launcher", "system_command_bridge"):
            return "process"
        elif tool in ("task_manager", "reminder_system", "spreadsheet_manager", "document_generator"):
            return "productivity"
        return "generic"

    async def execute_os_command(self, command: str) -> str:
        """Safely runs a shell command and returns stdout."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode == 0:
            return stdout.decode().strip()
        raise RuntimeError(f"Command failed: {stderr.decode().strip()}")
