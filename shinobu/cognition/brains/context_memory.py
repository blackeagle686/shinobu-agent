from typing import Any, Dict, List, Optional
from datetime import datetime


class ContextMemory:
    """
    Brain 5: Maintains conversational and session context.
    Tracks open files, ongoing tasks, and session continuity.
    Deterministic / Hybrid — NO LLM required.
    """

    def __init__(self):
        self._session: Dict[str, Any] = {}
        self._open_files: List[str] = []
        self._ongoing_tasks: List[Dict] = []
        self._interaction_log: List[Dict] = []

    # --- Session ---
    def set(self, key: str, value: Any):
        self._session[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._session.get(key, default)

    # --- File tracking ---
    def open_file(self, path: str):
        if path not in self._open_files:
            self._open_files.append(path)

    def close_file(self, path: str):
        self._open_files = [f for f in self._open_files if f != path]

    def get_open_files(self) -> List[str]:
        return list(self._open_files)

    # --- Task tracking ---
    def add_task(self, task: Dict):
        self._ongoing_tasks.append({**task, "added_at": datetime.now().isoformat()})

    def complete_task(self, task_id: Any):
        for t in self._ongoing_tasks:
            if t.get("id") == task_id:
                t["status"] = "done"

    def get_pending_tasks(self) -> List[Dict]:
        return [t for t in self._ongoing_tasks if t.get("status") != "done"]

    # --- Interaction log ---
    def log_interaction(self, role: str, content: str):
        self._interaction_log.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_recent_log(self, n: int = 10) -> List[Dict]:
        return self._interaction_log[-n:]

    def snapshot(self) -> Dict:
        return {
            "session": self._session,
            "open_files": self._open_files,
            "ongoing_tasks": self._ongoing_tasks,
            "interaction_log_count": len(self._interaction_log),
        }
