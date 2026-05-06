from typing import Optional, Any, Dict
from phoenix.framework.agent.core.profile import AgentProfile


class UXGenerator:
    """
    Brain 7: Formats agent responses for human readability.
    Provides clear, friendly, step-by-step output in Shinobu's voice.
    LLM: YES
    """
    def __init__(self, llm, profile: Optional[AgentProfile] = None):
        self.llm = llm
        self.profile = profile

    async def format_response(self, result: Any, original_request: str, action_taken: str) -> str:
        name = self.profile.identity.name if self.profile else "Shinobu"
        tone = self.profile.personality.communication_tone if self.profile else "friendly"
        prompt = (
            f"You are {name}, a {tone} personal OS assistant.\n"
            f"The user asked: '{original_request}'\n"
            f"Action taken: {action_taken}\n"
            f"Result: {result}\n\n"
            f"Write a clear, human-friendly summary of what was done and what the user should know next. "
            f"Be concise. Use bullet points if multiple steps were taken."
        )
        return await self.llm.generate(prompt, session_id=None, max_tokens=200)

    def format_confirmation_request(self, tool: str, args: Dict, reason: str) -> str:
        """Formats a user-facing confirmation prompt for destructive actions."""
        return (
            f"⚠️ **Confirmation Required**\n"
            f"I'm about to use **{tool}** with the following settings:\n"
            f"`{args}`\n\n"
            f"**Reason**: {reason}\n\n"
            f"Please confirm: type **yes** to proceed or **no** to cancel."
        )

    def format_safety_block(self, reason: str) -> str:
        """Formats a friendly message when an action is blocked by SafetyDecision."""
        return (
            f"🚫 **Action Blocked**\n"
            f"I couldn't complete that request for safety reasons:\n"
            f"_{reason}_\n\n"
            f"If you believe this is an error, please clarify what you'd like me to do."
        )

    async def generate_final_report(self, original_request: str, summaries: list, results_text: str) -> str:
        """Generates a comprehensive final report after task completion."""
        name = self.profile.identity.name if self.profile else "Shinobu"
        tone = self.profile.personality.communication_tone if self.profile else "professional and efficient"
        
        summary_str = "\n".join(summaries)
        
        prompt = (
            f"You are {name}, a {tone} personal OS assistant.\n"
            f"User Objective: {original_request}\n\n"
            f"Execution Logs:\n{results_text}\n\n"
            f"Task Status:\n{summary_str}\n\n"
            f"Provide a concise, high-level summary report for the user. "
            f"Mention what was achieved, any files created (with paths), and if anything failed. "
            f"Use a clear, structured format (e.g., Markdown headers or bullet points). "
            f"Keep it professional and helpful."
        )
        return await self.llm.generate(prompt, session_id=None, max_tokens=500)
