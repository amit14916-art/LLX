import os
import sys
import time
from unittest.mock import MagicMock
from kernel.dependency_mapper import get_dependency_graph
from kernel.retriever import ContextRetriever
from kernel.git_tools import init_git_branch, commit_changes
from kernel.critic import run_linter_check, critic_agent

def create_mock_workspace():
    """Creates mock source code files to verify indexation and dependency mapping."""
    print("[Demo] Creating mock workspace files...")
    
    # 1. Create a core utility file
    with open("mock_math_core.py", "w", encoding="utf-8") as f:
        f.write('''# Core math operations
def raw_add(x, y):
    """Raw low-level addition of two numbers."""
    return x + y

def raw_subtract(x, y):
    return x - y
''')
        
    # 2. Create a utility wrapper that imports core math operations
    with open("mock_calc_wrapper.py", "w", encoding="utf-8") as f:
        f.write('''# Calculator wrapper class
import mock_math_core

class Calculator:
    def add(self, a, b):
        # Uses low-level raw_add helper
        return mock_math_core.raw_add(a, b)
        
    def subtract(self, a, b):
        return mock_math_core.raw_subtract(a, b)
''')

    # 3. Create a test file importing wrapper
    with open("test_mock_calc.py", "w", encoding="utf-8") as f:
        f.write('''# Verification tests for mock calculator
from mock_calc_wrapper import Calculator

def test_calculator_add():
    c = Calculator()
    assert c.add(10, 5) == 15
''')

def cleanup_mock_workspace():
    """Cleans up the generated mock files."""
    print("[Demo] Cleaning up mock files...")
    for file in ["mock_math_core.py", "mock_calc_wrapper.py", "test_mock_calc.py", "buggy_syntax.py"]:
        if os.path.exists(file):
            try:
                os.remove(file)
            except Exception:
                pass

def test_dependency_mapping():
    print("\n--- 1. Testing Dependency Mapper ---")
    graph = get_dependency_graph(".")
    print(f"Dependency Graph:")
    for file, deps in graph.items():
        print(f"  {file} imports -> {deps}")
        
    assert "mock_calc_wrapper.py" in graph, "mock_calc_wrapper.py should be mapped."
    assert "mock_math_core.py" in graph["mock_calc_wrapper.py"], "mock_calc_wrapper.py must import mock_math_core.py."
    assert "mock_calc_wrapper.py" in graph["test_mock_calc.py"], "test_mock_calc.py must import mock_calc_wrapper.py."
    print("[SUCCESS] Dependency mapping validated!")

def test_retriever_indexing():
    print("\n--- 2. Testing Context Retriever Indexing ---")
    retriever = ContextRetriever(".")
    
    print("[Demo] Indexing workspace files into LanceDB...")
    retriever.index_workspace()
    
    print("[Demo] Performing semantic search for 'low-level addition'...")
    results = retriever.retrieve_context("low-level addition", limit=3)
    
    print("Semantic Search Results:")
    for idx, res in enumerate(results):
        print(f"  {idx+1}. File: {res['filepath']} (Chunk {res['chunk_idx']})")
        print(f"     Content: {res['content'].strip()}")
        
    assert len(results) > 0, "Should retrieve at least one matching snippet."
    assert any("raw_add" in r["content"] for r in results), "Should find the raw_add snippet."
    print("[SUCCESS] Context Retriever indexing & searching validated!")

def test_retriever_watchdog_update():
    print("\n--- 3. Testing Single File Re-indexing (Watchdog flow) ---")
    retriever = ContextRetriever(".")
    
    print("[Demo] Modifying mock_math_core.py to contain a new unique function...")
    with open("mock_math_core.py", "a", encoding="utf-8") as f:
        f.write("\n\ndef multiply_numbers_special(x, y):\n    return x * y\n")
        
    retriever.index_file("mock_math_core.py")
    
    print("[Demo] Searching for 'multiply_numbers_special'...")
    results = retriever.retrieve_context("multiply_numbers_special", limit=1)
    
    assert len(results) > 0, "Should retrieve the updated chunk."
    assert "multiply_numbers_special" in results[0]["content"], "Updated content not found in LanceDB search!"
    print(f"  Found matching snippet: {results[0]['content'].strip()}")
    print("[SUCCESS] File re-indexing verified successfully!")

def test_git_integration():
    print("\n--- 4. Testing Git Integration ---")
    branch = init_git_branch(".")
    print(f"[Demo] Created/Switched branch: {branch}")
    assert branch.startswith("feature/agent-"), "Branch name must start with feature/agent-"
    
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "feat: add mock addition utility"
    
    # Modify a file to ensure there is a change to commit
    with open("mock_math_core.py", "a", encoding="utf-8") as f:
        f.write("\n# Git commit verification comment\n")
        
    msg = commit_changes(".", "Mock task completion", mock_llm)
    print(f"[Demo] Created commit message: '{msg}'")
    assert len(msg) > 0, "Commit message should be returned."
    print("[SUCCESS] Git integration validated!")

def test_critic_node():
    print("\n--- 5. Testing Critic Linter & Score ---")
    # Write python code with syntax error
    with open("buggy_syntax.py", "w", encoding="utf-8") as f:
        f.write("def buggy_func(:\n    pass\n") # Syntax error!
        
    score, output = run_linter_check(".")
    print(f"[Demo] Buggy code score: {score:.2f}/10.00")
    print(f"[Demo] Linter Output:\n{output}")
    assert score < 10.0, "Score must be less than 10 for syntax errors."
    
    # Remove buggy file
    if os.path.exists("buggy_syntax.py"):
        os.remove("buggy_syntax.py")
        
    score_pass, output_pass = run_linter_check(".")
    print(f"[Demo] Clean code score: {score_pass:.2f}/10.00")
    assert score_pass == 10.0, "Score must be 10 for clean code."
    print("[SUCCESS] Critic node checks validated!")

def main():
    try:
        create_mock_workspace()
        test_dependency_mapping()
        test_retriever_indexing()
        test_retriever_watchdog_update()
        test_git_integration()
        test_critic_node()
        print("\n========================================")
        print("[SUCCESS] All indexer & orchestrator verification tests passed successfully!")
        print("========================================")
    finally:
        cleanup_mock_workspace()

if __name__ == "__main__":
    main()
