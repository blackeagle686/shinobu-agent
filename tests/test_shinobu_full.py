import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Load .env from Giyu (shared credentials)
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Giyu", ".env"))
load_dotenv(env_path)

from Shinobu.shinobu.agent import get_shinobu_agent


# ─────────────────── BRAIN TESTS ───────────────────

async def test_brains(agent):
    print("\n--- Testing Shinobu Brains ---")

    # 1. Intent Interpreter (LLM)
    print("Testing IntentInterpreter...")
    intent = await agent.intent_interpreter.interpret("Search for a Python tutorial on YouTube and write a summary to notes.txt")
    print(f"Intent: {intent}")

    # 2. Task Decomposer (LLM)
    print("Testing TaskDecomposer...")
    tasks = await agent.task_decomposer.decompose("Find and save a recipe to a file", intent)
    print(f"Tasks: {tasks}")

    # 3. Action Planner (LLM)
    print("Testing ActionPlanner...")
    actions = await agent.action_planner.plan_actions(tasks, intent.get("intent", "general"))
    print(f"Actions: {actions}")

    # 4. System Bridge (Deterministic)
    print("Testing SystemBridge (Deterministic)...")
    translated = agent.system_bridge.translate({"tool": "file_writer", "args": {"path": "~/test.txt", "content": "hi"}})
    print(f"SystemBridge: {translated}")

    # 5. Context Memory (Deterministic)
    print("Testing ContextMemory (Deterministic)...")
    agent.context_memory.open_file("~/notes.txt")
    agent.context_memory.add_task({"id": 1, "title": "Write recipe"})
    snap = agent.context_memory.snapshot()
    print(f"ContextMemory: {snap}")

    # 6. Safety Decision (Deterministic)
    print("Testing SafetyDecision (Deterministic)...")
    verdict_safe   = agent.safety_decision.check("file_reader",  {"path": "/home"})
    verdict_block  = agent.safety_decision.check("file_deleter", {"path": "/etc/passwd", "confirmed": False})
    print(f"Safe verdict: {verdict_safe}")
    print(f"Block verdict: {verdict_block}")

    # 7. UX Generator (LLM)
    print("Testing UXGenerator (LLM)...")
    response = await agent.ux_generator.format_response(
        result="File written successfully.",
        original_request="Save a recipe to file",
        action_taken="file_writer executed on ~/recipe.txt"
    )
    print(f"UX Response: {response}")


# ─────────────────── TOOL TESTS ───────────────────

async def test_tools(agent):
    print("\n--- Testing Shinobu Tools ---")

    # File tools
    print("Testing file_writer...")
    r = await agent.tools.get_tool("file_writer").execute(path="/tmp/shinobu_test.txt", content="Hello from Shinobu!")
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing file_reader...")
    r = await agent.tools.get_tool("file_reader").execute(path="/tmp/shinobu_test.txt")
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing file_search_engine...")
    r = await agent.tools.get_tool("file_search_engine").execute(directory="/tmp", pattern="shinobu*")
    print(f"Result: {r.output if r.success else r.error}")

    # Productivity tools
    print("Testing task_manager (create)...")
    r = await agent.tools.get_tool("task_manager").execute(action="create", title="Review Hashira-OS docs")
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing task_manager (list)...")
    r = await agent.tools.get_tool("task_manager").execute(action="list")
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing reminder_system (add)...")
    r = await agent.tools.get_tool("reminder_system").execute(action="add", message="Check Shinobu tests", remind_at="2026-05-07 09:00")
    print(f"Result: {r.output if r.success else r.error}")

    # System tools
    print("Testing system_command_bridge...")
    r = await agent.tools.get_tool("system_command_bridge").execute(command="echo 'Shinobu is online'")
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing document_generator...")
    r = await agent.tools.get_tool("document_generator").execute(
        path="/tmp/shinobu_doc.md",
        title="Test Report",
        sections={"Summary": "Test completed successfully.", "Next Steps": "Deploy to Hashira-OS."}
    )
    print(f"Result: {r.output if r.success else r.error}")

    print("Testing automation_pipeline_builder...")
    r = await agent.tools.get_tool("automation_pipeline_builder").execute(
        name="Morning Routine",
        steps=["Read emails", "Check system health", "Prepare daily report"]
    )
    print(f"Result: {r.output if r.success else r.error}")


# ─────────────────── FULL LOOP TEST ───────────────────

async def test_full_loop(agent):
    print("\n--- Testing Full Agent Loop ---")
    prompt = "Search for 'Hashira-OS architecture' online, create a task to review results, and save a summary to /tmp/shinobu_summary.txt"
    try:
        async for event in agent.run_stream(prompt, session_id="test_shinobu_session"):
            if event["type"] == "status":
                print(f"STATUS: {event['content']}")
            elif event["type"] == "chunk":
                print(event["content"], end="", flush=True)
    except Exception as e:
        print(f"\n[LOOP ERROR] {e}")
    print("\nLoop Complete.")


# ─────────────────── MAIN ───────────────────

async def main():
    print("--- Shinobu Test Suite ---")
    print(f"CWD: {os.getcwd()}")
    print(f"OPENAI_API_KEY: {'[SET]' if os.getenv('OPENAI_API_KEY') else '[NOT SET]'}")

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found.")
        return

    print("\nInitializing Shinobu Agent...")
    agent = await get_shinobu_agent()

    try:
        if not agent.thinker.llm.client:
            await agent.thinker.llm.init()
    except Exception as e:
        print(f"LLM init note: {e}")

    await test_brains(agent)
    await test_tools(agent)
    await test_full_loop(agent)


if __name__ == "__main__":
    asyncio.run(main())
