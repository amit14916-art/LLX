from langgraph.graph import StateGraph, START, END
from kernel.state import AgentState
from kernel.planner import planner_agent
from kernel.manager import manager_agent
from kernel.workers import coder_node, tester_node, security_node
from kernel.critic import critic_agent

def route_manager_tasks(state: AgentState) -> str:
    """
    Decides where to route the workflow next after the manager runs.
    - If current_task_id is None, routes to 'critic' for static analysis check.
    - If current_task_id is set:
      - If last_active_worker is 'coder' -> route to 'tester' to verify.
      - If last_active_worker is 'tester' and task.error_message is set -> route to 'coder' to self-heal.
      - If last_active_worker is 'security' and task.error_message is set -> route to 'coder' to fix.
      - If last_active_worker is None (new task assigned):
        - If task description matches test keywords -> route to 'tester'.
        - If task description matches security keywords -> route to 'security'.
        - Otherwise -> route to 'coder'.
    """
    current_task_id = state.get("current_task_id")
    if not current_task_id:
        return "critic"
        
    plan = state.get("plan", [])
    task = next((t for t in plan if t.id == current_task_id), None)
    if not task:
        return "critic"
        
    last_active_worker = state.get("last_active_worker")
    
    if last_active_worker == "coder":
        return "tester"
        
    if last_active_worker == "tester" and task.error_message:
        return "coder"
        
    if last_active_worker == "security" and task.error_message:
        return "coder"
        
    # Classify a fresh task run
    desc = task.description.lower()
    if "test" in desc or "verify" in desc or "assert" in desc:
        return "tester"
    elif "security" in desc or "vulnerability" in desc or "scan" in desc:
        return "security"
        
    return "coder"

def route_critic_tasks(state: AgentState) -> str:
    """
    Determines next state after critic review.
    - If code passes linter check (score = 10.0), transitions to END.
    - If code fails linter check (score < 10.0), routes back to 'manager'
      to delegate the cleanup task to the Coder.
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
        
    return "manager"

def create_agent_graph() -> StateGraph:
    """
    Creates and wires together the autonomous planner, manager coordinator,
    and specialized workers (coder, tester, security) and final critic.
    """
    workflow = StateGraph(AgentState)
    
    # Register graph nodes
    workflow.add_node("planner", planner_agent)
    workflow.add_node("manager", manager_agent)
    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("security", security_node)
    workflow.add_node("critic", critic_agent)
    
    # Define execution cycles
    workflow.add_edge(START, "planner")
    workflow.add_edge("planner", "manager")
    
    # Worker returns back to coordinator manager
    workflow.add_edge("coder", "manager")
    workflow.add_edge("tester", "manager")
    workflow.add_edge("security", "manager")
    
    # Configure manager conditional routing
    workflow.add_conditional_edges(
        "manager",
        route_manager_tasks,
        {
            "coder": "coder",
            "tester": "tester",
            "security": "security",
            "critic": "critic"
        }
    )
    
    # Configure critic conditional routing
    workflow.add_conditional_edges(
        "critic",
        route_critic_tasks,
        {
            "manager": "manager",
            END: END
        }
    )
    
    return workflow
