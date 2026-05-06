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
from Shinobu.shinobu.cognition.helpers.backbone import _load_backbone

app = FastAPI(title="Shinobu Web Suite")

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
    if hasattr(SHINOBU_AGENT.thinker.llm, "init"):
        try: await SHINOBU_AGENT.thinker.llm.init()
        except: pass
    print("✅ Shinobu Agent Ready.")

# ─────────────────── ROUTES ───────────────────

@app.get("/", response_class=HTMLResponse)
async def get_landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.get("/results", response_class=HTMLResponse)
async def get_results(request: Request):
    ctx = _load_backbone()
    return templates.TemplateResponse("results.html", {"request": request, "context": ctx})

@app.get("/analysis", response_class=HTMLResponse)
async def get_analysis(request: Request):
    ctx = _load_backbone()
    return templates.TemplateResponse("analysis.html", {"request": request, "context": ctx})

# ─────────────────── API ───────────────────

class ChatRequest(BaseModel):
    prompt: str
    session_id: str

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    async def event_generator():
        try:
            async for event in SHINOBU_AGENT.run_stream(req.prompt, session_id=req.session_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'chunk', 'content': f'Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
