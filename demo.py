import os
import sys
from datetime import datetime
from typing import Optional, List, Type, Any
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage, BaseMessage

from kernel.models import Task, TaskStatus, CodebaseContext, TestResults, ErrorEntry
from kernel.state import merge_tasks, append_errors, AgentState
from kernel.tools import ToolRegistry
from kernel.planner import planner_agent
from kernel.executor import executor_agent
from kernel.graph import create_agent_graph

def print_separator(title: str):
    print("\n" + "="*50)
    print(f" {title} ")
    print("="*50)

# ----------------------------------------------------
# Mock LLM classes to simulate structured outputs and tool calls
# ----------------------------------------------------
class MockStructuredLLM:
    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema
        
    def invoke(self, prompt: str, config: Optional[Any] = None) -> Any:
        if self.schema.__name__ == "PlanOutput":
            from kernel.planner import PlanOutput
            return PlanOutput(tasks=[
                Task(id="T01", description="Implement a calculator add function in calc.py and verify it passes test_calc.py", status=TaskStatus.PENDING)
            ])
        raise ValueError(f"Mock model does not support schema: {self.schema.__name__}")

class MockLLM(BaseChatModel):
    """A mock LangChain ChatModel to facilitate local demo execution without external keys."""
    
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        # Check if this is the Tester Worker
        is_tester = False
        for msg in messages:
            content_str = ""
            if isinstance(msg, dict):
                content_str = str(msg.get("content", ""))
            else:
                content_str = str(getattr(msg, "content", ""))
            if "Tester Worker" in content_str:
                is_tester = True
                break

        if is_tester:
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "test_calc.py",
                    "content": (
                        "import calc\n"
                        "def test_add():\n"
                        "    assert calc.add(2, 3) == 5\n"
                        "if __name__ == '__main__':\n"
                        "    test_add()\n"
                        "    print('Test passed successfully!')\n"
                    )
                },
                "id": "call_test_777"
            }]
            ai_msg = AIMessage(
                content="I will write the test_calc.py unit test file to verify the calculator addition logic.",
                tool_calls=tool_calls
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])

        # Check if the dialogue history already contains our fix execution confirmation ("call_fix_999")
        is_success = False
        for msg in reversed(messages):
            if hasattr(msg, "tool_call_id") and getattr(msg, "tool_call_id") == "call_fix_999":
                is_success = True
                break
            if isinstance(msg, dict) and msg.get("tool_call_id") == "call_fix_999":
                is_success = True
                break
            if "Test passed successfully!" in getattr(msg, "content", ""):
                is_success = True
                break
                
        if is_success:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="The calculator implementation was successfully corrected and all tests are passing. The task is fully complete."
            ))])
            
        # Check if the dialogue history contains a test failure to trigger healing
        is_healing_attempt = False
        for msg in reversed(messages):
            content_str = ""
            if isinstance(msg, dict):
                content_str = str(msg.get("content", ""))
            else:
                content_str = str(getattr(msg, "content", ""))
            if "Exit Code" in content_str or "failed" in content_str or "vulnerabilities" in content_str:
                is_healing_attempt = True
                break
                
        if is_healing_attempt:
            # Debug/Heal: write correct implementation
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "calc.py",
                    "content": "def add(a, b):\n    return a + b  # Corrected implementation\n"
                },
                "id": "call_fix_999"
            }]
            ai_msg = AIMessage(
                content="I see the test failed because we used subtraction (-) instead of addition (+). Writing the fix now.",
                tool_calls=tool_calls
            )
        else:
            # First attempt: write buggy implementation
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "calc.py",
                    "content": "def add(a, b):\n    return a - b  # Buggy implementation (subtraction instead of addition)\n"
                },
                "id": "call_write_888"
            }]
            ai_msg = AIMessage(
                content="I will write the calc.py file with the add function logic.",
                tool_calls=tool_calls
            )
            
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])
        
    @property
    def _llm_type(self) -> str:
        return "mock-chat-model"
        
    def with_structured_output(self, schema: Type[BaseModel], **kwargs):
        return MockStructuredLLM(schema)

    def bind_tools(self, tools: List[Any], **kwargs):
        return self

