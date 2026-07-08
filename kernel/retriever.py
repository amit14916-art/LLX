import os
import ast
import hashlib
from typing import List, Dict, Any, Optional
import pyarrow as pa
import lancedb

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

class ContextRetriever:
    """
    Semantic search and document chunk indexing engine using LanceDB.
    Chunks files recursively and retrieves context relevant to user goals.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.db_dir = os.path.join(self.workspace_path, ".lancedb")
        os.makedirs(self.db_dir, exist_ok=True)
        
        # Connect to serverless LanceDB
        self.db = lancedb.connect(self.db_dir)
        self.table_name = "workspace_code"
        self.vector_dim = 384  # Dimension of all-MiniLM-L6-v2
        
        # Attempt to load local embedding model
        self.model = None
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                # Load small, fast local embedding model
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                print(f"[Retriever] SentenceTransformer load failed: {e}. Falling back to pseudo-embeddings.")

        self._init_table()

    def _init_table(self):
        """Initializes the LanceDB table using PyArrow schema validations."""
        schema = pa.schema([
            ("id", pa.string()),
            ("vector", pa.list_(pa.float32(), self.vector_dim)),
            ("filepath", pa.string()),
            ("content", pa.string()),
            ("chunk_idx", pa.int32())
        ])
        
        if self.table_name not in self.db.table_names():
            self.table = self.db.create_table(self.table_name, schema=schema)
        else:
            self.table = self.db.open_table(self.table_name)

    def _embed(self, text: str) -> List[float]:
        """Generates embedding vector. Falls back to deterministic pseudo-vectors if no model is loaded."""
        if self.model:
            return self.model.encode(text).tolist()
        else:
            # Deterministic pseudo-vector generator based on text hashing
            # Enables Arrow float validation in LanceDB even without PyTorch
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vector = []
            for i in range(self.vector_dim):
                byte_val = h[i % len(h)]
                vector.append(float(byte_val) / 128.0 - 1.0)
            return vector

    def index_file(self, rel_filepath: str):
        """
        Chunks the file at the given relative workspace path, 
        generates embeddings, and stores/updates the entries in LanceDB.
        Safeguards: Skips files larger than 1MB or containing binary null bytes.
        """
        full_path = os.path.join(self.workspace_path, rel_filepath)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            return
            
        # 1. Size safeguard: Skip files larger than 1MB
        try:
            if os.path.getsize(full_path) > 1024 * 1024:
                print(f"[Retriever] Skipping {rel_filepath} (File size exceeds 1MB limit)")
                return
        except Exception:
            return

        # 2. Binary safeguard: Skip files containing null bytes
        try:
            with open(full_path, "rb") as f:
                header = f.read(1024)
                if b"\x00" in header:
                    print(f"[Retriever] Skipping binary file: {rel_filepath}")
                    return
        except Exception:
            return

        # 3. Read content
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            print(f"[Retriever] Error reading file {rel_filepath}: {e}")
            return

        # 4. Chunk content using AST if it's a Python file
        chunks = []
        ext = os.path.splitext(rel_filepath)[1].lower()
        if ext == ".py":
            try:
                tree = ast.parse(content)
                lines = content.splitlines()
                global_lines = []
                last_end = 0
                
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        # If there were global statements before this definition, chunk them
                        start_line = node.lineno - 1
                        if start_line > last_end:
                            global_chunk = "\n".join(lines[last_end:start_line]).strip()
                            if global_chunk:
                                chunks.append(global_chunk)
                        
                        # Chunk the function/class itself
                        end_line = getattr(node, "end_lineno", len(lines))
                        chunk_content = "\n".join(lines[start_line:end_line]).strip()
                        if chunk_content:
                            chunks.append(chunk_content)
                        last_end = end_line
                
                # Append any remaining module-level code
                if last_end < len(lines):
                    remaining_chunk = "\n".join(lines[last_end:]).strip()
                    if remaining_chunk:
                        chunks.append(remaining_chunk)
                        
                if not chunks and content.strip():
                    chunks = [content]
            except Exception:
                pass  # Fallback to word-limit chunking on AST parse errors
        
        # Fallback to 500-word blocks for non-python files or failed AST parses
        if not chunks:
            words = content.split()
            chunk_size = 500
            for i in range(0, len(words), chunk_size):
                chunks.append(" ".join(words[i:i + chunk_size]))

        # Delete any existing entries for this file
        escaped_path = rel_filepath.replace('"', '\\"')
        try:
            self.table.delete(f'filepath = "{escaped_path}"')
        except Exception:
            pass

        # Build records
        data = []
        for idx, chunk in enumerate(chunks):
            data.append({
                "id": f"{rel_filepath}_chunk_{idx}",
                "vector": self._embed(chunk),
                "filepath": rel_filepath,
                "content": chunk,
                "chunk_idx": idx
            })

        if data:
            self.table.add(data)
            print(f"[Retriever] Indexed {len(data)} chunk(s) for {rel_filepath}")

    def index_workspace(self):
        """Recursively scans the workspace and indexes py, ts, js, and tsx files."""
        exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", ".lancedb", "node_modules"}
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in {".py", ".ts", ".js", ".tsx"}:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.workspace_path).replace("\\", "/")
                    self.index_file(rel_path)

    def sync_workspace(self):
        """
        Synchronizes the workspace incrementally using Git commit hashes.
        If no metadata exists, runs a full indexing pass and records the HEAD commit.
        If a prior processed commit is saved:
          1. Identifies the difference between that commit and current HEAD.
          2. Processes only created/modified/deleted files.
          3. Updates the saved metadata with the new HEAD.
        """
        import json
        import subprocess
        
        metadata_path = os.path.join(self.db_dir, "index_metadata.json")
        
        def run_git_cmd(args):
            try:
                res = subprocess.run(
                    args,
                    cwd=self.workspace_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )
                return res.stdout.strip()
            except Exception:
                return ""
        
        # Get current HEAD commit
        head = run_git_cmd(["git", "rev-parse", "HEAD"])
        if not head:
            # If not in a git repo, fallback to full index
            print("[Retriever] Git not available or no HEAD commit. Running full index_workspace...")
            self.index_workspace()
            return

        # Check if metadata exists
        if not os.path.exists(metadata_path):
            print("[Retriever] No index metadata found. Running full index_workspace...")
            self.index_workspace()
            # Save metadata
            meta = {"last_processed_commit": head}
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return

        # Read metadata
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            last_commit = meta.get("last_processed_commit")
        except Exception:
            last_commit = None

        if not last_commit:
            print("[Retriever] Invalid metadata. Running full index_workspace...")
            self.index_workspace()
            meta = {"last_processed_commit": head}
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return

        if last_commit == head:
            print("[Retriever] Cache HIT. Workspace index is up-to-date with HEAD.")
            return

        # Get diff between last_commit and head
        print(f"[Retriever] Cache MISS. Indexing changes between {last_commit[:7]} and {head[:7]}...")
        diff_output = run_git_cmd(["git", "diff", "--name-only", last_commit, head])
        if not diff_output:
            # No changes in filenames, but let's double check
            print("[Retriever] No file diff found between commits.")
            meta = {"last_processed_commit": head}
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return

        changed_files = diff_output.splitlines()
        for fpath in changed_files:
            fpath = fpath.strip().replace("\\", "/")
            # Filter by supported extensions
            ext = os.path.splitext(fpath)[1].lower()
            if ext in {".py", ".ts", ".js", ".tsx"}:
                # Exclude virtual environments and temporary directories
                if any(part in fpath.split("/") for part in {".venv", "node_modules", ".git", ".gemini", ".lancedb"}):
                    continue
                
                full_fpath = os.path.join(self.workspace_path, fpath)
                if os.path.exists(full_fpath) and not os.path.isdir(full_fpath):
                    # Added or modified
                    print(f"[Retriever] Incremental Sync: Re-indexing {fpath}...")
                    self.index_file(fpath)
                else:
                    # Deleted file
                    print(f"[Retriever] Incremental Sync: Deleting {fpath} from index...")
                    escaped_path = fpath.replace('"', '\\"')
                    try:
                        self.table.delete(f'filepath = "{escaped_path}"')
                    except Exception:
                        pass

        # Update metadata
        meta["last_processed_commit"] = head
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print(f"[Retriever] Incremental Sync complete. Updated metadata to HEAD: {head[:7]}")

    def retrieve_context(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Performs semantic query retrieval. Falls back to token frequency
        matching on Uvicorn database records if SentenceTransformers is inactive.
        """
        if self.table_name not in self.db.table_names() or self.table.count_rows() == 0:
            return []

        if self.model:
            # Execute standard vector search via LanceDB Arrow engine
            query_vector = self._embed(query)
            return self.table.search(query_vector).limit(limit).to_list()
        else:
            # Term matching fallback: scan database and sort by keyword frequencies
            # without requiring pandas dependency
            arrow_table = self.table.to_arrow()
            contents = arrow_table["content"].to_pylist()
            filepaths = arrow_table["filepath"].to_pylist()
            ids = arrow_table["id"].to_pylist()
            vectors = arrow_table["vector"].to_pylist()
            chunk_idxs = arrow_table["chunk_idx"].to_pylist()
            
            query_words = set(query.lower().split())
            scored_results = []
            
            for idx in range(len(contents)):
                content_lower = contents[idx].lower()
                filepath_lower = filepaths[idx].lower()
                
                # Check intersections
                score = sum(1 for w in query_words if w in content_lower)
                # Boost match if file name/path contains query keywords
                score += sum(3 for w in query_words if w in filepath_lower)
                
                if score > 0:
                    scored_results.append((score, {
                        "id": ids[idx],
                        "vector": vectors[idx],
                        "filepath": filepaths[idx],
                        "content": contents[idx],
                        "chunk_idx": chunk_idxs[idx]
                    }))
            
            # Return top scoring chunks
            scored_results.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored_results[:limit]]
