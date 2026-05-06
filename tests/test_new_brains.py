import asyncio
import sys
import os

# Add the Shinobu directory to sys.path so we can import it
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Imports moved inside test_agent/main to ensure .env is loaded first

async def test_agent():
    from shinobu.agent import get_shinobu_agent
    from phoenix.framework.agent.memory.hybrid import HybridMemory
    
    print("Initializing agent...")
    agent = await get_shinobu_agent()
    print("Agent initialized.")
    
    # Initialize LLM
    try:
        if not agent.loop.planner.llm.client:
            await agent.loop.planner.llm.init()
    except Exception as e:
        print(f"LLM init note: {e}")
    
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
    # Load local .env first, then Giyu as fallback
    local_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    giyu_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Giyu", ".env"))
    
    if os.path.exists(local_env):
        print(f"Loading env from local: {local_env}")
        load_dotenv(local_env, override=True)
    elif os.path.exists(giyu_env):
        print(f"Loading env from Giyu fallback: {giyu_env}")
        load_dotenv(giyu_env, override=True)
    else:
        load_dotenv(override=True)
    
    key = os.getenv("OPENAI_API_KEY")
    if key:
        print(f"OPENAI_API_KEY is set (starts with {key[:5]}...)")
    else:
        print("OPENAI_API_KEY is NOT set!")
        
    asyncio.run(test_agent())
