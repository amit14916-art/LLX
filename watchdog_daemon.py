import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from kernel.retriever import ContextRetriever

class WorkspaceIndexHandler(FileSystemEventHandler):
    """
    Listens to filesystem events in the workspace and updates
    only modified/created files in the LanceDB database.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.retriever = ContextRetriever(self.workspace_path)
        print(f"[Watchdog] Initialized indexing database on workspace: {self.workspace_path}")

    def on_modified(self, event):
        self._process_event(event, "modified")

    def on_created(self, event):
        self._process_event(event, "created")

    def _process_event(self, event, event_type: str):
        if event.is_directory:
            return

        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()
        
        # Only index supported extensions
        if ext in {".py", ".ts", ".js", ".tsx"}:
            # Exclude virtual environments and temporary directories
            norm_path = os.path.normpath(filepath).replace("\\", "/")
            if any(part in norm_path.split("/") for part in {".venv", "node_modules", ".git", ".gemini", ".lancedb"}):
                return
                
            # Get path relative to the workspace root
            rel_path = os.path.relpath(filepath, self.workspace_path).replace("\\", "/")
            print(f"[Watchdog] File {event_type}: {rel_path}. Re-indexing...", flush=True)
            try:
                # Add delay to let file write fully complete
                time.sleep(0.5)
                self.retriever.index_file(rel_path)
                print(f"[Watchdog] File {rel_path} successfully re-indexed.", flush=True)
            except Exception as e:
                print(f"[Watchdog] Error indexing {rel_path}: {e}", flush=True)

def main():
    # Use current directory or arg
    workspace = sys.argv[1] if len(sys.argv) > 1 else "."
    workspace_path = os.path.abspath(workspace)

    event_handler = WorkspaceIndexHandler(workspace_path)
    observer = Observer()
    observer.schedule(event_handler, path=workspace_path, recursive=True)
    observer.start()
    
    print(f"[Watchdog] Monitoring folder '{workspace_path}' for changes. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Watchdog] Stopping file monitor...")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
