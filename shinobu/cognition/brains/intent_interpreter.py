import json
import re
from typing import Optional, Dict, Any
from phoenix.framework.agent.core.profile import AgentProfile


class IntentInterpreter:
    """
    Brain 1: Understands user requests in natural language.
    Classifies intent strictly into: 'communication', 'search', or 'action'.
    Extracts entities and detects if multi-task.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def interpret(self, user_input: str) -> Dict[str, Any]:
        quick = self._rule_based_intent(user_input)
        if quick:
            return quick

        name = self.profile.identity.name if self.profile else "Shinobu Kocho"
        role = self.profile.role.title if self.profile else "User Personal OS Assistant"
        
        prompt = (
            f"You are {name}, the {role}. You are a general assistant like Alexa, but with local OS capabilities.\n"
            f"Analyze the following user request and return a structured JSON.\n"
            f"Rules:\n"
            f"- 'intent': MUST be one of ['communication', 'search', 'action'].\n"
            f"   - 'communication' = general chatting, answering fast questions, greetings.\n"
            f"   - 'search' = searching the web for information.\n"
            f"   - 'action' = reading local files, summarizing files, creating files (PDF, Word, Excel, text), system commands.\n"
            f"- 'entities': extract any mentioned file names, locations, apps, topics, or URLs.\n"
            f"- 'multi_task': true if multiple distinct tasks are detected.\n"
            f"- 'subtasks': brief list of subtask descriptions if multi_task is true, else empty.\n\n"
            f"User: {user_input}\n\nReturn JSON only."
        )
        
        raw = await self.llm.generate(prompt, session_id=None, max_tokens=220)
        
        try:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(m.group(0)) if m else {}
            intent = data.get("intent", "communication")
            if intent not in ("communication", "search", "action"):
                intent = "communication"
            return {
                "intent": intent,
                "entities": data.get("entities", []),
                "multi_task": bool(data.get("multi_task", False)),
                "subtasks": data.get("subtasks", [])
            }
        except Exception:
            return self._rule_based_intent(user_input) or {"intent": "communication", "entities": [], "multi_task": False, "subtasks": []}

    def _rule_based_intent(self, user_input: str) -> Dict[str, Any]:
        text = user_input.lower().strip()
        entities = re.findall(r"(~\/[^\s]+|\/[^\s]+|https?://[^\s]+|[a-zA-Z0-9_\-]+\.(?:txt|md|json|csv|py|js|ts|pdf|docx|xlsx))", user_input)
        action_kw = ("create", "write", "edit", "open", "delete", "run", "execute", "save", "file", "folder", "pdf", "document")
        search_kw = ("search", "look up", "find info", "web", "google", "duckduckgo")
        is_search = any(k in text for k in search_kw)
        is_action = any(k in text for k in action_kw) or bool(entities)
        if is_search and is_action:
            return {"intent": "action", "entities": entities, "multi_task": True, "subtasks": ["search information", "apply result to requested action"]}
        if is_action:
            return {"intent": "action", "entities": entities, "multi_task": (" and " in text), "subtasks": []}
        if is_search:
            return {"intent": "search", "entities": entities, "multi_task": False, "subtasks": []}
        return None
