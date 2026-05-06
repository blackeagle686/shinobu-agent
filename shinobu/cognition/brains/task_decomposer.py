from typing import Optional, List, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile


class TaskDecomposer:
    """
    Brain 2: Breaks user requests into structured, ordered subtasks.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def decompose(self, user_input: str, intent_data: dict = None) -> List[Dict[str, Any]]:
        import json, re
        intent_ctx = f"Intent: {intent_data}" if intent_data else ""
        prompt = (
            f"You are {self.profile.identity.name if self.profile else 'Shinobu'}, a personal OS assistant.\n"
            f"{intent_ctx}\n"
            f"Break the following user request into an ordered list of atomic subtasks.\n"
            f"Each subtask should have: 'id', 'title', 'description', 'tool' (which tool to use), 'priority' (1=high).\n\n"
            f"User: {user_input}\n\nReturn a JSON array of subtasks only."
        )
        raw = await self.llm.generate(prompt, session_id=None, max_tokens=500)
        try:
            start = raw.find('[')
            end = raw.rfind(']') + 1
            return json.loads(raw[start:end])
        except Exception:
            return [{"id": 1, "title": "Execute request", "description": user_input,
                     "tool": "system_command_bridge", "priority": 1}]
