import * as vscode from 'vscode';
import { AgenticIdeWebviewProvider } from './AgenticIdeWebviewProvider';

export function activate(context: vscode.ExtensionContext) {
    console.log('Agentic IDE Extension is now active.');

    // Instantiate and register the Webview view provider for the sidebar
    const provider = new AgenticIdeWebviewProvider(context.extensionUri);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            AgenticIdeWebviewProvider.viewType,
            provider
        )
    );
}

export function deactivate() {}
