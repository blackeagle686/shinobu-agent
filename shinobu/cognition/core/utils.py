"""
Shinobu Loop Utilities — extracted helpers for the main agent loop.
Handles task querying, artifact mapping, safety, approval, and phase logic.
"""
import json
import os
import asyncio

from ..helpers.tasks import TASK_FILE, _load_tasks, _save_tasks, _mark_task, _reset_failed_tasks
from ..helpers.plan import (
    PLAN_FILE, _get_pending_plan_steps, _get_executable_plan_steps,
    _mark_plan_step, _reset_failed_plan_steps,
)
from ..helpers.generation import GENERATION_FILE
from ..helpers.state import STATE_FILE, _init_state_from_tasks, _update_state, _clear_state
from ..helpers.observability import log_agent_action
from .prompts import build_fast_answer_prompt


# ---------------------------------------------------------------------------
# Task queries
# ---------------------------------------------------------------------------

def get_pending_tasks() -> list:
    try:
        data = _load_tasks()
        return sorted(
            [t for t in data.get("tasks", []) if t.get("status") == "pending"],
            key=lambda t: t.get("priority", 99),
        )
    except Exception:
        return []


def get_executable_tasks() -> list:
    try:
        data = _load_tasks()
        all_tasks = data.get("tasks", [])
        status_map = {t.get("id"): t.get("status") for t in all_tasks}
        executable = []
        for t in all_tasks:
            if t.get("status") != "pending":
                continue
            deps_met, deps_failed = True, False
            for d in t.get("dependencies", []):
                s = status_map.get(d, "done")
                if s == "failed":
                    deps_failed = True
                elif s != "done":
                    deps_met = False
            if deps_failed:
                _mark_task(t.get("id"), "failed")
                continue
            if deps_met:
                executable.append(t)
        return sorted(executable, key=lambda t: t.get("priority", 99))
    except Exception:
        return []


def has_task_file() -> bool:
    return os.path.exists(TASK_FILE)


# ---------------------------------------------------------------------------
# Artifact → Action mapping
# ---------------------------------------------------------------------------

def _detect_vscode() -> bool:
    try:
        from shinobu.server import vscode_ipc_context
        return vscode_ipc_context.get() is not None
    except ImportError:
        return False


def map_artifacts_to_actions(generation_blocks: list) -> list:
    is_vscode = _detect_vscode()
    actions = []
    for block in generation_blocks:
        for art in block.get("artifacts", []):
            art_type = art.get("type")
            if art_type == "file_write":
                tool = "vscode_create_file" if is_vscode else "file_write"
                key = "path" if is_vscode else "file_path"
                actions.append({"tool": tool, "kwargs": {key: art.get("path", ""), "content": art.get("code", "")}})
            elif art_type == "file_update_multi":
                chunks = art.get("edits")
                if not chunks and "code" in art:
                    try:
                        chunks = json.loads(art["code"]) if isinstance(art["code"], str) else art["code"]
                    except Exception:
                        chunks = []
                if not chunks:
                    continue
                actions.append({"tool": "file_update_multi", "kwargs": {"file_path": art.get("path", ""), "edits": chunks}})
            elif art_type == "terminal":
                tool = "vscode_terminal_run" if is_vscode else "terminal"
                actions.append({"tool": tool, "kwargs": {"command": art.get("code", "")}})
    return actions


# ---------------------------------------------------------------------------
# Safety & Approval
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS = ["rm -rf /", "mkfs", "dd if="]
SENSITIVE_TOOLS = ["terminal", "vscode_terminal_run"]
SAFE_COMMANDS = ["ls", "pwd", "mkdir -p", "touch", "cat", "git status"]


def pre_execution_validate(actions: list) -> list:
    errors = []
    for act in actions:
        tool, kwargs = act.get("tool"), act.get("kwargs", {})
        path = kwargs.get("path") or kwargs.get("file_path")
        if path and (path.startswith("/") or ".." in path):
            errors.append(f"Safety Violation: Path '{path}' is absolute or contains '..'")
        if tool in SENSITIVE_TOOLS:
            cmd = kwargs.get("command", "")
            for pat in FORBIDDEN_PATTERNS:
                if pat in cmd:
                    errors.append(f"Safety Violation: Command '{cmd}' contains forbidden pattern '{pat}'")
    return errors