# ----------------------------------------------------
# Demos
# ----------------------------------------------------
def demonstrate_state():
    print_separator("1. LangGraph State Reducers Demonstration")
    
    state: AgentState = {
        "goal": "Build an autonomous IDE kernel",
        "plan": [],
        "codebase_context": CodebaseContext(
            workspace_path=os.path.abspath("."),
            active_files=["main.py"]
        ),
        "test_results": None,
        "error_log": []
    }
    
    print("Initial Goal:", state["goal"])
    print("Initial Plan:", state["plan"])
    print("Initial Error Log:", state["error_log"])
    
    print("\n--- Step 1: Adding a task to the plan ---")
    task_1 = Task(id="T01", description="Design State management architecture")
    state["plan"] = merge_tasks(state["plan"], [task_1])
    print("Plan:", [f"{t.id}: {t.description} ({t.status.value})" for t in state["plan"]])
    
    print("\n--- Step 2: Updating Task 1 and adding Task 2 ---")
    task_1_updated = Task(id="T01", description="Design State management architecture", status=TaskStatus.COMPLETED)
    task_2 = Task(id="T02", description="Implement Tool Registry")
    
    state["plan"] = merge_tasks(state["plan"], [task_1_updated, task_2])
    print("Plan after update (Task 1 updated, Task 2 appended):")
    for t in state["plan"]:
        print(f"  - {t.id}: {t.description} -> [{t.status.value}]")
        
    print("\n--- Step 3: Appending errors ---")
    err_1 = ErrorEntry(
        timestamp=datetime.utcnow().isoformat(),
        step="run_tests_node",
        message="ModuleNotFoundError: No module named 'langgraph'"
    )
    state["error_log"] = append_errors(state["error_log"], [err_1])
    
    err_2 = ErrorEntry(
        timestamp=datetime.utcnow().isoformat(),
        step="execute_shell_tool",
        message="PermissionError: [WinError 5] Access is denied"
    )
    state["error_log"] = append_errors(state["error_log"], [err_2])
    
    print("Error Log:")
    for err in state["error_log"]:
        print(f"  [{err.timestamp}] Node: '{err.step}' -> {err.message}")

def demonstrate_tools():
    print_separator("2. ToolRegistry & Execution Demonstration")
    
    registry = ToolRegistry(workspace_path=".")
    
    @registry.register
    def format_code(filepath: str, style: str = "black") -> str:
        """
        Formats a python file using the specified style formatter (default is 'black').
        """
        return f"Formatted file {filepath} using {style} style guidelines."
        
    print("\n--- Generated Tool Schemas (for LLM Function Calling) ---")
    schemas = registry.get_tool_schemas()
    for schema in schemas:
        print(f"\nTool Name: {schema['name']}")
        print(f"Description: {schema['description']}")
        print(f"Parameters: {schema['parameters']}")
        
    print("\n--- Executing tools via Registry ---")
    print("Writing 'test_tool.txt'...")
    write_res = registry.execute(
        "write_file", 
        path="test_tool.txt", 
        content="Hello from the Autonomous IDE Kernel ToolRegistry!"
    )
    print("Result:", write_res)
    
    print("\nReading 'test_tool.txt'...")
    read_res = registry.execute("read_file", path="test_tool.txt")
    print("Content:", read_res)
    
    print("\nListing files in workspace...")
    files = registry.execute("list_files")
    print("Files found:", files)
    
    print("\nExecuting shell command 'echo Hello World'...")
    cmd_res = registry.execute("execute_shell", command="echo Hello World")
    print("Result:\n", cmd_res)
    
    print("\nRunning custom registered format_code tool...")
    fmt_res = registry.execute("format_code", filepath="kernel/tools.py")
    print("Result:", fmt_res)

    print("\n--- Demonstrating Runtime Parameter Validation ---")
    print("Attempting to execute write_file with invalid argument type (path=123, content=None)...")
    invalid_res = registry.execute("write_file", path=123, content=None)
    print("Validation Error output from ToolRegistry:\n", invalid_res)

