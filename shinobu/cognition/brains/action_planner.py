import json
import re
from typing import Optional, List, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile


class ActionPlanner:
    """
    Brain 3: Maps decomposed tasks to specific tools.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def plan_actions(self, subtasks: List[Dict], intent_data: dict = None) -> List[Dict[str, Any]]:
        available_tools = [
            "file_reader", "file_writer", "file_editor", "file_deleter", "file_search_engine",
            "document_generator", "spreadsheet_manager", "system_command_bridge",
            "web_search_tool", "deep_search_tool", "browser_controller"
        ]

        prompt = (
            f"You are the Action Planner mapping subtasks to OS tools.\n"
            f"Available tools: {available_tools}\n\n"
            f"Rules for Tool Mapping:\n"
            f"- Use 'file_reader' to read files or summarize local files.\n"
            f"- Use 'file_writer' or 'document_generator' for simple text/markdown files.\n"
            f"- Use 'spreadsheet_manager' for CSV/Excel.\n"
            f"- Use 'system_command_bridge' if you need to run a shell command, or if you need to execute a python script to generate complex files like PDFs or DOCX.\n"
            f"   - When creating PDF/DOCX, the argument for 'system_command_bridge' should instruct the Generator to write and run a script to create the file at the required location (default '~/Downloads/shinobu/').\n"
            f"For each subtask, assign the best tool and provide 'args' as a dict.\n"
            f"Return a JSON array with: 'subtask_id', 'tool', 'args', 'execution_order'.\n\n"
            f"Subtasks: {json.dumps(subtasks)}\n\nReturn JSON array only."
        )

        raw = await self.llm.generate(prompt, session_id=None, max_tokens=600)
        
        try:
            start = raw.find('[')
            end = raw.rfind(']') + 1
            if start != -1 and end != -1:
                return json.loads(raw[start:end])
            else:
                raise ValueError("No JSON array found")
        except Exception:
            return [{"subtask_id": t.get("id", i+1), "tool": "system_command_bridge", "args": {"command": "echo 'Fallback action'"}, "execution_order": i+1}
                    for i, t in enumerate(subtasks)]
