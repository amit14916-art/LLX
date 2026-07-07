// Constants & State
let currentOpenFile = null;
let ws = null;
let allFiles = [];
let selectedIndex = 0;
let recentFolders = ['.'];

// DOM Elements
const workspacePathEl = document.getElementById('current-workspace-path');
const fileTreeEl = document.getElementById('file-tree');
const refreshFilesBtn = document.getElementById('refresh-files');
const editorTabsEl = document.getElementById('editor-tabs');
const editorTextarea = document.getElementById('editor-text');
const lineNumbersEl = document.getElementById('line-numbers');
const saveFileBtn = document.getElementById('save-file-btn');
const chatMessagesEl = document.getElementById('chat-messages');
const chatInputText = document.getElementById('chat-input-text');
const btnSubmitGoal = document.getElementById('btn-submit-goal');
const testCommandInput = document.getElementById('test-command-input');
const progressBox = document.getElementById('agent-progress-box');
const progressLog = document.getElementById('progress-log');

// Core Elements (Integrated Terminal, Theme, Quick Open, Inline AI)
const themeSelect = document.getElementById('theme-select');
const terminalPanel = document.getElementById('terminal-panel');
const terminalHeader = document.getElementById('terminal-header');
const toggleTerminalBtn = document.getElementById('toggle-terminal-btn');
const clearTerminalBtn = document.getElementById('clear-terminal-btn');
const terminalOutput = document.getElementById('terminal-output');
const terminalInput = document.getElementById('terminal-input');

const quickOpenModal = document.getElementById('quick-open-modal');
const quickOpenInput = document.getElementById('quick-open-input');
const quickOpenResults = document.getElementById('quick-open-results');

const inlineAiOverlay = document.getElementById('inline-ai-overlay');
const inlineAiInput = document.getElementById('inline-ai-input');

// Welcome Dashboard & Modals Elements
const welcomeDashboard = document.getElementById('welcome-dashboard');
const logoHomeBtn = document.getElementById('logo-home-btn');

const cardNewFile = document.getElementById('card-new-file');
const cardOpenFolder = document.getElementById('card-open-folder');
const cardCloneRepo = document.getElementById('card-clone-repo');
const cardShortcuts = document.getElementById('card-shortcuts');

const openFolderModal = document.getElementById('open-folder-modal');
const openFolderInput = document.getElementById('open-folder-input');
const btnFolderCancel = document.getElementById('btn-folder-cancel');
const btnFolderConfirm = document.getElementById('btn-folder-confirm');

const cloneRepoModal = document.getElementById('clone-repo-modal');
const cloneUrlInput = document.getElementById('clone-url-input');
const cloneDirInput = document.getElementById('clone-dir-input');
const btnCloneCancel = document.getElementById('btn-clone-cancel');
const btnCloneConfirm = document.getElementById('btn-clone-confirm');

const newFileModal = document.getElementById('new-file-modal');
const newFileInput = document.getElementById('new-file-input');
const btnFileCancel = document.getElementById('btn-file-cancel');
const btnFileConfirm = document.getElementById('btn-file-confirm');

const shortcutsModal = document.getElementById('shortcuts-modal');
const btnShortcutsClose = document.getElementById('btn-shortcuts-close');
const recentFoldersList = document.getElementById('recent-folders-list');

