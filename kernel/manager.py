from typing import Dict, Any, Optional
from langchain_core.runnables import RunnableConfig
from kernel.models import TaskStatus
from kernel.state import AgentState
from kernel.telemetry import log_telemetry
from kernel.utils import log_agent

def manager_agent(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Manager Coordinator Agent:
    - Coordinates task routing between specialized workers (Coder, Tester, Security).
    - Reviews last executed worker outcomes.
    - Handles self-healing redirection (routing failed tests or security violations back to Coder).
    """
    plan = list(state.get("plan", []))
    error_log = list(state.get("error_log", []))
    current_task_id = state.get("current_task_id")
    last_active_worker = state.get("last_active_worker")
    workspace_path = state["codebase_context"].workspace_path
    
    # 1. Evaluate output of recently executed worker
    if current_task_id:
        task = next((t for t in plan if t.id == current_task_id), None)
        if task:
            if last_active_worker == "coder":
                # Coder just wrote/fixed code. We must route to tester to verify!
                log_agent(f"[Manager] Coder finished. Routing task [{current_task_id}] to Tester for verification.", config)
                task.error_message = None # Clear error to allow testing
            elif last_active_worker == "tester":
                # Check if the latest error is from this tester execution
                if error_log and error_log[-1].step == f"tester_node:{current_task_id}":
                    log_agent(f"[Manager] Tester failed for task [{current_task_id}]. Routing to Coder for healing.", config)
                    task.status = TaskStatus.IN_PROGRESS
                    task.error_message = error_log[-1].message
                else:
                    # Tester passed!
                    log_agent(f"[Manager] Tester passed for task [{current_task_id}]. Task COMPLETED.", config)
                    task.status = TaskStatus.COMPLETED
                    task.error_message = None
                    current_task_id = None # Clear to fetch next task
                    last_active_worker = None
            elif last_active_worker == "security":
                # Check if the latest error is from this security execution
                if error_log and error_log[-1].step == f"security_node:{current_task_id}":
                    log_agent(f"[Manager] Security scan failed for task [{current_task_id}]. Routing to Coder to fix.", config)
                    task.status = TaskStatus.IN_PROGRESS
                    task.error_message = error_log[-1].message
                else:
                    # Security passed!
                    log_agent(f"[Manager] Security passed for task [{current_task_id}]. Task COMPLETED.", config)
                    task.status = TaskStatus.COMPLETED
                    task.error_message = None
                    current_task_id = None # Clear to fetch next task
                    last_active_worker = None
                    
    # 2. Assign the next pending task
    if not current_task_id:
        next_task = next((t for t in plan if t.status in (TaskStatus.PENDING, TaskStatus.FAILED)), None)
        if next_task:
            current_task_id = next_task.id
            next_task.status = TaskStatus.IN_PROGRESS
            last_active_worker = None # Reset for the new task
            log_agent(f"[Manager] Next task assigned: [{current_task_id}] {next_task.description}", config)
        else:
            log_agent("[Manager] All tasks completed. Transitioning to final Critic review.", config)
            current_task_id = None
            last_active_worker = None
            
    # Log manager telemetry (Manager node cost is minimal, uses 0 model tokens local check)
    log_telemetry(
        node_name="manager",
        tokens_used=0,
        success=True,
        error_msg=None,
        workspace_path=workspace_path,
        config=config,
        current_task_id=current_task_id
    )
    
    return {
        "plan": plan,
        "current_task_id": current_task_id,
        "last_active_worker": last_active_worker
    }
