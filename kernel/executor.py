import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from langchain_core.runnables import RunnableConfig
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import StructuredTool
from kernel.models import Task, TaskStatus, ErrorEntry
from kernel.state import AgentState, append_errors
from kernel.tools import ToolRegistry
from kernel.utils import log_agent

def get_langchain_tools(registry: ToolRegistry) -> List[StructuredTool]:
    """
    Wraps ToolRegistry functions as LangChain StructuredTools
    so they can be natively bound to LLMs that support tool calling.
    """
    return [
        StructuredTool.from_function(
            func=registry.read_file,
            name="read_file",
            description=registry.read_file.__doc__.strip()
        ),
        StructuredTool.from_function(
            func=registry.write_file,
            name="write_file",
            description=registry.write_file.__doc__.strip()
        ),
        StructuredTool.from_function(
            func=registry.execute_shell,
            name="execute_shell",
            description=registry.execute_shell.__doc__.strip()
        ),
        StructuredTool.from_function(
            func=registry.list_files,
            name="list_files",
            description=registry.list_files.__doc__.strip()
        )
    ]

def executor_agent(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """
    LangGraph executor node. Iterates through plan tasks, writes code,
    executes tests, and triggers a self-healing loop on test failures.
    
    Configuration options (configurable dictionary):
    - llm: LangChain ChatModel (Required)
    - test_command: Shell command to run tests (Default: 'pytest')
    - max_retries: Number of attempts to heal failing code (Default: 3)
    """
    configurable = config.get("configurable", {}) if config else {}
    llm = configurable.get("llm")
    if not llm or not isinstance(llm, BaseChatModel):
        raise ValueError(
            "Executor Agent Error: A LangChain BaseChatModel must be provided in the graph configuration.\n"
            "Pass it via config: graph.invoke(state, {'configurable': {'llm': chat_model}})"
        )
        
    test_command = configurable.get("test_command", "pytest")
    max_retries = configurable.get("max_retries", 3)
    
    # Initialize workspace-tied registry and LangChain tools
    workspace_path = state["codebase_context"].workspace_path
    registry = ToolRegistry(workspace_path=workspace_path)
    lc_tools = get_langchain_tools(registry)
    llm_with_tools = llm.bind_tools(lc_tools)
    
    # Track changes to the plan and error log
    plan = list(state.get("plan", []))
    error_log = list(state.get("error_log", []))
    
    for task in plan:
        # Skip tasks that are already complete
        if task.status == TaskStatus.COMPLETED:
            continue
            
        log_agent(f"\n>>> Executing Task [{task.id}]: {task.description}", config)
        task.status = TaskStatus.IN_PROGRESS
        
        # Initialize context for this task's coding session
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Coder Agent for an autonomous IDE kernel. Your goal is to write clean, correct code "
                    "that accomplishes the user's task. You have read/write/shell tools. "
                    "Always verify file details before writing, and follow up with testing. "
                    "Make concise tool calls to complete the task."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Overall Goal: {state['goal']}\n"
                    f"Current Workspace Path: {workspace_path}\n"
                    f"Task to execute: {task.description}\n"
                    f"List of active files: {state['codebase_context'].active_files}"
                )
            }
        ]
        
        # Execution loop for a single task (max 10 steps to prevent agent loops)
        task_success = True
        test_passed = False
        
        for step in range(10):
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            # If the model didn't call any tools, it assumes it is finished
            if not response.tool_calls:
                break
                
            # Process each tool call sequentially
            for tool_call in response.tool_calls:
                t_name = tool_call["name"]
                t_args = tool_call["args"]
                
                log_agent(f"Calling tool: {t_name}({t_args})", config)
                tool_output = registry.execute(t_name, **t_args)
                
                messages.append({
                    "role": "tool",
                    "name": t_name,
                    "tool_call_id": tool_call["id"],
                    "content": str(tool_output)
                })
                
                # Check for test run trigger: Run tests after file writes
                if t_name == "write_file":
                    log_agent(f"File modified. Running verification test: '{test_command}'", config)
                    test_res = registry.execute_shell(test_command)
                    log_agent(f"Test Run Output Summary:\n{test_res}", config)
                    
                    # Parse exit code from execute_shell output
                    match = re.search(r"\[Exit Code: (-?\d+)\]", test_res)
                    exit_code = int(match.group(1)) if match else -1
                    
                    if exit_code == 0:
                        test_passed = True
                    else:
                        test_passed = False
                        log_agent(f"Test failed (Exit Code {exit_code}). Starting self-healing loop...", config)
                        
                        # Add test failure to error log
                        err_entry = ErrorEntry(
                            timestamp=datetime.utcnow().isoformat(),
                            step=f"executor_agent:{task.id}",
                            message=f"Test failure during task '{task.description}' execution.",
                            traceback=test_res
                        )
                        error_log = append_errors(error_log, [err_entry])
                        
                        # Self-healing loop: prompt LLM to fix the bug
                        healed = False
                        for retry in range(max_retries):
                            log_agent(f"  Self-healing retry {retry + 1}/{max_retries}", config)
                            healing_prompt = (
                                f"Test failed with Exit Code {exit_code}.\n"
                                f"Test output is:\n{test_res}\n\n"
                                f"Please identify the bug and use the write_file tool to apply a fix."
                            )
                            messages.append({"role": "user", "content": healing_prompt})
                            
                            heal_resp = llm_with_tools.invoke(messages)
                            messages.append(heal_resp)
                            
                            if heal_resp.tool_calls:
                                # Apply the fix tool calls
                                for heal_call in heal_resp.tool_calls:
                                    h_name = heal_call["name"]
                                    h_args = heal_call["args"]
                                    log_agent(f"  Applying fix call: {h_name}({h_args})", config)
                                    heal_out = registry.execute(h_name, **h_args)
                                    messages.append({
                                        "role": "tool",
                                        "name": h_name,
                                        "tool_call_id": heal_call["id"],
                                        "content": str(heal_out)
                                    })
                                
                                # Re-run tests
                                test_res = registry.execute_shell(test_command)
                                match = re.search(r"\[Exit Code: (-?\d+)\]", test_res)
                                exit_code = int(match.group(1)) if match else -1
                                
                                if exit_code == 0:
                                    log_agent("  Self-healing succeeded! Code passed verification tests.", config)
                                    healed = True
                                    test_passed = True
                                    break
                                else:
                                    # Update error log with the new failure details
                                    err_entry = ErrorEntry(
                                        timestamp=datetime.utcnow().isoformat(),
                                        step=f"executor_agent:{task.id}:retry_{retry+1}",
                                        message=f"Self-healing attempt {retry+1} failed.",
                                        traceback=test_res
                                    )
                                    error_log = append_errors(error_log, [err_entry])
                            else:
                                log_agent("  Self-healing failed: Model did not propose a tool call fix.", config)
                                break
                                
                        if not healed:
                            task_success = False
                            break
                            
            if not task_success:
                break
                
        # Final test validation to guarantee correctness if no test has passed yet
        if task_success and not test_passed:
            log_agent(f"Task completed. Performing final verification test: '{test_command}'", config)
            test_res = registry.execute_shell(test_command)
            match = re.search(r"\[Exit Code: (-?\d+)\]", test_res)
            exit_code = int(match.group(1)) if match else -1
            if exit_code != 0:
                task_success = False
                err_entry = ErrorEntry(
                    timestamp=datetime.utcnow().isoformat(),
                    step=f"executor_agent:{task.id}:final_check",
                    message="Final verification test failed.",
                    traceback=test_res
                )
                error_log = append_errors(error_log, [err_entry])
                
        # Set task outcome status
        if task_success:
            log_agent(f"Task [{task.id}] completed successfully.", config)
            task.status = TaskStatus.COMPLETED
            task.error_message = None
        else:
            log_agent(f"Task [{task.id}] execution failed.", config)
            task.status = TaskStatus.FAILED
            task.error_message = "Test suite continues to fail after all self-healing attempts."
            break

    return {"plan": plan, "error_log": error_log}
