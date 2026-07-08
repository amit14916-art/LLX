import re
import os
import ast
from datetime import datetime
from typing import Dict, Any, List
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from kernel.models import Task, TaskStatus, ErrorEntry
from kernel.state import AgentState, append_errors
from kernel.tools import ToolRegistry
from kernel.telemetry import log_telemetry
from kernel.utils import log_agent

def get_langchain_tools(registry: ToolRegistry) -> List[StructuredTool]:
    """Wraps ToolRegistry functions as LangChain StructuredTools."""
    return [
        StructuredTool.from_function(func=registry.read_file, name="read_file", description=registry.read_file.__doc__.strip()),
        StructuredTool.from_function(func=registry.write_file, name="write_file", description=registry.write_file.__doc__.strip()),
        StructuredTool.from_function(func=registry.execute_shell, name="execute_shell", description=registry.execute_shell.__doc__.strip()),
        StructuredTool.from_function(func=registry.list_files, name="list_files", description=registry.list_files.__doc__.strip())
    ]

# ----------------------------------------------------
# 1. Coder Worker Node
# ----------------------------------------------------
def coder_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Coder Worker: Focuses on writing core logic, functions, and modifications.
    Does not run unit tests or security scans (delegated to specialized peers).
    """
    configurable = config.get("configurable", {})
    llm = configurable.get("llm")
    workspace_path = state["codebase_context"].workspace_path
    
    current_task_id = state.get("current_task_id")
    plan = list(state.get("plan", []))
    task = next((t for t in plan if t.id == current_task_id), None)
    
    if not task:
        return {}
        
    log_agent(f"[Coder Worker] Starting implementation for task: '{task.description}'", config)
    
    registry = ToolRegistry(workspace_path=workspace_path)
    lc_tools = get_langchain_tools(registry)
    llm_with_tools = llm.bind_tools(lc_tools)
    
    messages = [
        {"role": "system", "content": "You are a specialized Coder Worker. Write clean, correct code implementation files using read_file and write_file tools. Focus purely on writing correct logic as described in the task."},
        {"role": "user", "content": f"Task: {task.description}\nWorkspace: {workspace_path}"}
    ]
    if task.error_message:
        messages.append({"role": "user", "content": f"Previous verification failed with the following errors:\n{task.error_message}\nPlease fix the issues and write the correct implementation."})
        
    coder_tokens = 0
    task_success = True
    error_msg = None
    
    for step in range(6):
        in_tok = sum(len(str(m)) for m in messages) // 4
        response = llm_with_tools.invoke(messages)
        out_tok = (len(str(response.content)) + len(str(response.tool_calls))) // 4
        coder_tokens += max(10, in_tok + out_tok)
        
        messages.append(response)
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            t_name = tool_call["name"]
            t_args = tool_call["args"]
            log_agent(f"[Coder Worker] Tool Call: {t_name}({t_args})", config)
            tool_output = registry.execute(t_name, **t_args)
            messages.append({
                "role": "tool",
                "name": t_name,
                "tool_call_id": tool_call["id"],
                "content": str(tool_output)
            })

    log_telemetry(
        node_name="coder",
        tokens_used=coder_tokens,
        success=task_success,
        error_msg=error_msg,
        workspace_path=workspace_path,
        config=config,
        task_id=task.id
    )
    
    return {
        "plan": plan,
        "last_active_worker": "coder",
        "verified_by": []
    }

# ----------------------------------------------------
# 2. Tester Worker Node
# ----------------------------------------------------
def tester_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Tester Worker: Focuses on writing verification test cases (e.g., test_*.py)
    and running the test suites to assert correctness.
    """
    configurable = config.get("configurable", {})
    llm = configurable.get("llm")
    test_command = configurable.get("test_command", "pytest")
    workspace_path = state["codebase_context"].workspace_path
    
    current_task_id = state.get("current_task_id")
    plan = list(state.get("plan", []))
    task = next((t for t in plan if t.id == current_task_id), None)
    
    if not task:
        return {}
        
    log_agent(f"[Tester Worker] Designing unit tests for task: '{task.description}'", config)
    
    registry = ToolRegistry(workspace_path=workspace_path)
    lc_tools = get_langchain_tools(registry)
    llm_with_tools = llm.bind_tools(lc_tools)
    
    messages = [
        {"role": "system", "content": f"You are a specialized Tester Worker. Your role is to write clean, complete unit test files using write_file and run them with execute_shell. Run the test command '{test_command}' to verify that all code compiles and passes successfully."},
        {"role": "user", "content": f"Task implemented: {task.description}\nWorkspace: {workspace_path}"}
    ]
    
    tester_tokens = 0
    test_passed = False
    test_output = ""
    
    for step in range(5):
        in_tok = sum(len(str(m)) for m in messages) // 4
        response = llm_with_tools.invoke(messages)
        out_tok = (len(str(response.content)) + len(str(response.tool_calls))) // 4
        tester_tokens += max(10, in_tok + out_tok)
        
        messages.append(response)
        if not response.tool_calls:
            break
            
        for tool_call in response.tool_calls:
            t_name = tool_call["name"]
            t_args = tool_call["args"]
            log_agent(f"[Tester Worker] Tool Call: {t_name}({t_args})", config)
            tool_output = registry.execute(t_name, **t_args)
            messages.append({
                "role": "tool",
                "name": t_name,
                "tool_call_id": tool_call["id"],
                "content": str(tool_output)
            })
            
            if t_name == "execute_shell" and test_command in str(t_args.get("command", "")):
                test_output = str(tool_output)
                match = re.search(r"\[Exit Code: (-?\d+)\]", test_output)
                exit_code = int(match.group(1)) if match else -1
                test_passed = (exit_code == 0)

    # Perform a final test run if not run already
    if not test_passed:
        test_res = registry.execute_shell(test_command)
        test_output = test_res
        match = re.search(r"\[Exit Code: (-?\d+)\]", test_res)
        exit_code = int(match.group(1)) if match else -1
        test_passed = (exit_code == 0)
        
    error_log = list(state.get("error_log", []))
    if not test_passed:
        log_agent(f"[Tester Worker] Tests failed:\n{test_output}", config)
        err = ErrorEntry(
            timestamp=datetime.utcnow().isoformat(),
            step=f"tester_node:{task.id}",
            message=f"Tester node reported test failures for task '{task.description}'",
            traceback=test_output
        )
        error_log = append_errors(error_log, [err])

    log_telemetry(
        node_name="tester",
        tokens_used=tester_tokens,
        success=test_passed,
        error_msg=None if test_passed else "Unit tests failed.",
        workspace_path=workspace_path,
        config=config,
        task_id=task.id
    )
    
    return {
        "error_log": error_log,
        "test_results": None,
        "last_active_worker": "tester",
        "verified_by": ["tester"]
    }