// Initialization
document.addEventListener('DOMContentLoaded', () => {
    fetchWorkspaceInfo();
    loadWorkspaceFiles();
    connectWebSocket();
    showWelcomeDashboard(); // Load welcome screen by default

    // Core Event Listeners
    refreshFilesBtn.addEventListener('click', loadWorkspaceFiles);
    editorTextarea.addEventListener('input', updateLineNumbers);
    editorTextarea.addEventListener('scroll', syncEditorScroll);
    saveFileBtn.addEventListener('click', saveCurrentFile);
    btnSubmitGoal.addEventListener('click', submitGoalToAgent);

    // Theme Selector
    themeSelect.addEventListener('change', (e) => {
        document.body.className = e.target.value;
    });

    // Logo click goes home
    logoHomeBtn.addEventListener('click', showWelcomeDashboard);

    // Collapsible Terminal
    terminalHeader.addEventListener('click', (e) => {
        if (e.target !== clearTerminalBtn && e.target !== toggleTerminalBtn) {
            toggleTerminal();
        }
    });
    toggleTerminalBtn.addEventListener('click', toggleTerminal);
    clearTerminalBtn.addEventListener('click', () => {
        terminalOutput.textContent = '';
    });

    // Terminal Input
    terminalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            runTerminalCommand();
        }
    });

    // Shortcuts: Ctrl+P for File Finder, Ctrl+K for Inline AI
    window.addEventListener('keydown', handleShortcuts);
    
    // Quick Open Modal input and navigation
    quickOpenInput.addEventListener('input', filterQuickOpenFiles);
    quickOpenInput.addEventListener('keydown', handleQuickOpenNavigation);

    // Inline AI Modal key events
    inlineAiInput.addEventListener('keydown', handleInlineAiSubmit);

    // Welcome Dashboard Action Cards
    cardNewFile.addEventListener('click', () => {
        newFileModal.style.display = 'flex';
        newFileInput.value = '';
        newFileInput.focus();
    });

    cardOpenFolder.addEventListener('click', () => {
        openFolderModal.style.display = 'flex';
        openFolderInput.value = '';
        openFolderInput.focus();
    });

    cardCloneRepo.addEventListener('click', () => {
        cloneRepoModal.style.display = 'flex';
        cloneUrlInput.value = '';
        cloneDirInput.value = '';
        cloneUrlInput.focus();
    });

    cardShortcuts.addEventListener('click', () => {
        shortcutsModal.style.display = 'flex';
    });

    // Modals Cancel/Confirm Handlers
    btnFolderCancel.addEventListener('click', closeModals);
    btnFolderConfirm.addEventListener('click', confirmOpenFolder);

    btnCloneCancel.addEventListener('click', closeModals);
    btnCloneConfirm.addEventListener('click', confirmCloneRepo);

    btnFileCancel.addEventListener('click', closeModals);
    btnFileConfirm.addEventListener('click', confirmCreateFile);

    btnShortcutsClose.addEventListener('click', closeModals);
});

// Toggle Terminal Pane
function toggleTerminal() {
    terminalPanel.classList.toggle('collapsed');
    toggleTerminalBtn.textContent = terminalPanel.classList.contains('collapsed') ? '➕' : '➖';
}

// Global Shortcuts
function handleShortcuts(e) {
    // Ctrl+P (or Cmd+P) for Quick Open
    if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
        e.preventDefault();
        openQuickOpenModal();
    }
    // Ctrl+K (or Cmd+K) for Inline AI (only when inside editor)
    if ((e.ctrlKey || e.metaKey) && e.key === 'k' && document.activeElement === editorTextarea) {
        e.preventDefault();
        openInlineAiOverlay();
    }
    // Ctrl+S to save open file
    if ((e.ctrlKey || e.metaKey) && e.key === 's' && currentOpenFile) {
        e.preventDefault();
        saveCurrentFile();
    }
    // Escape key closes modals
    if (e.key === 'Escape') {
        closeModals();
    }
}

// Close All Modals
function closeModals() {
    quickOpenModal.style.display = 'none';
    inlineAiOverlay.style.display = 'none';
    openFolderModal.style.display = 'none';
    cloneRepoModal.style.display = 'none';
    newFileModal.style.display = 'none';
    shortcutsModal.style.display = 'none';
}

// Toggle Dashboard view
function showWelcomeDashboard() {
    currentOpenFile = null;
    welcomeDashboard.style.display = 'flex';
    editorTextarea.style.display = 'none';
    lineNumbersEl.style.display = 'none';
    saveFileBtn.style.display = 'none';
    
    // Highlight home tab
    editorTabsEl.innerHTML = `<div class="tab active">🏠 Welcome</div>`;
}

function hideWelcomeDashboard() {
    welcomeDashboard.style.display = 'none';
    editorTextarea.style.display = 'block';
    lineNumbersEl.style.display = 'block';
    saveFileBtn.style.display = 'block';
}