def demonstrate_planner():
    print_separator("3. Planner Agent Node Demonstration")
    
    mock_llm = MockLLM()
    
    state: AgentState = {
        "goal": "Build an addition function in calc.py and verify it works.",
        "plan": [],
        "codebase_context": CodebaseContext(workspace_path=os.path.abspath(".")),
        "test_results": None,
        "error_log": []
    }
    
    config = {"configurable": {"llm": mock_llm}}
    node_output = planner_agent(state, config)
    state["plan"] = merge_tasks(state["plan"], node_output["plan"])
    
    print("Generated Plan:")
    for task in state["plan"]:
        print(f"  - [{task.id}] {task.description} -> [{task.status.value}]")
    return state

def demonstrate_executor(state_with_plan: AgentState):
    print_separator("4. Executor Agent Node & Self-Healing Loop")
    
    mock_llm = MockLLM()
    registry = ToolRegistry(workspace_path=".")
    
    print("Setting up 'test_calc.py' in workspace...")
    test_script_content = (
        "import calc\n"
        "def test_add():\n"
        "    assert calc.add(2, 3) == 5\n"
        "if __name__ == '__main__':\n"
        "    test_add()\n"
        "    print('Test passed successfully!')\n"
    )
    registry.write_file("test_calc.py", test_script_content)
    
    config = {
        "configurable": {
            "llm": mock_llm,
            "test_command": "python test_calc.py",
            "max_retries": 3
        }
    }
    
    print("\nInvoking executor_agent node...")
    node_output = executor_agent(state_with_plan, config)
    
    state_with_plan["plan"] = merge_tasks(state_with_plan["plan"], node_output["plan"])
    state_with_plan["error_log"] = append_errors(state_with_plan["error_log"], node_output["error_log"])
    
    print("\n--- Execution Outcome ---")
    print("Final Agent State Plan:")
    for task in state_with_plan["plan"]:
        print(f"  - [{task.id}] {task.description} -> status: [{task.status.value}]")
        if task.error_message:
            print(f"    Error: {task.error_message}")
            
    print("\nError Log Entries Recorded:")
    for err in state_with_plan["error_log"]:
        print(f"  [{err.timestamp}] Step: '{err.step}' -> {err.message}")
        print("  Traceback snippet:\n", "\n".join(err.traceback.split("\n")[:4]))

def demonstrate_compiled_graph():
    print_separator("5. Compiled StateGraph End-to-End Workflow")
    
    mock_llm = MockLLM()
    registry = ToolRegistry(workspace_path=".")
    
    # Setup test file
    print("Setting up 'test_calc.py' in workspace...")
    test_script_content = (
        "import calc\n"
        "def test_add():\n"
        "    assert calc.add(2, 3) == 5\n"
        "if __name__ == '__main__':\n"
        "    test_add()\n"
        "    print('Test passed successfully!')\n"
    )
    registry.write_file("test_calc.py", test_script_content)
    
    # Initialize the wired StateGraph workflow
    workflow = create_agent_graph()
    app = workflow.compile()
    
    # Initial state entry
    initial_state: AgentState = {
        "goal": "Build an addition function in calc.py and verify it works.",
        "plan": [],
        "codebase_context": CodebaseContext(
            workspace_path=os.path.abspath("."),
            active_files=["main.py"]
        ),
        "test_results": None,
        "error_log": []
    }
    
    config = {
        "configurable": {
            "llm": mock_llm,
            "test_command": "python test_calc.py",
            "max_retries": 3
        }
    }
    
    print("\nInvoking compiled StateGraph app...")
    final_output = app.invoke(initial_state, config)
    
    print("\n--- Compiled Graph Execution Outcome ---")
    print("Final Agent State Plan:")
    for task in final_output["plan"]:
        print(f"  - [{task.id}] {task.description} -> status: [{task.status.value}]")
        
    print("\nError Log Entries Recorded:")
    for err in final_output["error_log"]:
        print(f"  [{err.timestamp}] Step: '{err.step}' -> {err.message}")
        print("  Traceback snippet:\n", "\n".join(err.traceback.split("\n")[:4]))

if __name__ == "__main__":
    demonstrate_state()
    demonstrate_tools()
    plan_state = demonstrate_planner()
    demonstrate_executor(plan_state)
    demonstrate_compiled_graph()