def is_sensitive_action(actions: list) -> bool:
    for act in actions:
        if act.get("tool") in SENSITIVE_TOOLS:
            cmd = act.get("kwargs", {}).get("command", "").strip()
            if not any(cmd.startswith(s) for s in SAFE_COMMANDS):
                return True
    return False


async def check_and_ask_approval(actions: list) -> tuple[bool, list]:
    if not is_sensitive_action(actions):
        return True, actions
    from shinobu.server import vscode_ipc_context
    ipc_call = vscode_ipc_context.get()
    if not ipc_call:
        return True, actions
    try:
        raw_res = await ipc_call("ask_approval", {"actions": actions})
        res = json.loads(raw_res)
        if res.get("decision") == "approved":
            return True, res.get("modified_actions", actions)
        return False, actions
    except Exception as e:
        print(f"[LOOP ERROR] Approval request failed: {e}")
        return False, actions


# ---------------------------------------------------------------------------
# Cleanup & Background
# ---------------------------------------------------------------------------

ALL_STATE_FILES = [TASK_FILE, PLAN_FILE, GENERATION_FILE, STATE_FILE]


def cleanup_state_files():
    for f in ALL_STATE_FILES:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass


def is_all_done() -> bool:
    try:
        data = _load_tasks()
        return all(t.get("status") == "done" for t in data.get("tasks", []))
    except Exception:
        return False


def schedule_background(bg_tasks: set, coro):
    task = asyncio.create_task(coro)
    bg_tasks.add(task)
    def _on_done(t):
        bg_tasks.discard(t)
        try: _ = t.exception()
        except Exception: pass
    task.add_done_callback(_on_done)


# ---------------------------------------------------------------------------
# Phase helpers  (ctx = dict with thinker, planner, generator, reflector,
#                 actor, analyzer, llm, bg, retries)
# ---------------------------------------------------------------------------

def finalize_task(task_id, task, failed, summaries):
    """Mark task done/failed and append to summaries."""
    status = "failed" if failed else "done"
    _mark_task(task_id, status)
    _update_state(task_id, status, task.get("title"))
    summaries.append(f"{'✗' if failed else '✓'} [{task.get('priority')}] {task.get('title')}")


async def init_phase(ctx, prompt, memory, session_id, is_resume) -> str:
    """Think phase (or resume). Returns objective metadata string."""
    if is_resume:
        log_agent_action("loop", "resume_execution", {}, {"status": "resuming"}, "success")
        _reset_failed_tasks()
        _reset_failed_plan_steps()
        return "Resuming previous task list..."

    _clear_state()
    analyze_task = asyncio.create_task(ctx["analyzer"].analyze_workspace(prompt))
    
    # 1. Interpret Intent
    intent_data = await ctx["intent_interpreter"].interpret(prompt)
    log_agent_action("intent_interpreter", "interpret", {"prompt": prompt}, intent_data, "success")
    memory.session.set("intent_data", intent_data)
    
    # 2. Decompose into tasks
    subtasks = await ctx["task_decomposer"].decompose(prompt, intent_data)
    for t in subtasks:
        if "status" not in t:
            t["status"] = "pending"
    log_agent_action("task_decomposer", "decompose", {"prompt": prompt, "intent": intent_data}, {"subtasks": subtasks}, "success")
    
    # 3. Save tasks to backbone
    task_data = {"original_prompt": prompt, "tasks": subtasks}
    _save_tasks(task_data)
    
    try:
        _init_state_from_tasks(_load_tasks().get("tasks", []))
    except Exception:
        pass
    try:
        analysis = await asyncio.wait_for(analyze_task, timeout=5.0)
        memory.session.set("project_analysis", analysis)
    except Exception:
        pass

    objective = f"Decomposed {len(subtasks)} tasks."
    memory.session.set("current_objective", objective)
    return objective


