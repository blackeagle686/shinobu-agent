from phoenix.framework.agent.core.loop import AgentLoop
import asyncio

from .helpers.tasks import _load_tasks, _mark_task
from .helpers.plan import _get_pending_plan_steps, _mark_plan_step
from .helpers.observability import clear_logs
from .brains.generator import ShinobuGenerator
from .core.utils import (
    get_pending_tasks, get_executable_tasks, has_task_file,
    cleanup_state_files, is_all_done,
    init_phase, ensure_plan_steps, execute_step,
    fast_answer, fast_answer_stream, finalize_task,
    validate_and_execute, stream_task_steps, StepResult,
)


class ShinobuLoop(AgentLoop):
    """
    Task-file driven agent loop with user-operations specialization:
      IntentInterpreter → TaskDecomposer → ActionPlanner → SystemBridge (→ tools) → UXGenerator.
    """

    MAX_RETRIES = 2
    MAX_ACTIONS = 30

    def __init__(self, thinker, planner, actor, reflector, analyzer,
                 intent_interpreter=None, task_decomposer=None,
                 action_planner=None, system_bridge=None,
                 context_memory=None, safety_decision=None,
                 ux_generator=None, generator=None,
                 search_classifier=None, browser_service=None):
        super().__init__(thinker, planner, actor, reflector, analyzer)
        self.intent_interpreter = intent_interpreter
        self.task_decomposer = task_decomposer
        self.action_planner = action_planner
        self.system_bridge = system_bridge
        self.context_memory = context_memory
        self.safety_decision = safety_decision
        self.ux_generator = ux_generator
        self.generator = generator or ShinobuGenerator(self.planner.llm)
        self.search_classifier = search_classifier
        self.browser_service = browser_service

    @property
    def _ctx(self):
        """Bundle components into a dict for utility functions."""
        return dict(
            thinker=self.thinker, planner=self.planner, generator=self.generator,
            reflector=self.reflector, actor=self.actor, analyzer=self.analyzer,
            intent_interpreter=self.intent_interpreter,
            task_decomposer=self.task_decomposer,
            action_planner=self.action_planner,
            system_bridge=self.system_bridge,
            context_memory=self.context_memory,
            safety_decision=self.safety_decision,
            ux_generator=self.ux_generator,
            search_classifier=self.search_classifier,
            browser_service=self.browser_service,
            llm=self.planner.llm, bg=self._background_tasks, retries=self.MAX_RETRIES,
            profile=self.ux_generator.profile if self.ux_generator else None,
        )

    # ------------------------------------------------------------------
    # Non-streaming
    # ------------------------------------------------------------------

    async def run(self, prompt: str, memory, session_id: str, mode: str = "auto", **kw) -> str:
        clear_logs()
        ctx = self._ctx
        is_resume = prompt.strip().lower() == "resume" or mode == "resume"

        if mode == "fast_ans" and not is_resume:
            return await fast_answer(ctx, prompt, memory, session_id)

        obj = await init_phase(ctx, prompt, memory, session_id, is_resume)
        intent_data = memory.session.get("intent_data", {})
        
        # Load last result if resuming
        if is_resume:
            from .helpers.backbone import get_last_result
            prev_result = get_last_result()
        else:
            prev_result = ""
            
        if not is_resume and intent_data.get("intent") == "communication":
            return await fast_answer(ctx, prompt, memory, session_id)

        await memory.add_interaction(session_id, "system", f"Task breakdown: {obj}")

        results, summaries, total = "", [], 0

        while has_task_file() and total < self.MAX_ACTIONS:
            pending = get_pending_tasks()
            if not pending:
                break
            task, tid = pending[0], pending[0].get("id")

            steps = await ensure_plan_steps(ctx, task, tid)
            if not steps:
                _mark_task(tid, "done")
                continue

            failed = False
            for step in steps:
                sid = step.get("plan_step_id")
                ok, txt, cnt, step_output = await execute_step(ctx, step, task, memory, session_id, prev_result=prev_result)
                total += cnt
                results += txt
                if ok:
                    _mark_plan_step(sid, "done")
                    if step_output:
                        prev_result = step_output
                else:
                    _mark_plan_step(sid, "failed")
                    failed = True
                    break

            finalize_task(tid, task, failed, summaries, result_output=prev_result)
            
            # If the tool asked a question, we MUST stop the loop and wait for user input
            if "QUESTION_TO_USER:" in prev_result:
                break

        if is_all_done():
            cleanup_state_files()

        # Generate Final Report
        report = await ctx["ux_generator"].generate_final_report(prompt, summaries, results)
        await memory.add_interaction(session_id, "assistant", report)
        return report

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def run_stream(self, prompt: str, memory, session_id: str, mode: str = "auto", **kw):
        clear_logs()
        ctx = self._ctx
        is_resume = prompt.strip().lower() == "resume" or mode == "resume"

        if mode == "fast_ans" and not is_resume:
            async for ev in fast_answer_stream(ctx, prompt, memory, session_id):
                yield ev
            return

        yield {"type": "status", "role": "system" if is_resume else "thinker",
               "content": "🔄 Resuming..." if is_resume else "🧠 Decomposing your request..."}

        # For stream_task_steps we need intent_data.
        # But wait, we can just do intent_data = await ctx["intent_interpreter"].interpret(prompt) here if we wanted.
        # But it's done in init_phase. Let's retrieve it from memory, or just return it from init_phase!
        # Actually let's just let init_phase handle it and we retrieve intent_data from memory.
        # Wait, I didn't save intent_data to memory in init_phase! Let's do it right now in loop.py by passing intent_data manually or saving it.
        obj = await init_phase(ctx, prompt, memory, session_id, is_resume)
        intent_data = memory.session.get("intent_data", {})
        
        # Load last result if resuming
        if is_resume:
            from .helpers.backbone import get_last_result
            prev_result = get_last_result()
        else:
            prev_result = ""
            
        # Fast path chat routing if intent is communication and not resuming
        if not is_resume and intent_data.get("intent") == "communication":
            async for ev in fast_answer_stream(ctx, prompt, memory, session_id):
                yield ev
            return

        memory.session.set("current_objective", obj)
        yield {"type": "status", "role": "thinker", "content": "📋 Tasks Breakdown Complete"}
        await memory.add_interaction(session_id, "system", f"Task breakdown: {obj}")

        results, summaries, total, task_num = "", [], 0, 0

        while has_task_file() and total < self.MAX_ACTIONS:
            executable = get_executable_tasks()
            if not executable:
                if get_pending_tasks():
                    yield {"type": "chunk", "role": "system", "content": "\n⚠ Deadlock\n"}
                break

            task, tid = executable[0], executable[0].get("id")
            task_num += 1

            try:
                count = len(_load_tasks().get("tasks", []))
            except Exception:
                count = "?"

            yield {"type": "status", "role": "planner",
                   "content": f"⚙ Task {task_num}/{count}: {task.get('title')}"}
            yield {"type": "chunk", "role": "planner",
                   "content": f"\n**[P{task.get('priority')}] {task.get('title')}**\n"}

            # Delegate step processing to async generator
            sr = StepResult()
            # Pass prev_result to stream_task_steps
            async for ev in stream_task_steps(ctx, task, tid, memory, session_id, sr, intent_data=intent_data, prev_result=prev_result):
                yield ev

            total += sr.action_count
            results += sr.text
            if sr.step_output:
                prev_result = sr.step_output
            finalize_task(tid, task, sr.failed, summaries, result_output=prev_result)

            # If the tool asked a question, we MUST stop the loop and wait for user input
            if "QUESTION_TO_USER:" in prev_result:
                icon, msg = ("?", "Waiting for user input...")
                yield {"type": "chunk", "role": "reflector", "content": f"  ↳ {icon} {msg}\n"}
                break

            icon, msg = ("✗", "Task failed.") if sr.failed else ("✓", "Task complete.")
            yield {"type": "chunk", "role": "reflector", "content": f"  ↳ {icon} {msg}\n"}

        if is_all_done():
            yield {"type": "status", "content": "🗑 Cleaning up..."}
            cleanup_state_files()

        # Final Report Phase
        yield {"type": "status", "role": "thinker", "content": "📊 Generating final report..."}
        report = await ctx["ux_generator"].generate_final_report(prompt, summaries, results)
        yield {"type": "chunk", "role": "reflector", "content": f"\n\n{report}\n"}
        await memory.add_interaction(session_id, "assistant", report)
