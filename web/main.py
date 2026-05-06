import os
import sys
import json
import asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure we can import from Shinobu package
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load credentials
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Giyu", ".env"))
load_dotenv(env_path)

from Shinobu.shinobu.agent import get_shinobu_agent

app = FastAPI(title="Shinobu Web UI")

# Mounting static files and templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Global agent instance
SHINOBU_AGENT = None

@app.on_event("startup")
async def startup_event():
    global SHINOBU_AGENT
    print("🧠 Initializing Shinobu Agent...")
    SHINOBU_AGENT = await get_shinobu_agent()
    # Pre-init LLM if needed
    if hasattr(SHINOBU_AGENT.thinker.llm, "init"):
        try:
            await SHINOBU_AGENT.thinker.llm.init()
        except:
            pass
    print("✅ Shinobu Agent Ready.")

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

class ChatRequest(BaseModel):
    prompt: str
    session_id: str

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    async def event_generator():
        try:
            async for event in SHINOBU_AGENT.run_stream(req.prompt, session_id=req.session_id):
                # Convert event to SSE format
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'chunk', 'content': f'Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
