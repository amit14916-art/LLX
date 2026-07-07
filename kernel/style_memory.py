import os
import hashlib
import subprocess
from typing import List, Dict, Any, Optional
import pyarrow as pa
import lancedb

class StyleMemory:
    """
    Style memory database using a dedicated LanceDB collection.
    Stores and retrieves 'Before/After' user corrections to personalize Coder output.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = os.path.abspath(workspace_path)
        self.db_dir = os.path.join(self.workspace_path, ".lancedb")
        self.db = lancedb.connect(self.db_dir)
        self.table_name = "style_memory"
        self.vector_dim = 384
        
        # Connect to same embedding model if sentence_transformers is available
        self.model = None
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            pass
            
        self._init_table()

    def _init_table(self):
        """Initializes the style memory table schema."""
        schema = pa.schema([
            ("id", pa.string()),
            ("vector", pa.list_(pa.float32(), self.vector_dim)),
            ("description", pa.string()),
            ("before_code", pa.string()),
            ("after_code", pa.string()),
            ("filepath", pa.string())
        ])
        if self.table_name not in self.db.table_names():
            self.table = self.db.create_table(self.table_name, schema=schema)
        else:
            self.table = self.db.open_table(self.table_name)

    def _embed(self, text: str) -> List[float]:
        """Generates embedding vector. Falls back to pseudo-vectors if no model is loaded."""
        if self.model:
            return self.model.encode(text).tolist()
        else:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vector = []
            for i in range(self.vector_dim):
                vector.append(float(h[i % len(h)]) / 128.0 - 1.0)
            return vector

    def add_preference(self, filepath: str, before_code: str, after_code: str, description: str):
        """Adds a before/after style correction to the memory database."""
        text_to_embed = f"{description}\n{before_code}\n{after_code}"
        pref_id = f"{filepath}_{hashlib.md5(text_to_embed.encode('utf-8')).hexdigest()[:8]}"
        
        data = [{
            "id": pref_id,
            "vector": self._embed(text_to_embed),
            "description": description,
            "before_code": before_code,
            "after_code": after_code,
            "filepath": filepath
        }]
        self.table.add(data)
        print(f"[StyleMemory] Recorded user preference for {filepath}: {description}")

    def retrieve_preferences(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieves top style examples matching query."""
        self.table = self.db.open_table(self.table_name)
        if self.table.count_rows() == 0:
            return []
            
        if self.model:
            query_vector = self._embed(query)
            return self.table.search(query_vector).limit(limit).to_list()
        else:
            # Term matching fallback
            arrow_table = self.table.to_arrow()
            ids = arrow_table["id"].to_pylist()
            vectors = arrow_table["vector"].to_pylist()
            descriptions = arrow_table["description"].to_pylist()
            before_codes = arrow_table["before_code"].to_pylist()
            after_codes = arrow_table["after_code"].to_pylist()
            filepaths = arrow_table["filepath"].to_pylist()
            
            words = set(query.lower().split())
            scored = []
            for i in range(len(descriptions)):
                score = sum(1 for w in words if w in descriptions[i].lower() or w in filepaths[i].lower())
                if score > 0:
                    scored.append((score, {
                        "id": ids[i],
                        "vector": vectors[i],
                        "description": descriptions[i],
                        "before_code": before_codes[i],
                        "after_code": after_codes[i],
                        "filepath": filepaths[i]
                    }))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:limit]]

def harvest_user_corrections(workspace_path: str, llm: Optional[Any] = None):
    """
    Scans the git repository for uncommitted files.
    Compares modifications to HEAD to retrieve Before/After states.
    Uses an LLM (if provided) to summarize the adjustment, then registers it.
    """
    style_mem = StyleMemory(workspace_path)
    
    # Get uncommitted modified files
    res = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=workspace_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if res.returncode != 0:
        return
        
    modified_files = [line.strip() for line in res.stdout.split("\n") if line.strip()]
    
    for rel_path in modified_files:
        ext = os.path.splitext(rel_path)[1].lower()
        if ext not in {".py", ".ts", ".js", ".tsx"}:
            continue
            
        full_path = os.path.join(workspace_path, rel_path)
        if not os.path.exists(full_path):
            continue
            
        # Get Before content
        before_res = subprocess.run(
            ["git", "show", f"HEAD:{rel_path}"],
            cwd=workspace_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if before_res.returncode != 0:
            continue
            
        before_code = before_res.stdout
        
        # Get After content
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                after_code = f.read()
        except Exception:
            continue
            
        if before_code.strip() == after_code.strip():
            continue
            
        # Generate description
        description = "User adjusted code formatting or structure"
        if llm:
            try:
                prompt = (
                    "Analyze the following code change made by the user. "
                    "Describe the style, formatting, or architectural correction in exactly one short sentence.\n\n"
                    f"BEFORE:\n{before_code}\n\n"
                    f"AFTER:\n{after_code}"
                )
                resp = llm.invoke(prompt)
                description = resp.content.strip()
            except Exception:
                pass
                
        style_mem.add_preference(rel_path, before_code, after_code, description)
