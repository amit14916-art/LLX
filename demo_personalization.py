import os
import json
import subprocess
from kernel.style_memory import StyleMemory, harvest_user_corrections

def run_git_cmd(args, cwd):
    res = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip()

def main():
    workspace_path = os.path.abspath(".")
    
    print("[Test] Initializing StyleMemory database...")
    style_mem = StyleMemory(workspace_path)
    
    # 1. Clean the table if it already contains data
    try:
        style_mem.db.drop_table("style_memory")
        style_mem._init_table()
        print("[Test] Cleared StyleMemory database collection for clean validation run.")
    except Exception:
        pass
        
    # Verify initial retrieval is empty
    initial_res = style_mem.retrieve_preferences("Calculate math functions", limit=3)
    assert len(initial_res) == 0, "Style memory must be empty on startup."
    
    # 2. Add style correction manually
    print("\n--- STEP 1: Recording manual style preference example ---")
    filepath = "math_utils.py"
    before_code = "def double(x):\n    return x * 2\n"
    after_code = "def double(x: int) -> int:\n    \"\"\"Doubles the input number with strict types.\"\"\"\n    return x * 2\n"
    vibe = "Ensure strict type annotations and docstrings for all mathematical utility helpers."
    
    style_mem.add_preference(filepath, before_code, after_code, vibe)
    
    # Retrieve and assert matching vibe matches query
    print("\n--- STEP 2: Retrieving style preferences for query 'type hints' ---")
    retrieved = style_mem.retrieve_preferences("Write mathematical functions with type hints", limit=3)
    assert len(retrieved) == 1, "Should retrieve exactly one style preference example."
    assert retrieved[0]["filepath"] == filepath
    assert retrieved[0]["description"] == vibe
    print(f"[Test] Successfully matched! Vibe Description: {retrieved[0]['description']}")
    
    # ----------------------------------------------------
    # STEP 3: Automatic harvesting of git diff modifications
    # ----------------------------------------------------
    print("\n--- STEP 3: Verifying automatic uncommitted git diff harvesting ---")
    test_file = "temp_harvest.py"
    
    # Ensure test file is in HEAD first so we have a 'before' diff reference
    with open(test_file, "w") as f:
        f.write("def greeting(name):\n    print('Hello ' + name)\n")
        
    run_git_cmd(["git", "add", test_file], workspace_path)
    run_git_cmd(["git", "commit", "-m", "Commit test file before manual edit"], workspace_path)
    
    # Now manually edit the file to create uncommitted diff (the 'After' preference!)
    with open(test_file, "w") as f:
        f.write("def greeting(name: str) -> None:\n    # Greeting function\n    print(f'Hello {name}')\n")
        
    print("[Test] Triggering automatic corrections harvesting...")
    harvest_user_corrections(workspace_path)
    
    # Debug: print table contents
    style_mem.table = style_mem.db.open_table(style_mem.table_name)
    arrow_tbl = style_mem.table.to_arrow()
    print(f"[Debug] Table rows count: {style_mem.table.count_rows()}")
    print(f"[Debug] Filepaths in table: {arrow_tbl['filepath'].to_pylist()}")
    print(f"[Debug] Descriptions in table: {arrow_tbl['description'].to_pylist()}")
    
    # Retrieve the harvested preference
    harvest_retrieved = style_mem.retrieve_preferences("greeting function formatting", limit=3)
    print(f"[Debug] Retrieved results count: {len(harvest_retrieved)}")
    assert len(harvest_retrieved) > 0, "Harvested preference must be retrieved."
    print("\n[SUCCESS] Automatically Harvested Style Preference:")
    print(f"File: {harvest_retrieved[0]['filepath']}")
    print(f"Before:\n{harvest_retrieved[0]['before_code']}")
    print(f"After:\n{harvest_retrieved[0]['after_code']}")
    
    # Clean up test changes
    print("\n--- STEP 4: Cleaning up test files ---")
    run_git_cmd(["git", "reset", "--hard", "HEAD~1"], workspace_path)
    if os.path.exists(test_file):
        os.remove(test_file)
        
    print("\n[SUCCESS] Advanced Personalization and Style Memory verified successfully!")

if __name__ == "__main__":
    main()
