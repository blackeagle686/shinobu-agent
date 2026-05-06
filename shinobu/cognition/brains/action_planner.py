import json
import re
from typing import Optional, List, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile


# Exact tool signatures — the LLM MUST use these arg names
TOOL_SIGNATURES = {
    "file_reader":         {"required": ["path"], "optional": []},
    "file_writer":         {"required": ["path", "content"], "optional": []},
    "file_editor":         {"required": ["path", "old_text", "new_text"], "optional": []},
    "file_deleter":        {"required": ["path"], "optional": ["confirmed"]},
    "file_search_engine":  {"required": [], "optional": ["directory", "pattern"]},
    "document_generator":  {"required": ["path", "title", "sections"], "optional": []},
    "spreadsheet_manager": {"required": ["path"], "optional": ["data", "sheet_name"]},
    "system_command_bridge": {"required": ["command"], "optional": []},
    "web_search_tool":     {"required": ["query"], "optional": []},
    "deep_search_tool":    {"required": ["topic"], "optional": ["extended"]},
    "browser_controller":  {"required": ["url"], "optional": ["action"]},
    "task_manager":        {"required": ["action"], "optional": ["title", "task_id"]},
    "reminder_system":     {"required": ["action", "message"], "optional": ["remind_at"]},
    # Pseudo-tool: uses the LLM to generate text content
    "llm_generate":        {"required": ["instruction"], "optional": ["context"]},
    "ask_user":            {"required": ["question"], "optional": []},
    "system_checker":      {"required": [], "optional": ["action"]},
    "pdf_viewer":          {"required": ["path"], "optional": []},
}


class ActionPlanner:
    """
    Brain 3: Maps decomposed tasks to specific tools with correct argument signatures.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def plan_actions(self, subtasks: List[Dict], intent_data: dict = None) -> List[Dict[str, Any]]:
        available_tools = list(TOOL_SIGNATURES.keys())

        # Build a concise signature reference for the LLM
        sig_lines = []
        for tool, sig in TOOL_SIGNATURES.items():
            req = ", ".join(sig["required"]) if sig["required"] else "(none)"
            opt = ", ".join(sig["optional"]) if sig["optional"] else "(none)"
            sig_lines.append(f"  - {tool}(required: [{req}], optional: [{opt}])")
        sig_block = "\n".join(sig_lines)

        prompt = (
            f"You are the Action Planner for Shinobu, an OS-level personal assistant.\n"
            f"Map each subtask to EXACTLY ONE tool from the list below.\n\n"
            f"TOOL SIGNATURES (use ONLY these exact argument names):\n{sig_block}\n\n"
            f"RULES:\n"
            f"- For 'summarize', 'write', 'compose', or any content-generation task, use 'llm_generate' tool.\n"
            f"  The 'instruction' arg should describe what to write. Example: {{\"tool\": \"llm_generate\", \"args\": {{\"instruction\": \"Write a summary of the project architecture\"}}}}\n"
            f"- For reading existing files, use 'file_reader' with 'path'.\n"
            f"- For saving/creating files, use 'file_writer' with 'path' and 'content'.\n"
            f"- For asking the user for confirmation or path, use 'ask_user' with 'question'.\n"
            f"- For checking office apps or defaults, use 'system_checker'.\n"
            f"- For opening PDFs in the system viewer, use 'pdf_viewer'.\n"
            f"  If the content depends on a previous step, set content to \"{{PREV_RESULT}}\" as a placeholder.\n"
            f"- For searching files, use 'file_search_engine' with 'directory' and 'pattern'.\n"
            f"- Default file creation directory: '~/Downloads/shinobu/'.\n"
            f"- Set 'depends_on' to the subtask_id this step needs output from (0 if independent).\n"
            f"  Crucially, if a subtask has dependencies, set 'depends_on' to the ID of the subtask it depends on.\n\n"
            f"Return a JSON array: [{{{{'subtask_id': int, 'tool': str, 'args': dict, 'execution_order': int, 'depends_on': int}}}}]\n\n"
            f"Subtasks: {json.dumps(subtasks)}\n\nReturn JSON array only."
        )

        raw = await self.llm.generate(prompt, session_id=None, max_tokens=500)

        try:
            start = raw.find('[')
            end = raw.rfind(']') + 1
            if start != -1 and end > 0:
                actions = json.loads(raw[start:end])
                # Post-process: normalize args to match tool signatures
                for action in actions:
                    action["args"] = self._normalize_args(action.get("tool", ""), action.get("args", {}))
                return actions
            else:
                raise ValueError("No JSON array found")
        except Exception:
            return [{"subtask_id": t.get("id", i+1), "tool": "llm_generate",
                     "args": {"instruction": t.get("description", t.get("title", ""))},
                     "execution_order": i+1, "depends_on": 0}
                    for i, t in enumerate(subtasks)]

    def _normalize_args(self, tool: str, args: dict) -> dict:
        """Fix common LLM arg-name mistakes based on known signatures."""
        if tool not in TOOL_SIGNATURES:
            return args

        normalized = dict(args)

        # Common renames
        renames = {
            "file_path": "path", "filepath": "path", "filename": "path", "file": "path",
            "file_name": "path", "output_path": "path", "input_path": "path",
            "search_query": "query", "text": "content", "body": "content",
            "cmd": "command", "shell_command": "command",
            "dir": "directory", "folder": "directory", "search_dir": "directory",
            "glob": "pattern", "file_pattern": "pattern", "name_pattern": "pattern",
        }
        for wrong, right in renames.items():
            if wrong in normalized and right not in normalized:
                normalized[right] = normalized.pop(wrong)

        # Tool-specific compatibility fixes
        if tool == "deep_search_tool":
            if "query" in normalized and "topic" not in normalized:
                normalized["topic"] = normalized.pop("query")

        # Remove args the tool doesn't accept
        sig = TOOL_SIGNATURES[tool]
        valid_keys = set(sig["required"] + sig["optional"])
        normalized = {k: v for k, v in normalized.items() if k in valid_keys}

        return normalized
