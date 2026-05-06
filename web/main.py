import os
import sys
import json
import asyncio
import time
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
    return templates.TemplateResponse(request=request, name="landing.html")

@app.get("/chat", response_class=HTMLResponse)
async def get_chat(request: Request):
    return templates.TemplateResponse(request=request, name="chat.html")

@app.get("/results", response_class=HTMLResponse)
async def get_results(request: Request):
    ctx = _load_backbone()
    return templates.TemplateResponse(request=request, name="results.html", context={"context": ctx})

@app.get("/search", response_class=HTMLResponse)
async def get_search(request: Request):
    return templates.TemplateResponse(request=request, name="search.html")

@app.get("/analysis", response_class=HTMLResponse)
async def get_analysis(request: Request):
    ctx = _load_backbone()
    return templates.TemplateResponse(request=request, name="analysis.html", context={"context": ctx})

# ─────────────────── API ───────────────────

class ChatRequest(BaseModel):
    prompt: str
    session_id: str
    mode: str = "agent_loop"

class SearchRequest(BaseModel):
    query: str
    level: str = "auto"       # auto | fast | mid | deep
    extended: bool = False     # use 5 pages instead of 3 for deep

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    # --- Auto Mode Logic ---
    effective_mode = req.mode
    if req.mode == "auto":
        # Ask the agent's intent interpreter to decide
        try:
            intent_obj = await SHINOBU_AGENT.intent_interpreter.interpret(req.prompt)
            intent = intent_obj.get("intent", "general")
            
            if intent == "web_search":
                effective_mode = "search"
            elif intent == "identity" or (intent == "general" and not intent_obj.get("multi_task")):
                effective_mode = "fast_ans"
            else:
                effective_mode = "agent_loop"
        except Exception:
            effective_mode = "fast_ans"

    # --- Mode Mapping ---
    # Convert UI names to Agent Loop modes
    if effective_mode == "chat": effective_mode = "fast_ans"
    if effective_mode == "agent": effective_mode = "agent_loop"

    async def event_generator():
        try:
            # Handle explicit search mode (fast mid-search)
            if effective_mode == "search":
                yield f"data: {json.dumps({'type': 'status', 'content': '🔍 Performing fast search...'})}\n\n"
                browser = SHINOBU_AGENT.browser_service
                res = await browser.mid_search(req.prompt)
                if res.get("success"):
                    ans = f"### 🔍 Search Results for: *{req.prompt}*\n\n"
                    for r in res['results'][:5]:
                        ans += f"#### [{r['title']}]({r['url']})\n"
                        if r.get('snippet'):
                            ans += f"> {r['snippet']}\n\n"
                    ans += "---\n**Search Complete.** Click below to explore deeper in the Search Hub."
                    yield f"data: {json.dumps({'type': 'chunk', 'content': ans})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': 'Search failed.'})}\n\n"
                return

            async for event in SHINOBU_AGENT.run_stream(req.prompt, session_id=req.session_id, mode=effective_mode):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'chunk', 'content': f'Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/search")
async def search_endpoint(req: SearchRequest):
    """Direct search API — returns structured search results as JSON."""
    from Shinobu.shinobu.services.webbrowser import WebBrowserService
    browser = SHINOBU_AGENT.browser_service if SHINOBU_AGENT else WebBrowserService()
    classifier = SHINOBU_AGENT.search_classifier if SHINOBU_AGENT else None

    start = time.time()

    # Classify level
    if req.level == "auto" and classifier:
        classification = await classifier.classify(req.query)
        level = classification.get("level", "mid")
        reason = classification.get("reason", "")
    else:
        level = req.level if req.level in ("fast", "mid", "deep") else "mid"
        reason = f"Manually set to {level}"

    # Execute search
    llm_answer = None
    if level == "fast":
        result = await browser.fast_search(req.query)
    elif level == "mid":
        result = await browser.mid_search(req.query)
    else:
        # Deep Search: Scrape top 3 pages
        result = await browser.deep_search(req.query, extended=req.extended)
        
        # Generate LLM Summary if search was successful
        if result.get("success") and result.get("pages") and SHINOBU_AGENT:
            from Shinobu.shinobu.cognition.core.prompts import build_deep_search_summary_prompt
            pages = result.get("pages", [])
            scraped_count = result.get("pages_scraped", 0)
            
            prompt = build_deep_search_summary_prompt(req.query, pages, scraped_count)
            llm_answer = await SHINOBU_AGENT.thinker.llm.generate(prompt, session_id=None, max_tokens=1500)

    elapsed = round(time.time() - start, 2)

    return {
        "level": level,
        "reason": reason,
        "elapsed_seconds": elapsed,
        "query": req.query,
        "llm_answer": llm_answer,
        **result,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
