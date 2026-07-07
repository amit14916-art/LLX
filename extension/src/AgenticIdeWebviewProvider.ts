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

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri]
        };

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

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
            overflow: hidden;
        }
        
        /* Tab Navigation styling */
        .tabs {
            display: flex;
            border-bottom: 1px solid var(--vscode-widget-border, #333);
            margin-bottom: 10px;
            flex-shrink: 0;
        }
        .tab {
            flex: 1;
            padding: 8px;
            text-align: center;
            cursor: pointer;
            color: var(--vscode-descriptionForeground);
            border-bottom: 2px solid transparent;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 10px;
            letter-spacing: 0.5px;
            transition: all 0.2s;
        }
        .tab.active {
            color: var(--vscode-foreground);
            border-bottom-color: var(--vscode-button-background);
        }
        
        .tab-content {
            display: none;
            flex-direction: column;
            flex-grow: 1;
            overflow-y: auto;
        }
        .tab-content.active {
            display: flex;
        }

        h3 {
            margin-top: 0;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 1px;
            color: var(--vscode-descriptionForeground);
        }
        
        /* Goal Tab Styling */
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
            margin-top: 10px;
            flex-grow: 1;
            background-color: var(--vscode-editor-background, #1e1e1e);
            border: 1px solid var(--vscode-widget-border, #333);
            border-radius: 2px;
            overflow-y: auto;
            padding: 8px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 11px;
            white-space: pre-wrap;
            box-sizing: border-box;
            height: 250px;
        }
        .log-entry {
            margin-bottom: 4px;
            line-height: 1.4;
        }
        .log-system { color: var(--vscode-textPreformat-foreground, #808080); }
        .log-tool { color: #4fc1ff; }
        .log-success { color: #4ec9b0; }
        .log-error { color: #f44747; }
        
        /* Telemetry Tab Styling */
        .metrics-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
            flex-shrink: 0;
        }
        .metric-card {
            background-color: var(--vscode-editor-background, #1e1e1e);
            border: 1px solid var(--vscode-widget-border, #333);
            border-radius: 4px;
            padding: 8px;
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
        }
        .metric-title {
            font-size: 9px;
            text-transform: uppercase;
            color: var(--vscode-descriptionForeground);
            margin-bottom: 4px;
            font-weight: bold;
        }
        .metric-value {
            font-size: 15px;
            font-weight: bold;
            color: var(--vscode-foreground);
        }
        .metric-sub {
            font-size: 9px;
            color: var(--vscode-descriptionForeground);
            margin-top: 2px;
        }
        
        /* SVG Ring Chart styling */
        .ring-container {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .progress-ring {
            transform: rotate(-90deg);
        }
        .progress-ring__circle {
            transition: stroke-dashoffset 0.35s;
            transform-origin: 50% 50%;
        }
        
        /* Health bar styling */
        .health-bar-container {
            background-color: var(--vscode-widget-border, #333);
            height: 6px;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
            width: 100%;
        }
        .health-bar-fill {
            background-color: #4ec9b0;
            height: 100%;
            width: 0%;
            transition: width 0.3s ease;
        }
        
        /* Event feed timeline */
        #telemetry-timeline {
            flex-grow: 1;
            background-color: var(--vscode-editor-background, #1e1e1e);
            border: 1px solid var(--vscode-widget-border, #333);
            border-radius: 4px;
            padding: 8px;
            overflow-y: auto;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 10px;
            height: 180px;
            box-sizing: border-box;
        }
        .timeline-item {
            padding: 4px 6px;
            border-bottom: 1px solid var(--vscode-widget-border, #292929);
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .timeline-item:last-child {
            border-bottom: none;
        }
        .timeline-header {
            display: flex;
            justify-content: space-between;
            font-weight: bold;
        }
        .timeline-success { color: #4ec9b0; }
        .timeline-failed { color: #f44747; }
    </style>
</head>
<body>
    <!-- Tabs Header -->
    <div class="tabs">
        <div class="tab active" onclick="switchTab('controller-tab', this)">Agent Console</div>
        <div class="tab" onclick="switchTab('telemetry-tab', this)">Telemetry Dashboard</div>
    </div>
    
    <!-- Tab 1: Agent Controller -->
    <div id="controller-tab" class="tab-content active">
        <h3>Define Your Goal</h3>
        <textarea id="goal-input" placeholder="e.g. Build addition function in calc.py and verify it passes test_calc.py"></textarea>
        
        <button id="run-btn">Run Agent</button>
        
        <h3>Execution Logs</h3>
        <div id="log-window"></div>
    </div>

    <!-- Tab 2: Telemetry & Observability -->
    <div id="telemetry-tab" class="tab-content">
        <div class="metrics-grid">
            <!-- Cost per Task Card -->
            <div class="metric-card">
                <div class="metric-title">Cost per Task</div>
                <div id="metric-cost" class="metric-value">$0.00000</div>
                <div id="metric-commits" class="metric-sub">0 commits total</div>
            </div>
            
            <!-- Success Ratio Gauge -->
            <div class="metric-card">
                <div class="metric-title">Success Rate</div>
                <div class="ring-container">
                    <svg class="progress-ring" width="30" height="30">
                        <circle class="progress-ring__circle" stroke="#333" stroke-width="3" fill="transparent" r="12" cx="15" cy="15"/>
                        <circle id="success-ring" class="progress-ring__circle" stroke="#4ec9b0" stroke-width="3" fill="transparent" r="12" cx="15" cy="15" stroke-dasharray="75.39" stroke-dashoffset="75.39"/>
                    </svg>
                    <span id="metric-success-pct" class="metric-value">0%</span>
                </div>
            </div>
            
            <!-- Linter Health Card -->
            <div class="metric-card" style="grid-column: span 2;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div class="metric-title">Linter Health Score</div>
                    <div id="metric-lint-score" class="metric-value" style="font-size:12px;">N/A</div>
                </div>
                <div class="health-bar-container">
                    <div id="lint-health-bar" class="health-bar-fill"></div>
                </div>
            </div>
            
            <!-- Tokens Counter Card -->
            <div class="metric-card" style="grid-column: span 2;">
                <div class="metric-title">Cumulative Tokens Used</div>
                <div id="metric-tokens" class="metric-value">0 tokens</div>
            </div>
        </div>
        
        <h3>Metrics Event Stream</h3>
        <div id="telemetry-timeline"></div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        
        // Element bindings
        const goalInput = document.getElementById('goal-input');
        const runBtn = document.getElementById('run-btn');
        const logWindow = document.getElementById('log-window');
        
        const metricCost = document.getElementById('metric-cost');
        const metricCommits = document.getElementById('metric-commits');
        const metricSuccessPct = document.getElementById('metric-success-pct');
        const metricTokens = document.getElementById('metric-tokens');
        const metricLintScore = document.getElementById('metric-lint-score');
        const lintHealthBar = document.getElementById('lint-health-bar');
        const successRing = document.getElementById('success-ring');
        const telemetryTimeline = document.getElementById('telemetry-timeline');
        
        // WebSockets instances
        let wsLogs = null;
        let wsMetrics = null;
        
        // Telemetry state aggregates
        let totalTokens = 0;
        let totalCost = 0.0;
        let totalCommits = 0;
        let successCount = 0;
        let failCount = 0;
        
        // Circular Progress Ring calculation parameters
        const ringRadius = 12;
        const ringCircumference = 2 * Math.PI * ringRadius; // ~75.40

        function setSuccessRingOffset(percent) {
            const offset = ringCircumference - (percent / 100) * ringCircumference;
            successRing.style.strokeDashoffset = offset;
        }

        // Switch between Console and Telemetry panels
        window.switchTab = function(tabId, tabEl) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            tabEl.classList.add('active');
            document.getElementById(tabId).classList.add('active');
        };

        function appendLog(message, type = 'system') {
            const entry = document.createElement('div');
            entry.className = 'log-entry log-' + type;
            entry.innerText = message;
            logWindow.appendChild(entry);
            logWindow.scrollTop = logWindow.scrollHeight;
        }

        // 1. Initialize Log Listener
        function connectLogsWebSocket() {
            if (wsLogs) wsLogs.close();
            wsLogs = new WebSocket('ws://127.0.0.1:8000/ws/logs');
            
            wsLogs.onopen = () => appendLog('[System] Connected to log broker.', 'system');
            wsLogs.onmessage = (event) => {
                const text = event.data;
                let type = 'system';
                if (text.includes('Error') || text.includes('failed') || text.includes('STDERR')) {
                    type = 'error';
                } else if (text.includes('succeeded') || text.includes('completed successfully') || text.includes('passed')) {
                    type = 'success';
                } else if (text.includes('Calling tool')) {
                    type = 'tool';
                }
                appendLog(text, type);
            };
            wsLogs.onerror = () => appendLog('[System] WebSocket log connection error.', 'error');
            wsLogs.onclose = () => setTimeout(connectLogsWebSocket, 5000);
        }

        // 2. Initialize Telemetry metrics listener
        function connectMetricsWebSocket() {
            if (wsMetrics) wsMetrics.close();
            wsMetrics = new WebSocket('ws://127.0.0.1:8000/metrics');
            
            wsMetrics.onopen = () => {
                console.log('[Telemetry] Connected to metrics WebSocket stream.');
            };
            
            wsMetrics.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    handleTelemetryEvent(data);
                } catch (e) {
                    console.error('Error parsing metrics payload:', e);
                }
            };
            
            wsMetrics.onerror = () => {
                console.error('[Telemetry] WebSocket metrics connection error.');
            };
            
            wsMetrics.onclose = () => setTimeout(connectMetricsWebSocket, 5000);
        }

        // 3. Connect to both WebSocket servers
        connectLogsWebSocket();
        connectMetricsWebSocket();

        // 4. Handle incoming telemetry event records
        function handleTelemetryEvent(event) {
            // Aggregate tokens and costs
            totalTokens += event.tokens_used;
            totalCost += event.cost;
            
            // Adjust success/failure ratio
            if (event.success_status === 'success') {
                successCount++;
            } else {
                failCount++;
            }
            
            const totalRuns = successCount + failCount;
            const successPct = totalRuns > 0 ? Math.round((successCount / totalRuns) * 100) : 0;
            
            // Adjust commits counter
            if (event.commit_message) {
                totalCommits++;
            }
            
            // Adjust linter health rating
            if (event.lint_score !== undefined) {
                const score = event.lint_score;
                metricLintScore.innerText = score.toFixed(2) + '/10.00';
                lintHealthBar.style.width = (score * 10) + '%';
                if (score < 10) {
                    lintHealthBar.style.backgroundColor = '#f44747'; // red style fill
                } else {
                    lintHealthBar.style.backgroundColor = '#4ec9b0'; // green style fill
                }
            }

            // Update UI widgets
            metricCost.innerText = '$' + totalCost.toFixed(5);
            metricCommits.innerText = totalCommits + ' commit(s) total';
            metricSuccessPct.innerText = successPct + '%';
            setSuccessRingOffset(successPct);
            metricTokens.innerText = totalTokens.toLocaleString() + ' tokens';

            // Add item to timeline view
            const item = document.createElement('div');
            item.className = 'timeline-item';
            
            const timeStr = event.timestamp.substring(11, 19);
            const statusClass = event.success_status === 'success' ? 'timeline-success' : 'timeline-failed';
            const statusText = event.success_status === 'success' ? 'SUCCESS' : 'REJECTED';
            
            item.innerHTML = \`
                <div class="timeline-header">
                    <span>[\${timeStr}] NODE: \${event.node_name.toUpperCase()}</span>
                    <span class="\${statusClass}">\${statusText}</span>
                </div>
                <div style="color:var(--vscode-descriptionForeground);">
                    Tokens: \${event.tokens_used} | Cost: $\${event.cost.toFixed(6)}
                </div>
            \`;
            
            telemetryTimeline.appendChild(item);
            telemetryTimeline.scrollTop = telemetryTimeline.scrollHeight;
        }

        // 5. Submit goals to backend
        runBtn.addEventListener('click', async () => {
            const goal = goalInput.value.trim();
            if (!goal) {
                vscode.postMessage({ command: 'showError', text: 'Please enter a goal before running.' });
                return;
            }

            runBtn.disabled = true;
            logWindow.innerHTML = '';
            appendLog('[System] Dispatching goal to fastapi: ' + goal, 'system');

            try {
                const response = await fetch('http://127.0.0.1:8000/execute', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ goal: goal })
                });

                if (response.status !== 200) {
                    throw new Error('Backend returned status ' + response.status);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();

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
                
                appendLog('[System] SSE Stream closed.', 'system');
            } catch (err) {
                appendLog('[System] Error executing goal: ' + err.message, 'error');
                vscode.postMessage({ command: 'showError', text: 'Failed to connect to FastAPI kernel.' });
                runBtn.disabled = false;
            }
        });

        function handleStateUpdate(chunk) {
            if (chunk.planner) {
                const plan = chunk.planner.plan;
                appendLog('\\n[Planner] Generated Plan:');
                plan.forEach(t => {
                    appendLog('  - [' + t.id + '] ' + t.description + ' (status: ' + t.status + ')', 'tool');
                });
            }

            if (chunk.executor) {
                appendLog('\\n[Executor] Task execution completed.');
            }

            if (chunk.critic) {
                const status = chunk.critic.critic_status;
                const score = chunk.critic.current_lint_score;
                
                if (status === 'PASSED') {
                    appendLog('[Success] Peer review PASSED! Score: ' + score.toFixed(2) + '/10.00', 'success');
                    vscode.postMessage({ command: 'showInfo', text: 'Agent has successfully finished the task!' });
                } else {
                    appendLog('[Error] Peer review REJECTED! Score: ' + score.toFixed(2) + '/10.00', 'error');
                    vscode.postMessage({ command: 'showError', text: 'Agent encountered style/type validation errors.' });
                }
                runBtn.disabled = false;
            }
        }
    </script>
</body>
</html>`;
    }
}
