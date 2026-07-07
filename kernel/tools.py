import os
import subprocess
import inspect
import importlib.util
import sys
from datetime import datetime
from typing import Callable, Dict, Any, List
from pydantic import create_model, validate_call

class ToolRegistry:
    """
    A registry for managing and executing tools used by the autonomous agentic IDE.
    Each tool is validated using Pydantic at runtime and generates schemas automatically.
    Dynamically loads custom user plugins (Skills) at startup.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.tools: Dict[str, Callable] = {}
        self.skills: Dict[str, Any] = {}
        
        # Automatically register default IDE tools
        self.register(self.read_file)
        self.register(self.write_file)
        self.register(self.execute_shell)
        self.register(self.list_files)
        
        # Dynamically discover and load modular skills
        self._load_dynamic_skills()

    def register(self, func: Callable) -> Callable:
        """Registers a function/method as a tool. Enforces Pydantic validation at runtime."""
        validated_func = validate_call(func)
        self.tools[func.__name__] = validated_func
        return validated_func

    def _load_dynamic_skills(self):
        """Scans the /skills directory and dynamically loads Python plugins at startup."""
        skills_dir = os.path.join(self.workspace_path, "skills")
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir, exist_ok=True)
            return

        # Ensure the skills directory is on path for absolute imports
        if skills_dir not in sys.path:
            sys.path.insert(0, skills_dir)

        for file in os.listdir(skills_dir):
            if file.endswith(".py") and file != "__init__.py":
                module_name = file[:-3]
                file_path = os.path.join(skills_dir, file)
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    from kernel.skills import BaseSkill
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseSkill)
                            and attr is not BaseSkill
                        ):
                            # Instantiate and register the skill plugin
                            skill_instance = attr()
                            self.skills[module_name] = skill_instance
                            print(f"[ToolRegistry] Dynamically loaded modular skill: {module_name}")
                except Exception as e:
                    print(f"[ToolRegistry] Error loading skill from {file}: {e}")

    def get_skills_schemas(self) -> List[Dict[str, Any]]:
        """Returns LLM-compatible schemas for all dynamically loaded skill plugins."""
        schemas = []
        for name, skill in self.skills.items():
            try:
                schema = skill.get_schema()
                # Ensure name matches the module file name for consistent execution
                schema["name"] = name
                schemas.append(schema)
            except Exception as e:
                print(f"[ToolRegistry] Failed to get schema for skill '{name}': {e}")
        return schemas

    def execute_skill(self, name: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a dynamic skill plugin inside a restricted sandboxed scope.
        The skill is passed a copy of the state and has no access to global parameters.
        """
        if name not in self.skills:
            raise ValueError(f"Dynamic skill '{name}' is not registered.")
            
        skill = self.skills[name]
        
        # Sandbox: Construct isolated state scope copy
        sandboxed_state = {
            "goal": state.get("goal"),
            "plan": [t.dict() if hasattr(t, "dict") else t for t in state.get("plan", [])],
            "codebase_context": state.get("codebase_context"),
            "test_results": state.get("test_results"),
            "error_log": state.get("error_log"),
            "git_branch": state.get("git_branch"),
            "current_lint_score": state.get("current_lint_score"),
            "critic_status": state.get("critic_status")
        }
        
        try:
            # Execute skill and return delta updates
            delta = skill.execute(sandboxed_state)
            if not isinstance(delta, dict):
                raise TypeError(f"Skill '{name}' execute must return a dictionary of state updates.")
            return delta
        except Exception as e:
            print(f"[ToolRegistry] Error running skill '{name}': {e}")
            from kernel.models import ErrorEntry
            err = ErrorEntry(
                timestamp=datetime.utcnow().isoformat(),
                step=f"skill:{name}",
                message=f"Sandbox error executing skill '{name}': {e}",
                traceback=""
            )
            return {"error_log": [err]}

    def execute(self, name: str, **kwargs) -> Any:
        """Executes a registered tool by its name. Enforces argument types and validations."""
        if name not in self.tools:
            return f"Error: Tool '{name}' is not registered."
        try:
            return self.tools[name](**kwargs)
        except Exception as e:
            return f"Error executing tool '{name}': {str(e)}"

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Generates json schemas for all registered tools, compatible with LLM function schemas."""
        schemas = []
        for name, func in self.tools.items():
            orig_func = getattr(func, "__wrapped__", func)
            sig = inspect.signature(orig_func)
            
            fields = {}
            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                
                param_type = param.annotation if param.annotation != inspect.Parameter.empty else Any
                if param.default == inspect.Parameter.empty:
                    fields[param_name] = (param_type, ...)
                else:
                    fields[param_name] = (param_type, param.default)
            
            arg_model = create_model(f"{name}_args", **fields)
            json_schema = arg_model.model_json_schema()
            json_schema.pop("title", None)
            
            schemas.append({
                "name": name,
                "description": orig_func.__doc__.strip() if orig_func.__doc__ else f"Run {name} tool",
                "parameters": json_schema
            })
        return schemas

    def _resolve_path(self, path: str) -> str:
        """Resolves path and enforces workspace directory boundary checks."""
        resolved = os.path.abspath(os.path.join(self.workspace_path, path))
        if not resolved.startswith(self.workspace_path):
            raise ValueError(f"Access Denied: Path '{path}' resolves outside workspace boundary.")
        return resolved

    def read_file(self, path: str) -> str:
        """Reads the full content of a file located inside the workspace."""
        resolved_path = self._resolve_path(path)
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"File not found at path: {path}")
        if os.path.isdir(resolved_path):
            raise IsADirectoryError(f"Target path '{path}' is a directory.")
        
        with open(resolved_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        """Writes string content to a file. Creates parent directories as needed."""
        resolved_path = self._resolve_path(path)
        parent_dir = os.path.dirname(resolved_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
            
        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to file '{path}'"

    def execute_shell(self, command: str) -> str:
        """Runs a shell command inside the workspace folder."""
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
        """Recursively lists all files in the workspace, excluding virtual environment (.venv)."""
        exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", "kernel.egg-info"}
        file_list = []
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.workspace_path)
                file_list.append(rel_path.replace("\\", "/"))
        return file_list
