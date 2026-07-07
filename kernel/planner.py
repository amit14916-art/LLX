from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models import BaseChatModel
from kernel.models import Task
from kernel.state import AgentState
from kernel.retriever import ContextRetriever
from kernel.dependency_mapper import get_dependency_graph
from kernel.utils import log_agent

class PlanOutput(BaseModel):
    """
    Schema for the structured output of the planner agent.
    Forces the LLM to output a sequential, ordered list of tasks.
    """
    tasks: List[Task] = Field(
        ...,
        description="A list of sequential technical tasks required to achieve the goal. Each task must have a unique ID."
    )

def create_planner_node(llm: BaseChatModel):
    """
    Factory to create a planner agent node bound to a specific LangChain ChatModel.
    Uses the model's with_structured_output interface to guarantee compliance.
    """
    structured_llm = llm.with_structured_output(PlanOutput)

    def planner_agent(state: AgentState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """
        Planner agent node function. Receives the goal from state, generates a structured plan,
        and returns the tasks list and updated codebase context (with dependency graph metadata).
        """
        goal = state.get("goal")
        if not goal:
            raise ValueError("Planner Agent Error: Goal is not defined in AgentState.")

        log_agent(f"Planner Agent: Analyzing goal and generating technical plan for: '{goal}'", config)

        # Retrieve workspace path from codebase context
        workspace_path = state["codebase_context"].workspace_path
        
        # 0. Automatically create a new git branch
        from kernel.git_tools import init_git_branch
        log_agent("Planner Agent: Setting up AgenticGit branch for workspace...", config)
        git_branch = init_git_branch(workspace_path)
        log_agent(f"Planner Agent: Active workspace branch set to '{git_branch}'", config)
        
        # 1. semantic context retrieval using LanceDB
        log_agent("Planner Agent: Scanning workspace and indexing files in LanceDB...", config)
        retriever = ContextRetriever(workspace_path)
        retriever.index_workspace()
        
        log_agent(f"Planner Agent: Performing semantic search for query: '{goal}'", config)
        snippets = retriever.retrieve_context(goal, limit=5)
        
        context_str = ""
        if snippets:
            context_str += "=== Project Context (Top 5 Semantic Snippets) ===\n"
            for idx, snip in enumerate(snippets):
                context_str += f"\nSnippet {idx+1} [File: {snip['filepath']}]:\n"
                context_str += f"```\n{snip['content']}\n```\n"
            log_agent(f"Planner Agent: Successfully injected {len(snippets)} relevant code snippets into prompt.", config)
        else:
            log_agent("Planner Agent: No relevant context snippets found in workspace index.", config)

        # 2. dependency mapping
        log_agent("Planner Agent: Generating workspace file dependency graph...", config)
        dep_graph = get_dependency_graph(workspace_path)
        
        # Update state metadata
        codebase_context = state["codebase_context"]
        codebase_context.dependency_graph = dep_graph
        
        dep_str = "=== Codebase Dependency Graph ===\n"
        for file, deps in dep_graph.items():
            dep_str += f"File: {file} -> Imports: {', '.join(deps) if deps else 'None'}\n"
        log_agent(f"Planner Agent: Dependency graph built ({len(dep_graph)} files mapped).", config)

        # 3. Inject context into system prompt
        prompt = (
            f"You are the Strategist Planner for an autonomous agentic IDE kernel.\n"
            f"Your current goal is: '{goal}'\n\n"
            f"{context_str}\n"
            f"{dep_str}\n"
            f"Break down this goal into a sequential list of technical tasks. "
            f"Generate a clear, execution-ready sequence. Each task must have a unique, short ID (e.g. T1, T2) "
            f"and start in the 'pending' status."
        )

        # Invoke model with structured output
        plan_res: PlanOutput = structured_llm.invoke(prompt, config)
        
        # Calculate tokens and log telemetry
        in_tokens = len(prompt) // 4
        out_tokens = sum(len(t.description) for t in plan_res.tasks) // 4
        total_tokens = max(100, in_tokens + out_tokens)
        
        from kernel.telemetry import log_telemetry
        log_telemetry(
            node_name="planner",
            tokens_used=total_tokens,
            success=True,
            error_msg=None,
            workspace_path=workspace_path,
            config=config,
            task_count=len(plan_res.tasks)
        )
        
        return {
            "plan": plan_res.tasks,
            "codebase_context": codebase_context,
            "git_branch": git_branch
        }

    return planner_agent

def planner_agent(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Default planner agent node. Extracts the LLM from the LangGraph config parameters.
    The config should contain a 'configurable' dictionary with a 'llm' key.
    """
    configurable = config.get("configurable", {}) if config else {}
    llm = configurable.get("llm")
    if not llm or not isinstance(llm, BaseChatModel):
        raise ValueError(
            "Planner Agent Error: A LangChain BaseChatModel must be provided in the graph configuration.\n"
            "Pass it via config: graph.invoke(state, {'configurable': {'llm': chat_model}})"
        )
    
    node = create_planner_node(llm)
    return node(state, config)
