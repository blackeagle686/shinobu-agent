import os
from phoenix import Agent, init_phoenix, startup_phoenix


async def get_shinobu_agent(on_startup_progress=None):
    """
    Initializes the Phoenix framework and returns the fully configured Shinobu agent —
    the User Operations Layer of Hashira-OS.
    """
    init_phoenix()
    await startup_phoenix(on_progress=on_startup_progress)

    from .cognition.brains import (
        IntentInterpreter, TaskDecomposer, ActionPlanner, SystemBridge,
        ContextMemory, SafetyDecision, UXGenerator,
        ShinobuReflector, ShinobuGenerator, SearchLevelClassifier
    )
    from .cognition.loop import ShinobuLoop
    from .services.webbrowser import WebBrowserService
    from phoenix.framework.agent.core.profile import AgentProfile
    
    # Use generic brains for the base Agent requirements if needed, 
    # but ShinobuLoop will primarily use the specialized ones.
    from phoenix.framework.agent.cognition.thinker import Thinker as AgentThinker
    from phoenix.framework.agent.cognition.planner import Planner as AgentPlanner

    # Load profile
    profile_path = os.path.join(os.path.dirname(__file__), "profile.json")
    profile = AgentProfile.from_json(profile_path)

    # Shared service instances
    browser_service = WebBrowserService()

    agent = Agent(
        loop_cls=ShinobuLoop,
        component_factories={
            "thinker":   lambda **ctx: AgentThinker(ctx["llm"]),
            "planner":   lambda **ctx: AgentPlanner(ctx["llm"], ctx["tools"]),
            "reflector": lambda **ctx: ShinobuReflector(ctx["llm"]),
            "generator": lambda **ctx: ShinobuGenerator(ctx["llm"]),
            "loop": lambda **ctx: ShinobuLoop(
                thinker=ctx["thinker"],
                planner=ctx["planner"],
                actor=ctx["actor"],
                reflector=ctx["reflector"],
                analyzer=ctx["analyzer"],
                intent_interpreter=IntentInterpreter(ctx["llm"], profile=profile),
                task_decomposer=TaskDecomposer(ctx["llm"], profile=profile),
                action_planner=ActionPlanner(ctx["llm"], profile=profile),
                system_bridge=SystemBridge(),
                context_memory=ContextMemory(),
                safety_decision=SafetyDecision(),
                ux_generator=UXGenerator(ctx["llm"], profile=profile),
                generator=ctx.get("generator") or ShinobuGenerator(ctx["llm"]),
                search_classifier=SearchLevelClassifier(ctx["llm"], profile=profile),
                browser_service=browser_service,
            ),
        },
        profile=profile,
    )

    from .tools.user_tools import (
        FileReader, FileWriter, FileEditor, FileDeleter, FileSearchEngine,
        WebSearchTool, DeepSearchTool, BrowserController, MediaPreparer,
        TaskManagerTool, ReminderSystem, SpreadsheetManager, DocumentGenerator,
        ChatContextManager, ResponseFormatter,
        ProcessLauncher, SystemCommandBridge, AutomationPipelineBuilder,
        SystemChecker, PDFViewer, AskUser
    )

    # Register all tools
    agent.register_tool(FileReader())
    agent.register_tool(FileWriter())
    agent.register_tool(FileEditor())
    agent.register_tool(FileDeleter())
    agent.register_tool(FileSearchEngine())
    
    # Some tools need the LLM from the planner (which is generic but shared)
    llm = agent.loop.planner.llm
    
    agent.register_tool(WebSearchTool(
        browser_service=browser_service,
        llm=llm,
    ))
    agent.register_tool(DeepSearchTool(
        browser_service=browser_service,
        llm=llm,
    ))
    agent.register_tool(BrowserController(browser_service=browser_service))
    agent.register_tool(MediaPreparer())
    agent.register_tool(TaskManagerTool())
    agent.register_tool(ReminderSystem())
    agent.register_tool(SpreadsheetManager())
    agent.register_tool(DocumentGenerator())
    agent.register_tool(ChatContextManager())
    agent.register_tool(ResponseFormatter())
    agent.register_tool(ProcessLauncher())
    agent.register_tool(SystemCommandBridge())
    agent.register_tool(AutomationPipelineBuilder())
    agent.register_tool(SystemChecker())
    agent.register_tool(PDFViewer())
    agent.register_tool(AskUser())

    # Attach brains to agent for direct access
    agent.intent_interpreter   = agent.loop.intent_interpreter
    agent.task_decomposer      = agent.loop.task_decomposer
    agent.action_planner       = agent.loop.action_planner
    agent.system_bridge        = agent.loop.system_bridge
    agent.context_memory       = agent.loop.context_memory
    agent.safety_decision      = agent.loop.safety_decision
    agent.ux_generator         = agent.loop.ux_generator
    agent.search_classifier    = agent.loop.search_classifier
    agent.browser_service      = browser_service

    return agent
