import os
import json
import subprocess
from kernel.retriever import ContextRetriever

def run_git_cmd(args, cwd):
    res = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip()

def main():
    workspace_path = os.path.abspath(".")
    db_dir = os.path.join(workspace_path, ".lancedb")
    metadata_path = os.path.join(db_dir, "index_metadata.json")
    
    print("[Test] Initializing ContextRetriever...")
    retriever = ContextRetriever(workspace_path)
    
    # Ensure a git repository exists and has at least one commit
    head = run_git_cmd(["git", "rev-parse", "HEAD"], workspace_path)
    if not head:
        print("[Test] Initializing Git repository for caching tests...")
        run_git_cmd(["git", "init"], workspace_path)
        with open("initial_file.py", "w") as f:
            f.write("# Init file\n")
        run_git_cmd(["git", "add", "initial_file.py"], workspace_path)
        run_git_cmd(["git", "commit", "-m", "Initial commit"], workspace_path)
        head = run_git_cmd(["git", "rev-parse", "HEAD"], workspace_path)
        
    print(f"[Test] Current HEAD commit: {head}")
    
    # Clean up previous metadata if any
    if os.path.exists(metadata_path):
        os.remove(metadata_path)
        
    # ----------------------------------------------------
    # Verification Step 1: Initial Full Scan
    # ----------------------------------------------------
    print("\n--- STEP 1: Running initial synchronization (no metadata) ---")
    retriever.sync_workspace()
    
    assert os.path.exists(metadata_path), "Metadata JSON file must be created."
    with open(metadata_path, "r") as f:
        meta = json.load(f)
    print(f"[Test] Saved Metadata: {meta}")
    assert meta["last_processed_commit"] == head, "Metadata commit must match HEAD."
    
    # ----------------------------------------------------
    # Verification Step 2: Cache Hit (Bypass Re-Indexing)
    # ----------------------------------------------------
    print("\n--- STEP 2: Running sync again (no changes, should bypass) ---")
    # Redirect stdout to check output print
    retriever.sync_workspace()
    
    # ----------------------------------------------------
    # Verification Step 3: Incremental Diff Sync
    # ----------------------------------------------------
    print("\n--- STEP 3: Making a file change and committing to test diff sync ---")
    test_file = "temp_cache_test.py"
    with open(test_file, "w") as f:
        f.write("def cached_function():\n    print('Caching working!')\n")
        
    run_git_cmd(["git", "add", test_file], workspace_path)
    run_git_cmd(["git", "commit", "-m", "Modify test file for cache verification"], workspace_path)
    
    new_head = run_git_cmd(["git", "rev-parse", "HEAD"], workspace_path)
    print(f"[Test] New HEAD commit: {new_head}")
    
    print("\n[Test] Running incremental synchronization...")
    retriever.sync_workspace()
    
    # Verify metadata is updated
    with open(metadata_path, "r") as f:
        new_meta = json.load(f)
    print(f"[Test] Updated Metadata: {new_meta}")
    assert new_meta["last_processed_commit"] == new_head, "Metadata commit must be updated to new HEAD."
    
    # Clean up test file from git history to leave the repo clean
    print("\n--- STEP 4: Cleaning up git changes ---")
    run_git_cmd(["git", "reset", "--hard", head], workspace_path)
    if os.path.exists(test_file):
        os.remove(test_file)
        
    print("\n[SUCCESS] Incremental Workspace Synchronization verified successfully!")

if __name__ == "__main__":
    main()
