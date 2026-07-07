import os
from kernel.tools import ToolRegistry
from kernel.planner import create_planner_node
from kernel.state import AgentState
from kernel.models import CodebaseContext

class MockChatModel:
    """Mock LLM to bypass remote queries."""
    def with_structured_output(self, schema, **kwargs):
        class MockStructured:
            def invoke(self, prompt, config=None):
                from kernel.planner import PlanOutput
                from kernel.models import Task
                print(f"\n[Planner LLM Received Prompt]:\n{prompt}\n")
                return PlanOutput(tasks=[
                    Task(id="T01", description="Verify dynamic skills in system prompt", status="pending")
                ])
        return MockStructured()

def main():
    workspace_path = os.path.abspath(".")
    
    print("[Test] Initializing ToolRegistry (scans skills/ directory)...")
    registry = ToolRegistry(workspace_path)
    
    # ----------------------------------------------------
    # Verification 1: Dynamic Loading Discovery
    # ----------------------------------------------------
    assert "mock_refactor_skill" in registry.skills, "Registry must dynamically discover and load mock_refactor_skill."
    print("[SUCCESS] Found dynamically loaded skill: mock_refactor_skill.")
    
    # ----------------------------------------------------
    # Verification 2: Schema Extraction
    # ----------------------------------------------------
    schemas = registry.get_skills_schemas()
    assert len(schemas) == 1, "Should retrieve exactly one skill schema."
    assert schemas[0]["name"] == "mock_refactor_skill", "Schema name must match the skill module name."
    assert "target_file" in schemas[0]["parameters"]["properties"], "Schema parameters must match get_schema structure."
    print(f"[SUCCESS] Extracted Skill Schema: {schemas[0]}")
    
    # ----------------------------------------------------
    # Verification 3: Safety Sandboxing Execution
    # ----------------------------------------------------
    print("\n--- STEP 3: Executing dynamic skill in restricted sandbox ---")
    state: AgentState = {
        "goal": "Refactor codebase modules",
        "plan": [],
        "codebase_context": CodebaseContext(workspace_path=workspace_path, active_files=[]),
        "test_results": None,
        "error_log": [],
        "git_branch": None,
        "current_lint_score": 1.0,
        "critic_status": None,
        "last_active_worker": None,
        "current_task_id": None
    }
    
    # Execute skill
    delta = registry.execute_skill("mock_refactor_skill", state)
    print(f"[Test] Sandbox Execution Return Delta: {delta}")
    
    # Validate delta returns expected outputs
    assert delta["critic_status"] == "SKILL_VERIFIED"
    assert delta["current_lint_score"] == 9.95
    
    # Validate safety isolation: Original state properties must NOT be mutated
    assert state["current_lint_score"] == 1.0, "Sandbox error: Original state was mutated!"
    assert state["critic_status"] is None, "Sandbox error: Original state was mutated!"
    print("[SUCCESS] Safety Sandbox verified: execution isolated, original state protected.")
    
    # ----------------------------------------------------
    # Verification 4: Planner Discovery Prompt Injection
    # ----------------------------------------------------
    print("\n--- STEP 4: Verifying Planner Prompt Skill Discovery ---")
    planner = create_planner_node(MockChatModel())
    planner(state)
    
    print("[SUCCESS] Modular Plugin Architecture E2E validation completed successfully!")

if __name__ == "__main__":
    main()
