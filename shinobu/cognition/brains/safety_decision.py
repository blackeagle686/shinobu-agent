import os
from typing import Any, Dict, List

# Directories that are protected from deletion/modification
PROTECTED_PATHS = ["/", "/home", "/etc", "/usr", "/bin", "/sbin", "/var"]

# Actions that require explicit user confirmation
DESTRUCTIVE_ACTIONS = {"file_deleter", "process_launcher", "system_command_bridge", "automation_pipeline_builder"}


class SafetyDecision:
    """
    Brain 6: Validates actions and prevents dangerous operations.
    Deterministic — NO LLM.
    """

    def check(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a safety verdict: {'safe': bool, 'reason': str, 'requires_confirmation': bool}
        """
        # Check destructive tools
        if tool in DESTRUCTIVE_ACTIONS:
            return {
                "safe": True,
                "requires_confirmation": True,
                "reason": f"Tool '{tool}' can modify system state. Requires user confirmation."
            }

        # File path safety check
        path = args.get("path", "")
        if path:
            resolved = os.path.abspath(path)
            for protected in PROTECTED_PATHS:
                if resolved == protected or resolved.startswith(protected + os.sep):
                    return {
                        "safe": False,
                        "requires_confirmation": False,
                        "reason": f"Access to protected path '{resolved}' is not allowed."
                    }

        # Permission check for file operations
        if tool in ("file_reader", "file_editor") and path:
            if not os.path.exists(path):
                return {
                    "safe": False,
                    "requires_confirmation": False,
                    "reason": f"File '{path}' does not exist."
                }

        return {"safe": True, "requires_confirmation": False, "reason": "Action is safe to proceed."}

    def is_destructive(self, tool: str) -> bool:
        return tool in DESTRUCTIVE_ACTIONS
