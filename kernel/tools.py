import os
import subprocess
import inspect
from typing import Callable, Dict, Any, List
from pydantic import create_model, validate_call

class ToolRegistry:
    """
    A registry for managing and executing tools used by the autonomous agentic IDE.
    Each tool is validated using Pydantic at runtime and generates schemas automatically.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.tools: Dict[str, Callable] = {}
        
        # Automatically register default IDE tools
        self.register(self.read_file)
        self.register(self.write_file)
        self.register(self.execute_shell)
        self.register(self.list_files)

    def register(self, func: Callable) -> Callable:
        """
        Registers a function/method as a tool. Enforces Pydantic validation at runtime.
        """
        validated_func = validate_call(func)
        self.tools[func.__name__] = validated_func
        return validated_func

    def execute(self, name: str, **kwargs) -> Any:
        """
        Executes a registered tool by its name. Enforces argument types and validations.
        """
        if name not in self.tools:
            return f"Error: Tool '{name}' is not registered."
        try:
            return self.tools[name](**kwargs)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """
        Generates json schemas for all registered tools, compatible with LLM function schemas.
        Uses Pydantic's create_model to extract argument properties dynamically.
        """
        schemas = []
        for name, func in self.tools.items():
            # Extract unwrapped original function
            orig_func = getattr(func, "__wrapped__", func)
            sig = inspect.signature(orig_func)
            
            # Map parameters to Pydantic dynamic fields
            fields = {}
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                
                param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
                if param.default == inspect.Parameter.empty:
                    fields[param_name] = (param_type, ...)
                else:
                    fields[param_name] = (param_type, param.default)
            
            # Create a dynamic Pydantic BaseModel to derive the schema
            arg_model = create_model(f"{name}_args", **fields)
            json_schema = arg_model.model_json_schema()
            
            # Remove title to keep schema clean for LLM consumption
            json_schema.pop("title", None)
            
            schemas.append({
                "name": name,
                "description": orig_func.__doc__.strip() if orig_func.__doc__ else f"Run {name} tool",
                "parameters": json_schema
            })
        return schemas

    def _resolve_path(self, path: str) -> str:
        """
        Resolves a relative file path to the workspace root.
        Secures path to prevent directory traversal outside the workspace.
        """
        resolved = os.path.abspath(os.path.join(self.workspace_path, path))
        if not resolved.startswith(self.workspace_path):
            raise ValueError(f"Access Denied: Path '{path}' resolves outside workspace boundary.")
        return resolved

    def read_file(self, path: str) -> str:
        """
        Reads the full content of a file located inside the workspace.
        """
        resolved_path = self._resolve_path(path)
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"File not found at path: {path}")
        if os.path.isdir(resolved_path):
            raise IsADirectoryError(f"Target path '{path}' is a directory.")
        
        with open(resolved_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        """
        Writes string content to a file at the specified workspace path.
        Creates any parent directories as needed.
        """
        resolved_path = self._resolve_path(path)
        parent_dir = os.path.dirname(resolved_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to file '{path}'"

    def execute_shell(self, command: str) -> str:
        """
        Runs a shell command inside the workspace folder.
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            output = []
            if result.stdout:
                output.append(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                output.append(f"STDERR:\n{result.stderr}")
            combined = "\n".join(output) if output else "Command completed with no output."
            return f"{combined}\n[Exit Code: {result.returncode}]"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds.\n[Exit Code: -1]"
        except Exception as e:
            return f"Error executing shell command: {str(e)}\n[Exit Code: -2]"

    def list_files(self) -> List[str]:
        """
        Recursively lists all files in the workspace, excluding virtual environment (.venv)
        and Git control files.
        """
        exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", "kernel.egg-info"}
        file_list = []
        for root, dirs, files in os.walk(self.workspace_path):
            # Prune directories in-place to skip excluded paths
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.workspace_path)
                file_list.append(rel_path.replace("\\", "/"))
        return file_list
