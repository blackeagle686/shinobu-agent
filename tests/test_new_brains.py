import asyncio
import sys
import os

# Add the Shinobu directory to sys.path so we can import it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shinobu.agent import get_shinobu_agent
from phoenix.memory.hybrid import HybridMemory

async def test_agent():
    print("Initializing agent...")
    agent = await get_shinobu_agent()
    print("Agent initialized.")
    
    memory = HybridMemory()
    session_id = "test_session"
    
    # User's request
    prompt = "Create a summary of the project architecture and save it as a text file in my Downloads/shinobu directory."
    print(f"\nUser Prompt: {prompt}")
    print("-" * 40)
    
    # Run the loop
    try:
        # We can use run() for non-streaming execution
        result = await agent.loop.run(prompt, memory, session_id, mode="auto")
        print("\n=== EXECUTION RESULT ===")
        print(result)
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    # Ensure OPENAI_API_KEY is available or it might fail if not properly loaded
    from dotenv import load_dotenv
    # Try loading from the global .shinobu env just in case
    global_env = os.path.expanduser("~/.shinobu/.env")
    if os.path.exists(global_env):
        load_dotenv(global_env, override=True)
    else:
        load_dotenv(override=True)
    asyncio.run(test_agent())