async def ensure_plan_steps(ctx, task, task_id, intent_data=None) -> list:
    steps = _get_pending_plan_steps(task_id)
    if not steps:
        # Action Planner creates tool mappings
        actions = await ctx["action_planner"].plan_actions([task], intent_data)
        
        # Convert ActionPlanner format to PlanSteps format for legacy compatibility, or just store actions.
        # But wait, action_planner outputs: [{"subtask_id": 1, "tool": "file_reader", "args": {...}}]
        # Let's wrap them into a plan step so the rest of the stream logic works.
        new_steps = []
        for a in actions:
            # Create a simple plan step that bypasses generator by specifying the exact tool
            new_steps.append({
                "plan_step_id": a.get("execution_order", 1),
                "task_id": task_id,
                "status": "pending",
                "type": a.get("tool"),
                "solution": {"approach": f"Use {a.get('tool')}"},
                "dependencies": [],
                "direct_action": a  # We add this custom field to skip generator
            })
        
        from ..helpers.plan import _save_plan, _load_plan
        existing = _load_plan()
        existing_steps = existing.get("plan_steps", [])
        
        next_step_id = max([s.get("plan_step_id", 0) for s in existing_steps], default=0) + 1
        for s in new_steps:
            s["plan_step_id"] = next_step_id
            next_step_id += 1
            existing_steps.append(s)
            
        _save_plan({"plan_steps": existing_steps})
        steps = _get_pending_plan_steps(task_id)
        log_agent_action("action_planner", "plan_actions", {"task": task}, {"plan_steps": steps}, "success")
    return steps


async def fast_answer(ctx, prompt, memory, session_id) -> str:
    context = await memory.get_full_context(session_id, query=prompt)
    profile_info = str(ctx["profile"].to_dict()) if ctx.get("profile") else ""
    ans = await ctx["llm"].generate(build_fast_answer_prompt(context, prompt, profile_info), session_id=session_id)
    await memory.add_interaction(session_id, "assistant", ans)
    return ans


async def fast_answer_stream(ctx, prompt, memory, session_id):
    yield {"type": "status", "role": "analyzer", "content": "⚡ Fast Answer mode active..."}
    context = await memory.get_full_context(session_id, query=prompt)
    profile_info = str(ctx["profile"].to_dict()) if ctx.get("profile") else ""
    async for chunk in ctx["llm"].generate_stream(build_fast_answer_prompt(context, prompt, profile_info), session_id=session_id):
        yield {"type": "chunk", "content": chunk}
    await memory.add_interaction(session_id, "assistant", "Fast answer generated.")


async def validate_and_execute(ctx, actions) -> tuple[str, list, bool]:
    """Validate, approve, execute. Returns (result_str, final_actions, was_executed)."""
    errors = pre_execution_validate(actions)
    if errors:
        log_agent_action("loop", "pre_execution_validate", {"actions": actions}, {"errors": errors}, "failed")
        return "Pre-execution validation failed: " + "; ".join(errors), actions, False
    approved, actions = await check_and_ask_approval(actions)
    if not approved:
        log_agent_action("loop", "ask_approval", {"actions": actions}, {"result": "denied"}, "failed")
        return "Execution denied by user.", actions, False
    result = await ctx["actor"].execute({"actions": actions})
    log_agent_action("actor", "execute_actions", {"actions": actions}, {"result": result}, "success")
    return result, actions, True


