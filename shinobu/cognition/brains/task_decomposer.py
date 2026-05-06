import json
import re
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
        intent_ctx = f"Intent: {intent_data}" if intent_data else ""
        
        prompt = (
            f"You are {self.profile.identity.name if self.profile else 'Shinobu'}, a personal OS assistant.\n"
            f"{intent_ctx}\n"
            f"Break the following user request into an ordered list of logical subtasks.\n"
            f"Do NOT assign specific technical tools yet. Just describe the logical steps (e.g. 'Read file', 'Summarize content', 'Create PDF document').\n"
            f"RULES FOR FILES:\n"
            f"  - If creating/editing a file and the user did NOT specify an absolute path, first add a subtask: 'Ask user if they want to save in the default location (~/Downloads/shinobu/) or provide a custom path'.\n"
            f"  - If the user DID specify a path, use it directly.\n"
            f"Each subtask should have:\n"
            f"  - 'id': int\n"
            f"  - 'title': str\n"
            f"  - 'description': str\n"
            f"  - 'priority': int (1=high)\n"
            f"  - 'dependencies': list of IDs (e.g. [1] if it depends on task 1)\n\n"
            f"User: {user_input}\n\nReturn a JSON array of subtasks only."
        )
        
        raw = await self.llm.generate(prompt, session_id=None, max_tokens=350)
        
        try:
            start = raw.find('[')
            end = raw.rfind(']') + 1
            if start != -1 and end != -1:
                return json.loads(raw[start:end])
            else:
                raise ValueError("No JSON array found")
        except Exception:
            return [{"id": 1, "title": "Execute user action", "description": user_input, "priority": 1}]
