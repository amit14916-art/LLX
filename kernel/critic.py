import os
import ast
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional
from langchain_core.runnables import RunnableConfig
from kernel.state import AgentState, append_errors
from kernel.models import Task, ErrorEntry
from kernel.git_tools import commit_changes
from kernel.utils import log_agent

def run_linter_check(workspace_path: str, config: Optional[RunnableConfig] = None) -> tuple[float, str]:
    """
    Runs static analysis (flake8 and mypy) against the generated code.
    Falls back to AST compilation checks if style libraries are not installed.
    """
    log_messages = []
    total_errors = 0
    
    # 1. Run flake8
    try:
        res = subprocess.run(
            ["flake8", "."],
            cwd=workspace_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 127 or "not found" in res.stderr.lower():
            raise FileNotFoundError()
        
        stdout = res.stdout.strip()
        if stdout:
            flake_errs = [line for line in stdout.split("\n") if line.strip()]
            total_errors += len(flake_errs)
            log_messages.append(f"--- flake8 Errors ---\n{stdout}")
    except (FileNotFoundError, Exception):
        # Graceful AST compilation fallback
        ast_errors = []
        exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", ".lancedb"}
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, workspace_path).replace("\\", "/")
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            ast.parse(f.read(), filename=full_path)
                    except SyntaxError as e:
                        ast_errors.append(f"{rel_path}:{e.lineno}:{e.offset}: SyntaxError: {e.msg}")
                    except Exception as e:
                        ast_errors.append(f"{rel_path}:0:0: ReadError: {e}")
        
        if ast_errors:
            total_errors += len(ast_errors)
            log_messages.append(f"--- AST Syntax Errors ---\n" + "\n".join(ast_errors))

    # 2. Run mypy (if available)
    try:
        res = subprocess.run(
            ["mypy", "."],
            cwd=workspace_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if not (res.returncode == 127 or "not found" in res.stderr.lower()):
            stdout = res.stdout.strip()
            # Mypy reports success via: 'Success: no issues found in ...'
            if stdout and "Success:" not in stdout:
                mypy_errs = [line for line in stdout.split("\n") if line.strip() and ":" in line]
                total_errors += len(mypy_errs)
                log_messages.append(f"--- mypy Type Mismatches ---\n{stdout}")
    except Exception:
        pass # Gracefully skip mypy checks if mypy execution errors out

    # Compute a 0-10 score based on linter errors
    score = max(0.0, 10.0 - total_errors)
    combined_output = "\n\n".join(log_messages) if log_messages else "Static Analysis: No errors found."
    return score, combined_output

def critic_agent(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    LangGraph critic node. Runs flake8/mypy, rates health score, and updates
    state status to 'PASSED' or 'REJECTED'. On rejection, logs traces and
    hands execution back to Coder for refinements.
    """
    workspace_path = state["codebase_context"].workspace_path
    log_agent("\n>>> Running Critic Peer Review (flake8 & mypy checks)...", config)
    
    score, linter_output = run_linter_check(workspace_path, config)
    log_agent(f"Critic: Static analysis score: {score:.2f}/10.00", config)
    
    error_log = list(state.get("error_log", []))
    plan = list(state.get("plan", []))
    
    if score < 10.0:
        log_agent(f"Critic: Code REJECTED. Lint/type errors found:\n{linter_output}", config)
        
        err = ErrorEntry(
            timestamp=datetime.utcnow().isoformat(),
            step="critic_agent",
            message=f"Peer review REJECTED code (Score: {score:.2f}/10.00)",
            traceback=linter_output
        )
        error_log = append_errors(error_log, [err])
        
        # Inject style cleanup task to plan
        clean_task_id = "T_LINT_CLEANUP"
        existing_cleanup = None
        for t in plan:
            if t.id == clean_task_id:
                existing_cleanup = t
                break
                
        desc = f"Refine code to fix style/type violations:\n{linter_output}"
        if existing_cleanup:
            existing_cleanup.status = "pending"
            existing_cleanup.description = desc
        else:
            new_task = Task(
                id=clean_task_id,
                description=desc,
                status="pending"
            )
            plan.append(new_task)
            
        return {
            "error_log": error_log,
            "current_lint_score": score,
            "plan": plan,
            "critic_status": "REJECTED"
        }
    else:
        log_agent("Critic: Peer review PASSED! Committing codebase changes...", config)
        
        # Invoke Git commit
        configurable = config.get("configurable", {})
        llm = configurable.get("llm")
        
        commit_msg = commit_changes(workspace_path, state["goal"], llm)
        log_agent(f"Critic: Created commit: '{commit_msg}'", config)
        
        return {
            "current_lint_score": 10.0,
            "error_log": error_log,
            "critic_status": "PASSED"
        }
