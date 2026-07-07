from langgraph.graph import StateGraph, START, END
from kernel.state import AgentState
from kernel.planner import planner_agent
from kernel.executor import executor_agent
from kernel.critic import critic_agent
from kernel.models import TaskStatus

def should_continue(state: AgentState) -> str:
    """
    Determines next state after executor run.
    - If all tasks are completed, transitions to 'critic' for static analysis.
    - If there are failing tasks or errors, loops back to 'executor'.
    """
    plan = state.get("plan", [])
    if plan and all(t.status == TaskStatus.COMPLETED for t in plan):
        return "critic"
        
    return "executor"

def should_critic_continue(state: AgentState) -> str:
    """
    Determines next state after critic peer review.
    - If code passes linter check (score = 10.0), transitions to END.
    - If code fails linter check (score < 10.0), loops back to 'executor' for style clean-up.
    - Exits after 3 failed linter cleanup rounds to prevent infinite routing.
    """
    lint_score = state.get("current_lint_score")
    if lint_score is not None and lint_score >= 10.0:
        return END
        
    error_log = state.get("error_log", [])
    critic_failures = sum(1 for err in error_log if err.step == "critic_agent")
    if critic_failures >= 3:
        print("[Critic] Peer review: Max style cleanup iterations reached. Exiting graph.")
        return END
        
    return "executor"

def create_agent_graph() -> StateGraph:
    """
    Creates and wires together the autonomous planner, coder, and critic agents.
    """
    workflow = StateGraph(AgentState)
    
    # Register graph nodes
    workflow.add_node("planner", planner_agent)
    workflow.add_node("executor", executor_agent)
    workflow.add_node("critic", critic_agent)
    
    # Define start entry edge
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "executor")
    
    # Configure executor conditional branching
    workflow.add_conditional_edges(
        "executor",
        should_continue,
        {
            "critic": "critic",
            "executor": "executor"
        }
    )
    
    # Configure critic conditional branching
    workflow.add_conditional_edges(
        "critic",
        should_critic_continue,
        {
            "executor": "executor",
            END: END
        }
    )
    
    return workflow