# ----------------------------------------------------
# 3. Security Worker Node
# ----------------------------------------------------
def security_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Security Worker: Scans the codebase for security risks (e.g., hardcoded credentials,
    eval/exec statements, command injection vectors in subprocess calls).
    """
    workspace_path = state["codebase_context"].workspace_path
    current_task_id = state.get("current_task_id")
    plan = list(state.get("plan", []))
    task = next((t for t in plan if t.id == current_task_id), None)
    
    if not task:
        return {}
        
    log_agent(f"[Security Worker] Performing vulnerability scan on task implementation...", config)
    
    security_violations = []
    exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", ".lancedb"}
    
    # Common vulnerability patterns
    patterns = {
        r'\beval\s*\(': "Use of unsafe eval() statement",
        r'\bexec\s*\(': "Use of unsafe exec() statement",
        r'shell\s*=\s*True': "Command injection vulnerability (shell=True in subprocess)",
        r'(?:api_key|password|secret|passwd|token)\s*=\s*[\'"][a-zA-Z0-9_\-]{8,}[\'"]': "Hardcoded secret or credential"
    }
    
    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in {".py", ".ts", ".js", ".tsx"}:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, workspace_path).replace("\\", "/")
                
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        for pattern, desc in patterns.items():
                            if re.search(pattern, line):
                                security_violations.append(
                                    f"File: {rel_path} (Line {idx+1}): {desc} -> {line.strip()}"
                                )
                except Exception as e:
                    security_violations.append(f"File: {rel_path}: Error reading file: {e}")
                    
    error_log = list(state.get("error_log", []))
    security_success = (len(security_violations) == 0)
    
    if not security_success:
        violations_summary = "\n".join(security_violations)
        log_agent(f"[Security Worker] Vulnerability alert:\n{violations_summary}", config)
        err = ErrorEntry(
            timestamp=datetime.utcnow().isoformat(),
            step=f"security_node:{task.id if task else 'unknown'}",
            message="Security scanning detected critical vulnerabilities",
            traceback=violations_summary
        )
        error_log = append_errors(error_log, [err])
    else:
        log_agent("[Security Worker] Vulnerability scan passed. No critical vulnerabilities found.", config)

    log_telemetry(
        node_name="security",
        tokens_used=0,
        success=security_success,
        error_msg=None if security_success else "Security vulnerabilities detected.",
        workspace_path=workspace_path,
        config=config,
        task_id=task.id if task else "unknown"
    )
    
    return {
        "error_log": error_log,
        "last_active_worker": "security",
        "verified_by": ["security"]
    }
