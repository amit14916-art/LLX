import os
import ast
import re
from typing import Dict, List

class PythonImportCollector(ast.NodeVisitor):
    """AST visitor to gather all imports in a Python file."""
    def __init__(self):
        self.imports = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.append(node.module)

def parse_python_imports(filepath: str) -> List[str]:
    """Parses a Python file and returns a list of imported module names."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=filepath)
        collector = PythonImportCollector()
        collector.visit(tree)
        return collector.imports
    except Exception:
        return []

def parse_js_ts_imports(filepath: str) -> List[str]:
    """Uses regular expressions to extract module imports from JS/TS/TSX files."""
    imports = []
    import_patterns = [
        r'\bimport\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
        r'\bimport\s+[\'"]([^\'"]+)[\'"]',
        r'\brequire\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
        r'\bexport\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]'
    ]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        for pattern in import_patterns:
            matches = re.findall(pattern, content)
            imports.extend(matches)
        return list(set(imports))
    except Exception:
        return []

def get_dependency_graph(workspace_path: str) -> Dict[str, List[str]]:
    """
    Scans the workspace for code files and parses imports.
    Resolves imports against workspace files to build a local file dependency graph.
    """
    workspace_path = os.path.abspath(workspace_path)
    exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", "node_modules", ".lancedb"}
    graph = {}
    
    # First, list all code files in the workspace (with relative paths)
    all_workspace_files = set()
    for root, dirs, files in os.walk(workspace_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in {".py", ".js", ".ts", ".tsx"}:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, workspace_path).replace("\\", "/")
                all_workspace_files.add(rel_path)

    # Now, parse imports for each code file and resolve them
    for rel_file in all_workspace_files:
        full_path = os.path.join(workspace_path, rel_file)
        ext = os.path.splitext(rel_file)[1].lower()
        
        if ext == ".py":
            raw_imports = parse_python_imports(full_path)
        else:
            raw_imports = parse_js_ts_imports(full_path)
            
        resolved_imports = []
        for imp in raw_imports:
            # Normalize python modules (e.g. 'kernel.models' -> 'kernel/models')
            path_format = imp.replace(".", "/")
            
            # Form potential candidate filepaths relative to workspace
            candidates = [
                path_format,
                path_format + ".py",
                path_format + ".ts",
                path_format + ".js",
                path_format + ".tsx",
                # Support relative paths (e.g., './models' -> 'kernel/models')
                os.path.normpath(os.path.join(os.path.dirname(rel_file), path_format)).replace("\\", "/")
            ]
            
            # Check if any candidate is a local file
            for cand in candidates:
                # Append extension combinations
                for suffix in ["", ".py", ".ts", ".js", ".tsx"]:
                    full_cand = cand + suffix if suffix else cand
                    # Normalize CAND relative path
                    norm_cand = os.path.normpath(full_cand).replace("\\", "/")
                    if norm_cand in all_workspace_files and norm_cand != rel_file:
                        resolved_imports.append(norm_cand)
                        break
                else:
                    continue
                break
                
        graph[rel_file] = list(set(resolved_imports))
        
    return graph
