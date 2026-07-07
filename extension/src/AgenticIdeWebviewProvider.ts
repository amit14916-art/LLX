import * as vscode from 'vscode';

export class AgenticIdeWebviewProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'agentic-ide.sidebar';
    private _view?: vscode.WebviewView;

    constructor(private readonly _extensionUri: vscode.Uri) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this._view = webviewView;

        // Configure webview settings: allow scripts and restrict asset roots
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        // Listen for notification messages from the Webview frontend
        webviewView.webview.onDidReceiveMessage(message => {
            switch (message.command) {
                case 'showInfo':
                    vscode.window.showInformationMessage(message.text);
                    break;
                case 'showError':
                    vscode.window.showErrorMessage(message.text);
                    break;
            }
        });
    }

    private _getHtmlForWebview(webview: vscode.Webview): string {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agentic IDE</title>
    <style>
        body {
            padding: 10px;
            color: var(--vscode-foreground);
            font-family: var(--vscode-font-family, sans-serif);
            font-size: var(--vscode-font-size, 13px);
            background-color: var(--vscode-sideBar-background);
            display: flex;
            flex-direction: column;
            height: 100vh;
            box-sizing: border-box;
        }
        h3 {
            margin-top: 0;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 1px;
            color: var(--vscode-descriptionForeground);
        }
        textarea {
            width: 100%;
            height: 80px;
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border, transparent);
            padding: 6px 8px;
            resize: vertical;
            border-radius: 2px;
            box-sizing: border-box;
            font-family: inherit;
        }
        textarea:focus {
            outline: 1px solid var(--vscode-focusBorder);
        }
        button {
            margin-top: 8px;
            width: 100%;
            padding: 8px;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            cursor: pointer;
            font-weight: 600;
            border-radius: 2px;
            transition: background-color 0.2s;
        }
        button:hover {
            background-color: var(--vscode-button-hoverBackground);
        }
        button:disabled {
            background-color: var(--vscode-button-secondaryBackground, #555);
            color: #aaa;
            cursor: not-allowed;
        }
        #log-window {
            margin-top: 15px;
            flex-grow: 1;
            background-color: var(--vscode-editor-background, #1e1e1e);
            border: 1px solid var(--vscode-widget-border, #333);
            border-radius: 2px;
            overflow-y: auto;
            padding: 10px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 11px;
            white-space: pre-wrap;
            box-sizing: border-box;
            height: 250px;
            display: flex;
            flex-direction: column;
        }
        .log-entry {
            margin-bottom: 4px;
            line-height: 1.4;
        }
        .log-system {
            color: var(--vscode-textPreformat-foreground, #808080);
        }
        .log-tool {
            color: #4fc1ff; /* light blue */
        }
        .log-success {
            color: #4ec9b0; /* green */
        }
        .log-error {
            color: #f44747; /* red */
        }
        .task-list {
            margin: 5px 0;
            padding-left: 15px;
            list-style-type: square;
        }
        .task-pending { color: #858585; }
        .task-progress { color: #cca700; font-weight: bold; }
        .task-completed { color: #4ec9b0; text-decoration: line-through; }
        .task-failed { color: #f44747; font-weight: bold; }
    </style>
</head>
<body>
    <h3>Define Your Goal</h3>
    <textarea id="goal-input" placeholder="e.g. Implement add function in calc.py and verify it passes test_calc.py"></textarea>
    
    <button id="run-btn">Run Agent</button>
    
    <h3>Execution Logs</h3>
    <div id="log-window"></div>

    <script>
        const vscode = acquireVsCodeApi();
        const goalInput = document.getElementById('goal-input');
        const runBtn = document.getElementById('run-btn');
        const logWindow = document.getElementById('log-window');
        
        let ws = null;

        function log(message, type = 'system') {
            const entry = document.createElement('div');
            entry.className = 'log-entry log-' + type;
            entry.innerText = message;
            logWindow.appendChild(entry);
            logWindow.scrollTop = logWindow.scrollHeight;
        }

        // Initialize WebSocket connection for real-time logs
        function connectWebSocket() {
            if (ws) ws.close();
            
            ws = new WebSocket('ws://127.0.0.1:8000/ws/logs');
            
            ws.onopen = () => {
                log('[System] Connected to Agentic IDE Kernel Logger.', 'system');
            };
            
            ws.onmessage = (event) => {
                const text = event.data;
                // Colorize logs slightly based on keywords
                let type = 'system';
                if (text.includes('Error') || text.includes('failed') || text.includes('STDERR')) {
                    type = 'error';
                } else if (text.includes('succeeded') || text.includes('completed successfully') || text.includes('Test passed')) {
                    type = 'success';
                } else if (text.includes('Calling tool')) {
                    type = 'tool';
                }
                log(text, type);
            };
            
            ws.onerror = () => {
                log('[System] WebSocket logger connection error. Is the FastAPI backend running?', 'error');
            };
            
            ws.onclose = () => {
                // Attempt to reconnect in 5 seconds
                setTimeout(connectWebSocket, 5000);
            };
        }

        // Connect WebSocket on view initialization
        connectWebSocket();

        runBtn.addEventListener('click', async () => {
            const goal = goalInput.value.trim();
            if (!goal) {
                vscode.postMessage({ command: 'showError', text: 'Please enter a goal before running.' });
                return;
            }

            runBtn.disabled = true;
            logWindow.innerHTML = '';
            log('[System] Dispatching goal: ' + goal, 'system');

            try {
                const response = await fetch('http://127.0.0.1:8000/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ goal: goal })
                });

                if (response.status !== 200) {
                    throw new Error('Backend returned status ' + response.status);
                }

                // Parse the Server-Sent Events (SSE) stream
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop(); // Retain partial lines in buffer

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.substring(6).trim();
                            if (!dataStr) continue;
                            
                            try {
                                const chunk = JSON.parse(dataStr);
                                handleStateUpdate(chunk);
                            } catch (e) {
                                console.error('Error parsing SSE event:', e);
                            }
                        }
                    }
                }
                
                log('[System] SSE Stream closed.', 'system');
            } catch (err) {
                log('[System] Error executing goal: ' + err.message, 'error');
                vscode.postMessage({ command: 'showError', text: 'Failed to connect to FastAPI kernel.' });
                runBtn.disabled = false;
            }
        });

        function handleStateUpdate(chunk) {
            // Process planner node output
            if (chunk.planner) {
                const plan = chunk.planner.plan;
                log('\\n[Planner] Generated Plan:');
                plan.forEach(t => {
                    log('  - [' + t.id + '] ' + t.description + ' (status: ' + t.status + ')', 'tool');
                });
            }

            // Process executor node final outcome
            if (chunk.executor) {
                const plan = chunk.executor.plan;
                const errors = chunk.executor.error_log || [];
                
                log('\\n[Executor] Finalizing execution loop.');
                
                const allCompleted = plan.every(t => t.status === 'completed');
                if (allCompleted) {
                    log('[Success] All tasks successfully completed and verified!', 'success');
                    vscode.postMessage({ command: 'showInfo', text: 'Agent has successfully finished the task!' });
                } else {
                    log('[Error] Execution loop halted. Some tasks failed.', 'error');
                    vscode.postMessage({ command: 'showError', text: 'Agent encountered a critical error during execution.' });
                }
                
                runBtn.disabled = false;
            }
        }
    </script>
</body>
</html>`;
    }
}