// --- Dynamic Workspace / Folder Switching ---
async function confirmOpenFolder() {
    const path = openFolderInput.value.trim();
    if (!path) return;

    btnFolderConfirm.disabled = true;
    btnFolderConfirm.textContent = 'Opening...';

    try {
        const res = await fetch('/api/workspace', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });
        const result = await res.json();
        
        if (result.status === 'success') {
            appendMessage('system', `Opened workspace: ${path}`);
            addRecentFolder(path);
            closeModals();
            fetchWorkspaceInfo();
            loadWorkspaceFiles();
            showWelcomeDashboard();
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch (err) {
        alert(`Failed to open folder: ${err.message}`);
    } finally {
        btnFolderConfirm.disabled = false;
        btnFolderConfirm.textContent = 'Open Folder';
    }
}

// --- Git Clone Integration ---
async function confirmCloneRepo() {
    const url = cloneUrlInput.value.trim();
    const dest = cloneDirInput.value.trim();
    if (!url || !dest) {
        alert('Please fill out both repository URL and folder name.');
        return;
    }

    btnCloneConfirm.disabled = true;
    btnCloneConfirm.textContent = 'Cloning...';
    appendMessage('system', `Cloning GitHub repo: ${url} into local folder: ${dest}...`);

    try {
        const res = await fetch('/api/git/clone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url, path: dest })
        });
        const result = await res.json();
        
        if (result.status === 'success') {
            appendMessage('system', `Successfully cloned repository! Workspace switched to: ${result.workspace_path}`);
            addRecentFolder(result.workspace_path);
            closeModals();
            fetchWorkspaceInfo();
            loadWorkspaceFiles();
            showWelcomeDashboard();
        } else {
            appendMessage('error', `Git Clone failed: ${result.message}`);
            alert(`Clone failed: ${result.message}`);
        }
    } catch (err) {
        alert(`Failed to clone: ${err.message}`);
    } finally {
        btnCloneConfirm.disabled = false;
        btnCloneConfirm.textContent = 'Clone Repo';
    }
}

// --- Create New File ---
async function confirmCreateFile() {
    const filename = newFileInput.value.trim();
    if (!filename) return;

    btnFileConfirm.disabled = true;
    
    try {
        const res = await fetch('/api/file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: filename, content: '' })
        });
        const result = await res.json();
        
        if (result.status === 'success') {
            closeModals();
            loadWorkspaceFiles();
            openFile(filename);
        } else {
            alert(`Failed to create file: ${result.message}`);
        }
    } catch (err) {
        alert(`Failed to create file: ${err.message}`);
    } finally {
        btnFileConfirm.disabled = false;
    }
}

// Manage Recent Folders list
function addRecentFolder(path) {
    if (!recentFolders.includes(path)) {
        recentFolders.unshift(path);
        if (recentFolders.length > 5) recentFolders.pop();
        updateRecentFoldersUI();
    }
}

function updateRecentFoldersUI() {
    recentFoldersList.innerHTML = '';
    recentFolders.forEach(path => {
        const item = document.createElement('div');
        item.className = 'recent-item';
        item.textContent = path === '.' ? '🏠 Current Project Workspace Root (.)' : `📁 ${path}`;
        item.addEventListener('click', async () => {
            openFolderInput.value = path === '.' ? '.' : path;
            confirmOpenFolder();
        });
        recentFoldersList.appendChild(item);
    });
}

// --- Quick Open (Ctrl+P) Logic ---
function openQuickOpenModal() {
    quickOpenModal.style.display = 'flex';
    quickOpenInput.value = '';
    quickOpenInput.focus();
    selectedIndex = 0;
    filterQuickOpenFiles();
}

function filterQuickOpenFiles() {
    const query = quickOpenInput.value.toLowerCase().trim();
    const filtered = allFiles.filter(f => f.toLowerCase().includes(query));
    
    quickOpenResults.innerHTML = '';
    if (filtered.length === 0) {
        quickOpenResults.innerHTML = '<div class="modal-item">No files matched</div>';
        return;
    }

    filtered.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'modal-item';
        if (index === selectedIndex) {
            item.className += ' active';
        }
        item.innerHTML = `📄 <span class="file-name">${file}</span>`;
        item.addEventListener('click', () => {
            openFile(file);
            closeModals();
        });
        quickOpenResults.appendChild(item);
    });
}

function handleQuickOpenNavigation(e) {
    const items = quickOpenResults.querySelectorAll('.modal-item');
    if (items.length === 0) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedIndex = (selectedIndex + 1) % items.length;
        filterQuickOpenFiles();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedIndex = (selectedIndex - 1 + items.length) % items.length;
        filterQuickOpenFiles();
    } else if (e.key === 'Enter') {
        e.preventDefault();
        const activeItem = items[selectedIndex];
        if (activeItem) {
            const filename = activeItem.querySelector('.file-name').textContent;
            openFile(filename);
            closeModals();
        }
    }
}

