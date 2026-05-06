from typing import Optional, List, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile

# Maps intent categories to default tool choices
TOOL_ROUTING_MAP = {
    "file_operation":   ["file_reader", "file_writer", "file_editor", "file_deleter", "file_search_engine"],
    "web_search":       ["web_search_tool", "deep_search_tool"],
    "media":            ["media_preparer", "browser_controller"],
    "productivity":     ["task_manager", "reminder_system", "document_generator", "spreadsheet_manager"],
    "system_control":   ["system_command_bridge", "process_launcher", "automation_pipeline_builder"],
    "communication":    ["chat_context_manager", "response_formatter"],
    "general":          ["system_command_bridge"],
}


class ActionPlanner:
    """
    Brain 3: Maps decomposed tasks to specific tools and sets execution order.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    def get_candidate_tools(self, intent: str) -> List[str]:
        return TOOL_ROUTING_MAP.get(intent, TOOL_ROUTING_MAP["general"])

    async def plan_actions(self, subtasks: List[Dict], intent: str) -> List[Dict[str, Any]]:
        import json, re
        candidates = self.get_candidate_tools(intent)
        prompt = (
            f"You are {self.profile.identity.name if self.profile else 'Shinobu'}, mapping subtasks to OS tools.\n"
            f"Available tools for this intent: {candidates}\n"
            f"For each subtask, assign the best tool and provide 'args' as a dict.\n"
            f"Return a JSON array with: 'subtask_id', 'tool', 'args', 'execution_order'.\n\n"
            f"Subtasks: {json.dumps(subtasks)}\n\nReturn JSON only."
        )
        raw = await self.llm.generate(prompt, session_id=None, max_tokens=400)
        try:
            start = raw.find('[')
            end = raw.rfind(']') + 1
            return json.loads(raw[start:end])
        except Exception:
            return [{"subtask_id": t.get("id", i+1), "tool": candidates[0], "args": {}, "execution_order": i+1}
                    for i, t in enumerate(subtasks)]
