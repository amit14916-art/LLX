from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(BaseModel):
    id: str = Field(..., description="Unique identifier for the task")
    description: str = Field(..., description="Detailed description of what needs to be done")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution status of the task")
    error_message: Optional[str] = Field(default=None, description="Error message if the task failed")

class CodebaseContext(BaseModel):
    workspace_path: str = Field(..., description="Absolute path to the workspace directory")
    active_files: List[str] = Field(default_factory=list, description="List of files currently open or active in the workspace")
    summary: Optional[str] = Field(default=None, description="High-level structural or architectural summary of the codebase")
    dependency_graph: Dict[str, List[str]] = Field(default_factory=dict, description="File-to-file import dependency graph mapping")

class TestResults(BaseModel):
    passed: int = Field(default=0, description="Number of passing tests")
    failed: int = Field(default=0, description="Number of failing tests")
    errors: int = Field(default=0, description="Number of tests that encountered unexpected errors")
    raw_output: str = Field(default="", description="Raw stdout/stderr output from the test runner")

class ErrorEntry(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp of the error occurrence")
    step: str = Field(..., description="The step, agent node, or tool execution where the error occurred")
    message: str = Field(..., description="The error message description")
    traceback: Optional[str] = Field(default=None, description="Optional traceback detailing the error root cause")