async def handle_syntax_error(ctx, step, task, blocks, memory, session_id, attempt=0):
    """Log, reflect on syntax error. Returns (result_text, reflection)."""
    error_msg = next((b.get("error") for b in blocks if b.get("status") == "syntax_error"), "Syntax validation failed")
    log_agent_action("generator", "generate_step", {"step": step, "task": task}, {"error": error_msg}, "failed")
    approach = step.get("solution", {}).get("approach", "")
    reflection = await ctx["reflector"].reflect(approach, {"actions": []}, f"Generation failed: {error_msg}")
    log_agent_action("reflector", "reflect", {"approach": approach}, reflection, "success")
    text = f"\nStep '{step.get('type')}' (attempt {attempt + 1}):\n  Result: Syntax Error\n  Reflection: {reflection['reflection']}\n"
    schedule_background(ctx["bg"], memory.add_interaction(
        session_id, "system", f"Step: {step.get('type')} | Result: Syntax Error | Reflection: {reflection['reflection']}"))
    return text, reflection


async def execute_step(ctx, step, task, memory, session_id, prev_result="") -> tuple[bool, str, int, str]:
    """Generate → execute → reflect for one step (non-streaming).
    Returns (ok, text, action_count, step_output).
    step_output is the raw result string for dependency chaining.
    """
    result_text, total_cnt, step_output = "", 0, ""
    for attempt in range(ctx["retries"]):
        # Bypass Generator if direct_action exists
        direct = step.get("direct_action")
        if direct:
            tool_name = direct.get("tool", "")
            args = dict(direct.get("args", {}))
            
            # Substitute {PREV_RESULT} placeholders
            for k, v in args.items():
                if isinstance(v, str) and "{PREV_RESULT}" in v:
                    args[k] = v.replace("{PREV_RESULT}", prev_result)
            
            # Handle llm_generate pseudo-tool
            if tool_name == "llm_generate":
                instruction = args.get("instruction", "")
                extra_ctx = args.get("context", prev_result or "")
                gen_prompt = f"You are Shinobu, a helpful assistant. {instruction}"
                if extra_ctx:
                    gen_prompt += f"\n\nContext:\n{extra_ctx}"
                generated = await ctx["llm"].generate(gen_prompt, session_id=session_id, max_tokens=1500)
                step_output = generated
                result_text += f"\nStep 'llm_generate' (attempt {attempt + 1}):\n  Result: Content generated ({len(generated)} chars).\n"
                return True, result_text, 0, step_output
            
            actions = [{"tool": tool_name, "kwargs": args}]
        else:
            gen = await ctx["generator"].generate_step(step, task)
            blocks = gen.get("generation_blocks", [])
            if any(b.get("status") == "syntax_error" for b in blocks):
                txt, _ = await handle_syntax_error(ctx, step, task, blocks, memory, session_id, attempt)
                result_text += txt
                continue
            log_agent_action("generator", "generate_step", {"step": step, "task": task}, gen, "success")
            actions = map_artifacts_to_actions(blocks)

        if not actions:
            return True, result_text, total_cnt, step_output
        action_result, actions, executed = await validate_and_execute(ctx, actions)
        if executed:
            total_cnt += len(actions)
            step_output = action_result
        approach = step.get("solution", {}).get("approach", "")
        reflection = await ctx["reflector"].reflect(approach, {"actions": actions}, action_result)
        log_agent_action("reflector", "reflect", {"approach": approach, "actions": actions, "result": action_result}, reflection, "success")
        result_text += f"\nStep '{step.get('type')}' (attempt {attempt + 1}):\n  Result: {action_result}\n  Reflection: {reflection['reflection']}\n"
        schedule_background(ctx["bg"], memory.add_interaction(
            session_id, "system", f"Step: {step.get('type')} | Result: {action_result} | Reflection: {reflection['reflection']}"))
        if reflection["is_complete"]:
            return True, result_text, total_cnt, step_output
    return False, result_text, total_cnt, step_output


# ---------------------------------------------------------------------------
# Streaming step execution (async generator)
# ---------------------------------------------------------------------------

class StepResult:
    """Mutable container passed into stream_task_steps."""
    __slots__ = ("failed", "text", "action_count")
    def __init__(self):
        self.failed = False
        self.text = ""
        self.action_count = 0


