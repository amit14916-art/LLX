from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from kernel.models import Task, CodebaseContext, TestResults, ErrorEntry

def merge_tasks(left: List[Task], right: List[Task]) -> List[Task]:
    """
    Reducer function for LangGraph to merge two lists of Tasks.
    If a task ID in the update (right) already exists in the current state (left),
    it is updated with the new values. Otherwise, it is appended to the plan.
    """
    if left is None:
        left = []
    if right is None:
        right = []
        
    task_dict = {task.id: task for task in left}
    for task in right:
        task_dict[task.id] = task
        
    return list(task_dict.values())

def append_errors(left: List[ErrorEntry], right: List[ErrorEntry]) -> List[ErrorEntry]:
    """
    Reducer function for LangGraph to append new errors to the error log.
    """
    if left is None:
        left = []
    if right is None:
        right = []
    return left + right

def merge_verified(left: List[str], right: List[str]) -> List[str]:
    """
    Reducer function to merge verified worker tags in parallel execution.
    An empty list update clears the verified list.
    """
    if right is None:
        return left if left is not None else []
    if not right:
        return []
    if left is None:
        left = []
    return list(set(left + right))

class AgentState(TypedDict):
    """
    LangGraph state schema for the autonomous agentic IDE kernel.
    Expanded to track git branch names and code lint health scores.
    """
    goal: str
    plan: Annotated[List[Task], merge_tasks]
    codebase_context: CodebaseContext
    test_results: Optional[TestResults]
    error_log: Annotated[List[ErrorEntry], append_errors]
    git_branch: Optional[str]
    current_lint_score: Optional[float]
    critic_status: Optional[str]
    current_task_id: Optional[str]
    last_active_worker: Optional[str]
    verified_by: Annotated[List[str], merge_verified]