// --- Inline AI (Ctrl+K) Logic ---
function openInlineAiOverlay() {
    inlineAiOverlay.style.display = 'block';
    inlineAiInput.value = '';
    inlineAiInput.focus();
}

async function handleInlineAiSubmit(e) {
    if (e.key === 'Escape') {
        closeModals();
    }
    if (e.key === 'Enter') {
        const prompt = inlineAiInput.value.trim();
        if (!prompt) return;

        inlineAiInput.disabled = true;
        inlineAiInput.value = '🤖 Generating code inline...';

        try {
            // Call the local mock generator for immediate cool inline results
            await new Promise(resolve => setTimeout(resolve, 1500)); // Simulate think delay
            
            let insertedCode = `\n# AI Generated: ${prompt}\n`;
            if (prompt.toLowerCase().includes('fibonacci')) {
                insertedCode += `def fibonacci(n):\n    if n <= 0:\n        return []\n    elif n == 1:\n        return [0]\n    sequence = [0, 1]\n    while len(sequence) < n:\n        sequence.append(sequence[-1] + sequence[-2])\n    return sequence\n`;
            } else if (prompt.toLowerCase().includes('comment')) {
                insertedCode += `# Added code explanation for current section\n`;
            } else if (prompt.toLowerCase().includes('calculator')) {
                insertedCode += `class SimpleCalculator:\n    def add(self, a, b): return a + b\n`;
            } else {
                insertedCode += `def generated_function():\n    # TODO: Implement based on: ${prompt}\n    pass\n`;
            }

            // Insert code at cursor position in textarea
            const startPos = editorTextarea.selectionStart;
            const endPos = editorTextarea.selectionEnd;
            const originalVal = editorTextarea.value;
            
            editorTextarea.value = originalVal.substring(0, startPos) + insertedCode + originalVal.substring(endPos);
            editorTextarea.selectionStart = startPos + insertedCode.length;
            editorTextarea.selectionEnd = startPos + insertedCode.length;
            
            updateLineNumbers();
            appendMessage('system', `Inline AI code inserted successfully.`);
        } catch (err) {
            appendMessage('error', `Inline AI failed: ${err.message}`);
        } finally {
            inlineAiInput.disabled = false;
            closeModals();
        }
    }
}

// --- Terminal Executor Logic ---
async function runTerminalCommand() {
    const cmd = terminalInput.value.trim();
    if (!cmd) return;

    terminalInput.value = '';
    
    // Append user command
    terminalOutput.textContent += `\n$ ${cmd}\n`;
    terminalOutput.scrollTop = terminalOutput.scrollHeight;

    try {
        const res = await fetch('/api/terminal', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ command: cmd })
        });
        
        const data = await res.json();
        
        if (data.status === 'success') {
            terminalOutput.textContent += data.output;
        } else {
            terminalOutput.textContent += `Error: ${data.message}\n`;
        }
    } catch (err) {
        terminalOutput.textContent += `Terminal execution failed: ${err.message}\n`;
    }
    
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Sync scrolling
function syncEditorScroll() {
    lineNumbersEl.scrollTop = editorTextarea.scrollTop;
}

// Update Editor Line Numbers
function updateLineNumbers() {
    const lines = editorTextarea.value.split('\n');
    const lineCount = Math.max(lines.length, 1);
    let html = '';
    for (let i = 1; i <= lineCount; i++) {
        html += `<div>${i}</div>`;
    }
    lineNumbersEl.innerHTML = html;
}

// Fetch Workspace Info
async function fetchWorkspaceInfo() {
    try {
        const res = await fetch('/api/workspace');
        const data = await res.json();
        workspacePathEl.textContent = data.workspace_path;
    } catch (err) {
        console.error('Error fetching workspace:', err);
        workspacePathEl.textContent = 'Disconnected';
    }
}

// Load Files into Sidebar & cache for Quick Open
async function loadWorkspaceFiles() {
    fileTreeEl.innerHTML = '<div class="loading-spinner">Loading workspace files...</div>';
    try {
        const res = await fetch('/api/files');
        allFiles = await res.json();
        
        fileTreeEl.innerHTML = '';
        if (allFiles.length === 0) {
            fileTreeEl.innerHTML = '<div class="file-item">No files found.</div>';
            return;
        }

        allFiles.forEach(file => {
            const item = document.createElement('div');
            item.className = 'file-item';
            if (currentOpenFile === file) {
                item.className += ' active';
            }
            item.innerHTML = `<span class="file-icon">${file.endsWith('.py') ? '🐍' : '📄'}</span><span class="file-name">${file}</span>`;
            item.addEventListener('click', () => openFile(file));
            fileTreeEl.appendChild(item);
        });
    } catch (err) {
        fileTreeEl.innerHTML = '<div class="file-item text-danger">Error loading files</div>';
    }
}

