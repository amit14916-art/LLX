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
                # Coder just wrote/fixed code. We must route to tester/security to verify!
                log_agent(f"[Manager] Coder finished. Routing task [{current_task_id}] to Tester and Security concurrently for verification.", config)
                task.error_message = None # Clear error to allow testing
            elif last_active_worker in ("tester", "security"):
                # Check if there were any failures in either parallel node for this task run
                failed_steps = []
                if error_log:
                    # Check at most the last 2 entries in the error log since they run concurrently
                    for err in error_log[-2:]:
                        if err.step in (f"tester_node:{current_task_id}", f"security_node:{current_task_id}"):
                            failed_steps.append(err)
                
                if failed_steps:
                    err_msg = " & ".join(e.message for e in failed_steps)
                    log_agent(f"[Manager] Verification failed for task [{current_task_id}]: {err_msg}. Routing to Coder for healing.", config)
                    task.status = TaskStatus.IN_PROGRESS
                    task.error_message = err_msg
                else:
                    # Both passed!
                    log_agent(f"[Manager] Verification passed (Tester & Security succeeded) for task [{current_task_id}]. Task COMPLETED.", config)
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
