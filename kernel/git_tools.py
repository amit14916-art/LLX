import os
import time
import subprocess
from langchain_core.language_models import BaseChatModel

def _run_git_cmd(args: list, cwd: str) -> str:
    """Executes a git command and returns the stdout string."""
    try:
        res = subprocess.run(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        # Return stderr details on failure
        return f"ERROR: {e.stderr.strip()}"

def init_git_branch(workspace_path: str) -> str:
    """
    Checks if Git is initialized in the workspace (runs git init if not).
    Generates a unique branch name 'feature/agent-[timestamp]' and checks out to it.
    """
    cwd = os.path.abspath(workspace_path)
    
    # 1. Check if git repo exists
    test_repo = _run_git_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd)
    if "ERROR" in test_repo:
        print("[Git] Git repository not initialized. Initializing git...")
        _run_git_cmd(["git", "init"], cwd)
        
        # Configure local git user if not set (ensures commit succeeds in sandboxed environments)
        _run_git_cmd(["git", "config", "user.name", "Agentic Coder"], cwd)
        _run_git_cmd(["git", "config", "user.email", "agent@agentic-ide.local"], cwd)
        
        # Create initial files and commit so checking out branches works
        if not os.path.exists(os.path.join(cwd, ".gitignore")):
            with open(os.path.join(cwd, ".gitignore"), "w") as f:
                f.write(".venv/\n.lancedb/\n__pycache__/\n*.log\n")
                
        _run_git_cmd(["git", "add", ".gitignore"], cwd)
        _run_git_cmd(["git", "commit", "-m", "chore: initial workspace setup"], cwd)

    # 2. Check current status to avoid conflict, then checkout branch
    timestamp = int(time.time())
    branch_name = f"feature/agent-{timestamp}"
    
    print(f"[Git] Creating new branch: {branch_name}")
    res = _run_git_cmd(["git", "checkout", "-b", branch_name], cwd)
    
    if "ERROR" in res:
        # If it fails (e.g. branch exists or other issues), fallback to checkout
        print(f"[Git] Checkout failed, trying checkout: {res}")
        _run_git_cmd(["git", "checkout", branch_name], cwd)
        
    return branch_name

def commit_changes(workspace_path: str, goal: str, llm: BaseChatModel) -> str:
    """
    Generates a conventional commit message using the LLM based on the user goal,
    stages all files, and performs the Git commit.
    """
    cwd = os.path.abspath(workspace_path)
    
    # Generate commit message using LLM
    prompt = (
        f"You are the Git Commit Writer for an autonomous agent.\n"
        f"The agent successfully completed the goal: '{goal}'.\n"
        f"Write a short, conventional 1-line Git commit message (e.g., 'feat: add subtraction endpoint' or 'fix: calculator logic').\n"
        f"Output ONLY the commit message string, with no quotes, formatting, or extra text."
    )
    
    try:
        response = llm.invoke(prompt)
        commit_msg = response.content.strip().strip("'\"` ")
    except Exception as e:
        print(f"[Git] LLM commit message generation failed: {e}. Using default.")
        commit_msg = f"feat: implement solutions for goal '{goal}'"

    # Stage files and commit
    _run_git_cmd(["git", "add", "."], cwd)
    res = _run_git_cmd(["git", "commit", "-m", commit_msg], cwd)
    
    print(f"[Git] Changes committed: {commit_msg}")
    return commit_msg
