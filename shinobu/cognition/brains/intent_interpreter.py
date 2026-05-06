from typing import Optional
from phoenix.framework.agent.core.profile import AgentProfile


class IntentInterpreter:
    """
    Brain 1: Understands user requests in natural language.
    Classifies intent, detects multi-task requests, extracts entities.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def interpret(self, user_input: str) -> dict:
        prompt = (
            f"You are {self.profile.identity.name if self.profile else 'Shinobu'}, a friendly personal OS assistant.\n"
            f"Analyze the following user request and return a structured JSON with:\n"
            f"- 'intent': primary intent (e.g. file_operation, web_search, productivity, system_control, media)\n"
            f"- 'entities': extracted entities (file names, apps, topics, URLs)\n"
            f"- 'multi_task': true if multiple tasks detected\n"
            f"- 'subtasks': list of subtask descriptions if multi_task is true\n\n"
            f"User: {user_input}\n\nReturn JSON only."
        )
        import json, re
        raw = await self.llm.generate(prompt, session_id=None, max_tokens=300)
        try:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(m.group(0)) if m else {"intent": "general", "entities": [], "multi_task": False, "subtasks": []}
        except Exception:
            return {"intent": "general", "entities": [], "multi_task": False, "subtasks": []}
