import os
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Type, Any
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage, BaseMessage

from kernel.models import Task, TaskStatus, CodebaseContext, TestResults, ErrorEntry
from kernel.state import merge_tasks, append_errors, AgentState
from kernel.graph import create_agent_graph

app = FastAPI(title="Agentic IDE Kernel API", version="1.0.0")

# Configure CORS to allow local VS Code extension or web interfaces to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this to specific VS Code schemes or localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reference to the main asyncio loop for dispatching websocket logs from agent threads
main_loop = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

# ----------------------------------------------------
# WebSocket Connection Manager for logs
# ----------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        # Format as timestamped log line
        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        for connection in self.active_connections:
            try:
                await connection.send_text(log_line)
            except Exception:
                pass

manager = ConnectionManager()

class TelemetryManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, event: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(event)
            except Exception:
                pass

telemetry_manager = TelemetryManager()

# ----------------------------------------------------
# Mock LLM fallback for local testability without API keys
# ----------------------------------------------------
class MockStructuredLLM:
    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema
        
    def invoke(self, prompt: str, config: Optional[Any] = None) -> Any:
        if self.schema.__name__ == "PlanOutput":
            from kernel.planner import PlanOutput
            return PlanOutput(tasks=[
                Task(id="T01", description="Implement a calculator add function in calc.py", status=TaskStatus.PENDING),
                Task(id="T02", description="Write and run unit tests for the calculator add function in test_calc.py", status=TaskStatus.PENDING),
                Task(id="T03", description="Run a codebase security scanning validation", status=TaskStatus.PENDING)
            ])
        raise ValueError(f"Mock model does not support schema: {self.schema.__name__}")

class MockLLM(BaseChatModel):
    """Fallback Mock ChatModel to run backend out-of-the-box."""
    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        # Determine which agent is calling the mock LLM
        is_tester = False
        is_coder = False
        
        for msg in messages:
            content_str = str(getattr(msg, "content", ""))
            if "Tester Worker" in content_str:
                is_tester = True
            elif "Coder Worker" in content_str:
                is_coder = True
                
        # 1. Tester Agent tool output
        if is_tester:
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "test_calc.py",
                    "content": "from calc import add\ndef test_add():\n    assert add(2, 3) == 5\n"
                },
                "id": "call_write_test"
            }]
            ai_msg = AIMessage(
                content="I will write the unit tests for add function in test_calc.py.",
                tool_calls=tool_calls
            )
            return ChatResult(generations=[ChatGeneration(message=ai_msg)])
            
        # 2. Coder Agent tool output
        is_healing_attempt = False
        for msg in reversed(messages):
            content_str = str(getattr(msg, "content", ""))
            if "Exit Code" in content_str or "failed" in content_str:
                is_healing_attempt = True
                break
                
        if is_healing_attempt:
            # Correct the bug
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "calc.py",
                    "content": "def add(a, b):\n    return a + b  # Corrected implementation\n"
                },
                "id": "call_fix_999"
            }]
            ai_msg = AIMessage(
                content="I see the tests failed. I will write the corrected addition logic to calc.py.",
                tool_calls=tool_calls
            )
        else:
            # Write initial buggy implementation
            tool_calls = [{
                "name": "write_file",
                "args": {
                    "path": "calc.py",
                    "content": "def add(a, b):\n    return a - b  # Buggy implementation\n"
                },
                "id": "call_write_888"
            }]
            ai_msg = AIMessage(
                content="I will write the initial calc.py addition function.",
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

def get_chat_model() -> BaseChatModel:
    """
    Initializes a real LangChain ChatModel if API keys are set,
    otherwise falls back to the MockLLM for local testing.
    """
    if os.environ.get("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.1)
    elif os.environ.get("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-3-5-sonnet-latest", temperature=0.1)
    else:
        # Fallback to local mock runner
        return MockLLM()

# ----------------------------------------------------
# API Endpoint Models & Routing
# ----------------------------------------------------
class GoalRequest(BaseModel):
    goal: str
    workspace_path: Optional[str] = None
    test_command: Optional[str] = "python test_calc.py"

@app.post("/execute")
async def execute_goal(request: GoalRequest):
    """
    POST endpoint to initialize and stream LangGraph agent execution.
    Sends Server-Sent Events (SSE) back to the client.
    """
    # Use current directory if no workspace path is specified
    workspace_path = request.workspace_path or os.path.abspath(".")
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=400, detail=f"Workspace path does not exist: {workspace_path}")
        
    # Compile graph
    graph = create_agent_graph().compile()
    
    # Initialize state
    state: AgentState = {
        "goal": request.goal,
        "plan": [],
        "codebase_context": CodebaseContext(
            workspace_path=os.path.abspath(workspace_path),
            active_files=[]
        ),
        "test_results": None,
        "error_log": [],
        "git_branch": None,
        "current_lint_score": None
    }
    
    # Define WebSocket broadcast callback for graph logging
    def log_callback(msg: str):
        if main_loop:
            asyncio.run_coroutine_threadsafe(manager.broadcast(msg), main_loop)
            
    # Define WebSocket broadcast callback for telemetry metrics
    def telemetry_callback(event: dict):
        if main_loop:
            asyncio.run_coroutine_threadsafe(telemetry_manager.broadcast(event), main_loop)
            
    # Setup configuration
    config = {
        "configurable": {
            "llm": get_chat_model(),
            "test_command": request.test_command,
            "max_retries": 3,
            "log_callback": log_callback,
            "telemetry_callback": telemetry_callback
        }
    }
    
    async def event_generator():
        # Stream the nodes execution asynchronously
        async for chunk in graph.astream(state, config):
            # Parse state data chunk (e.g. {"planner": {...}} or {"executor": {...}})
            # Normalize tasks/errors to be JSON serializable
            serializable_chunk = {}
            for node, val in chunk.items():
                node_data = {}
                if "plan" in val:
                    node_data["plan"] = [task.dict() for task in val["plan"]]
                if "error_log" in val:
                    node_data["error_log"] = [err.dict() for err in val["error_log"]]
                if "goal" in val:
                    node_data["goal"] = val["goal"]
                if "git_branch" in val:
                    node_data["git_branch"] = val["git_branch"]
                if "current_lint_score" in val:
                    node_data["current_lint_score"] = val["current_lint_score"]
                if "critic_status" in val:
                    node_data["critic_status"] = val["critic_status"]
                if "current_task_id" in val:
                    node_data["current_task_id"] = val["current_task_id"]
                serializable_chunk[node] = node_data
                
            yield f"data: {json.dumps(serializable_chunk)}\n\n"
            await asyncio.sleep(0.1) # brief yield
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint to stream real-time execution logs back to client.
    """
    await manager.connect(websocket)
    try:
        # Keep connection open and wait for client to close it
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

@app.websocket("/metrics")
async def telemetry_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint to stream real-time JSON telemetry metrics back to client.
    """
    await telemetry_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_manager.disconnect(websocket)
    except Exception:
        telemetry_manager.disconnect(websocket)