// Open File in Editor
async function openFile(filename) {
    currentOpenFile = filename;
    hideWelcomeDashboard();

    // Update active UI classes
    document.querySelectorAll('.file-item').forEach(el => {
        const nameEl = el.querySelector('.file-name');
        if (nameEl && nameEl.textContent === filename) {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });

    // Update Tab
    editorTabsEl.innerHTML = `<div class="tab active">📁 ${filename}</div>`;

    // Fetch Content
    editorTextarea.value = 'Loading file...';
    try {
        const res = await fetch(`/api/file?path=${encodeURIComponent(filename)}`);
        const data = await res.json();
        editorTextarea.value = data.content;
        updateLineNumbers();
    } catch (err) {
        editorTextarea.value = 'Failed to load file contents.';
    }
}

// Save Current File
async function saveCurrentFile() {
    if (!currentOpenFile) {
        alert('Please open a file first to save.');
        return;
    }
    
    try {
        const response = await fetch('/api/file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                path: currentOpenFile,
                content: editorTextarea.value
            })
        });

        const result = await response.json();
        if (result.status === 'success') {
            appendMessage('system', `Successfully saved file: ${currentOpenFile}`);
        } else {
            appendMessage('error', `Failed to save file: ${result.message}`);
        }
    } catch (err) {
        appendMessage('error', `Error saving file: ${err.message}`);
    }
}

// Connect to Log WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WS Logs connected.');
    };

    ws.onmessage = (event) => {
        const msg = event.data;
        appendProgressLog(msg);
    };

    ws.onclose = () => {
        console.log('WS Logs disconnected, retrying...');
        setTimeout(connectWebSocket, 3000);
    };
}

// Append Chat Message
function appendMessage(sender, text) {
    const msgEl = document.createElement('div');
    msgEl.className = `message ${sender}`;
    msgEl.innerHTML = `
        <div class="message-content">
            <strong>${sender.toUpperCase()}:</strong> ${text}
        </div>
    `;
    chatMessagesEl.appendChild(msgEl);
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

// Append Progress Log Entry
function appendProgressLog(logText) {
    progressBox.style.display = 'flex';
    const logEl = document.createElement('div');
    logEl.className = 'log-entry';
    logEl.textContent = logText;
    progressLog.appendChild(logEl);
    progressLog.scrollTop = progressLog.scrollHeight;
}

// Submit Goal to Agent
async function submitGoalToAgent() {
    const goalText = chatInputText.value.trim();
    if (!goalText) return;

    appendMessage('user', goalText);
    chatInputText.value = '';
    progressLog.innerHTML = '';
    progressBox.style.display = 'flex';
    appendProgressLog('[Client] Initiating agent execution...');

    try {
        const testCommand = testCommandInput.value || 'pytest';
        const response = await fetch('/execute', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                goal: goalText,
                test_command: testCommand
            })
        });

        if (!response.body) {
            throw new Error('Streaming response body not supported.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // keep partial line in buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataJson = JSON.parse(line.slice(6));
                    handleAgentStreamChunk(dataJson);
                }
            }
        }
        
        appendProgressLog('[Client] Execution stream completed.');
        loadWorkspaceFiles(); // Reload files in case agent created new ones
    } catch (err) {
        appendMessage('error', `Agent execution failed: ${err.message}`);
    }
}

// Handle Agent Stream Chunk
function handleAgentStreamChunk(chunk) {
    for (const [nodeName, data] of Object.entries(chunk)) {
        if (data.plan && data.plan.length > 0) {
            const activeTasks = data.plan.map(t => `${t.id}: ${t.description} [${t.status}]`).join('\n');
            appendProgressLog(`[Node: ${nodeName}] Plan updated:\n${activeTasks}`);
        }
        
        if (data.error_log && data.error_log.length > 0) {
            const lastErr = data.error_log[data.error_log.length - 1];
            appendProgressLog(`[Error] ${lastErr.step}: ${lastErr.message}`);
        }
    }
}
