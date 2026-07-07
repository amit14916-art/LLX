import os
import json
import httpx
import subprocess
from app import app
from fastapi.testclient import TestClient

def main():
    workspace_path = os.path.abspath(".")
    
    # ----------------------------------------------------
    # Verification 1: Self-Update API Endpoints
    # ----------------------------------------------------
    print("[Test] Verifying backend self-update endpoints...")
    client = TestClient(app)
    
    # Reset version.json to 1.0.0
    version_file = os.path.join(workspace_path, "version.json")
    with open(version_file, "w", encoding="utf-8") as f:
        json.dump({"version": "1.0.0"}, f)
        
    # GET /version
    resp = client.get("/version")
    assert resp.status_code == 200
    data = resp.json()
    print(f"[Test] GET /version: {data}")
    assert data["local_version"] == "1.0.0"
    assert data["latest_version"] == "1.1.0"
    assert data["update_available"] is True
    
    # POST /update
    update_resp = client.post("/update")
    assert update_resp.status_code == 200
    update_data = update_resp.json()
    print(f"[Test] POST /update response: {update_data}")
    assert update_data["status"] == "success"
    
    # GET /version again (should be updated now)
    resp2 = client.get("/version")
    data2 = resp2.json()
    print(f"[Test] GET /version post-update: {data2}")
    assert data2["local_version"] == "1.1.0"
    assert data2["update_available"] is False
    print("[SUCCESS] Backend self-update API verified.")
    
    # ----------------------------------------------------
    # Verification 2: Extension Configuration and Startup
    # ----------------------------------------------------
    print("\n[Test] Verifying extension package.json configuration schema...")
    pkg_file = os.path.join(workspace_path, "extension", "package.json")
    with open(pkg_file, "r", encoding="utf-8") as f:
        pkg_data = json.load(f)
        
    configs = pkg_data.get("contributes", {}).get("configuration", {}).get("properties", {})
    assert "agenticIde.openaiApiKey" in configs, "Missing openaiApiKey config."
    assert "agenticIde.modelPreference" in configs, "Missing modelPreference config."
    assert "agenticIde.serverPort" in configs, "Missing serverPort config."
    print("[SUCCESS] extension/package.json contains all required settings.json schema options.")

    # ----------------------------------------------------
    # Verification 3: Build Automation compilation
    # ----------------------------------------------------
    print("\n[Test] Executing build.py compiler and packager script...")
    res = subprocess.run(
        [os.path.join(workspace_path, ".venv", "Scripts", "python.exe"), "build.py"],
        cwd=workspace_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"[Build Output]:\n{res.stdout}")
    if res.stderr:
        print(f"[Build Errors/Warnings]:\n{res.stderr}")
        
    # Check if compiled code or copied files exist
    ext_kernel = os.path.join(workspace_path, "extension", "kernel")
    ext_skills = os.path.join(workspace_path, "extension", "skills")
    assert os.path.exists(ext_kernel), "Kernel must be bundled into extension."
    assert os.path.exists(ext_skills), "Skills must be bundled into extension."
    
    print("\n[SUCCESS] Build packaging and self-updating verified successfully!")

if __name__ == "__main__":
    main()
