import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { exec } from 'child_process';
import { AgenticIdeWebviewProvider } from './AgenticIdeWebviewProvider';

export function activate(context: vscode.ExtensionContext) {
    console.log('Agentic IDE Extension is now active.');

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
        const workspaceRoot = workspaceFolders[0].uri.fsPath;
        setupVirtualEnvironment(workspaceRoot);
    }

    const provider = new AgenticIdeWebviewProvider(context.extensionUri);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            AgenticIdeWebviewProvider.viewType,
            provider
        )
    );
}

function setupVirtualEnvironment(workspaceRoot: string) {
    const venvPath = path.join(workspaceRoot, '.venv');
    const requirementsPath = path.join(workspaceRoot, 'requirements.txt');

    // Skip if virtual environment is already present
    if (fs.existsSync(venvPath)) {
        console.log('[Agentic IDE] Local virtual environment (.venv) already exists.');
        return;
    }

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "Agentic IDE: Initializing Python environment...",
        cancellable: false
    }, (progress) => {
        return new Promise<void>((resolve, reject) => {
            progress.report({ message: "Creating virtual environment (.venv)..." });
            
            exec('python -m venv .venv', { cwd: workspaceRoot }, (err) => {
                if (err) {
                    vscode.window.showErrorMessage(`Failed to create .venv: ${err.message}`);
                    reject(err);
                    return;
                }
                
                progress.report({ message: "Installing requirements.txt dependencies..." });
                
                const pipExec = process.platform === 'win32'
                    ? path.join(venvPath, 'Scripts', 'pip.exe')
                    : path.join(venvPath, 'bin', 'pip');
                    
                exec(`"${pipExec}" install -r "${requirementsPath}"`, { cwd: workspaceRoot }, (pipErr) => {
                    if (pipErr) {
                        vscode.window.showErrorMessage(`Failed to install requirements: ${pipErr.message}`);
                        reject(pipErr);
                        return;
                    }
                    vscode.window.showInformationMessage("Agentic IDE: Python virtual environment configured successfully!");
                    resolve();
                });
            });
        });
    });
}

export function deactivate() {}
