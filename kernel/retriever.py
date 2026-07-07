import os
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
        """
        full_path = os.path.join(self.workspace_path, rel_filepath)
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            return
            
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[Retriever] Error reading file {rel_filepath}: {e}")
            return

        # Chunk the content by splitting into 500-word blocks
        words = content.split()
        chunk_size = 500
        chunks = []
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
        exclude_dirs = {".git", ".venv", "__pycache__", ".ipynb_checkpoints", ".gemini", ".lancedb"}
        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in {".py", ".ts", ".js", ".tsx"}:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.workspace_path).replace("\\", "/")
                    self.index_file(rel_path)

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
