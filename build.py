import os
import subprocess
import shutil
import sys

def main():
    workspace_dir = os.path.abspath(".")
    extension_dir = os.path.join(workspace_dir, "extension")
    
    print("[Build] Bundling Python kernel and skills into extension bundle...")
    ext_kernel_dir = os.path.join(extension_dir, "kernel")
    ext_skills_dir = os.path.join(extension_dir, "skills")
    
    if os.path.exists(ext_kernel_dir):
        shutil.rmtree(ext_kernel_dir)
    if os.path.exists(ext_skills_dir):
        shutil.rmtree(ext_skills_dir)
        
    shutil.copytree(os.path.join(workspace_dir, "kernel"), ext_kernel_dir)
    shutil.copytree(os.path.join(workspace_dir, "skills"), ext_skills_dir)
    
    print("[Build] Installing npm dependencies in extension/...")
    subprocess.run(["npm", "install"], cwd=extension_dir, shell=True, check=True)
    
    print("[Build] Compiling extension TypeScript source...")
    subprocess.run(["npm", "run", "compile"], cwd=extension_dir, shell=True, check=True)
    
    print("[Build] Packaging extension to .vsix using vsce package...")
    # Use npx @vscode/vsce to bundle and package without requiring global installations
    res = subprocess.run(
        ["npx", "@vscode/vsce", "package", "--no-dependencies", "-o", "../agentic-ide-1.0.0.vsix"], 
        cwd=extension_dir, 
        shell=True
    )
    if res.returncode == 0:
        print("[Build] SUCCESS: VS Code extension package created: agentic-ide-1.0.0.vsix")
    else:
        print("[Build] Warning: vsce packaging failed. Check package.json details.")

if __name__ == "__main__":
    main()