async def stream_task_steps(ctx, task, task_id, memory, session_id, result: StepResult, intent_data=None):
    """Async generator: process all plan steps for a task, yielding stream events."""
    steps = _get_pending_plan_steps(task_id)
    if not steps:
        yield {"type": "status", "role": "planner", "content": "  ↳ Mapping actions..."}
        steps = await ensure_plan_steps(ctx, task, task_id, intent_data)
    if not steps:
        _mark_task(task_id, "done")
        yield {"type": "chunk", "role": "planner", "content": "  ↳ No steps required.\n"}
        return

    step_attempts = {}
    while True:
        exec_steps = _get_executable_plan_steps(task_id)
        if not exec_steps:
            if _get_pending_plan_steps(task_id):
                result.failed = True
            break
        to_run = []
        for s in exec_steps:
            sid = s.get("plan_step_id")
            step_attempts[sid] = step_attempts.get(sid, 0) + 1
            if step_attempts[sid] > ctx["retries"]:
                _mark_plan_step(sid, "failed")
                result.failed = True
            else:
                to_run.append(s)
        if result.failed or not to_run:
            break

        yield {"type": "status", "role": "actor", "content": f"  ↳ Generating ({len(to_run)} steps)..."}
        
        # Bypass Generator if direct_action exists
        gen_results = []
        for s in to_run:
            if s.get("direct_action"):
                gen_results.append({"direct_action": s.get("direct_action")})
            else:
                try:
                    res = await ctx["generator"].generate_step(s, task)
                    gen_results.append(res)
                except Exception as e:
                    gen_results.append(e)

        for step, gen in zip(to_run, gen_results):
            sid = step.get("plan_step_id")
            if isinstance(gen, Exception):
                yield {"type": "chunk", "role": "system", "content": f"    ↳ ⚠ {gen}\n"}
                continue
            approach = step.get("solution", {}).get("approach", "")
            yield {"type": "chunk", "role": "planner",
                   "content": f"  ↳ Step {step.get('step_index', '?')} ({step.get('type')}): {approach[:60]}...\n"}
            
            if "direct_action" in gen:
                actions = [{"tool": gen["direct_action"].get("tool"), "kwargs": gen["direct_action"].get("args", {})}]
            else:
                blocks = gen.get("generation_blocks", [])
                if any(b.get("status") == "syntax_error" for b in blocks):
                    txt, ref = await handle_syntax_error(ctx, step, task, blocks, memory, session_id)
                    result.text += txt
                    yield {"type": "chunk", "role": "reflector", "content": f"    ↳ ⚠ Retry: {ref['reflection']}\n"}
                    continue
                log_agent_action("generator", "generate_step", {"step": step, "task": task}, gen, "success")
                actions = map_artifacts_to_actions(blocks)

            if not actions:
                _mark_plan_step(sid, "done")
                yield {"type": "chunk", "role": "actor", "content": "    ↳ Done (No actions needed)\n"}
                continue

            yield {"type": "status", "role": "actor", "content": f"  ↳ Executing {len(actions)} actions..."}
            action_result, actions, executed = await validate_and_execute(ctx, actions)
            if executed:
                result.action_count += len(actions)
            else:
                label = "⛔" if is_sensitive_action(actions) else "⚠"
                yield {"type": "chunk", "role": "system", "content": f"    ↳ {label} {action_result}\n"}

            reflection = await ctx["reflector"].reflect(approach, {"actions": actions}, action_result)
            log_agent_action("reflector", "reflect",
                             {"approach": approach, "actions": actions, "result": action_result}, reflection, "success")
            result.text += f"\nStep '{step.get('type')}':\nResult: {action_result}\nReflection: {reflection['reflection']}\n"
            schedule_background(ctx["bg"], memory.add_interaction(
                session_id, "system",
                f"Step: {step.get('type')} | Result: {action_result} | Reflection: {reflection['reflection']}"))

            if reflection["is_complete"]:
                _mark_plan_step(sid, "done")
                yield {"type": "chunk", "role": "reflector", "content": f"    ↳ ✓ {reflection['reflection']}\n"}
            else:
                yield {"type": "chunk", "role": "reflector", "content": f"    ↳ ⚠ Retry: {reflection['reflection']}\n"}
