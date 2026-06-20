cat > src/storage.py << 'EOF'
"""DuckDB storage"""
from pathlib import Path
from typing import List, Dict
import duckdb
from config.settings import settings

class SegundoCerebroStorage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or settings.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))
    
    def initialize_schema(self):
        schema_path = Path(__file__).parent.parent / "sql" / "schema_duckdb.sql"
        with open(schema_path, "r") as f:
            self.conn.execute(f.read())
    
    def insert_video(self, titulo: str, caminho: str, transricao: str, 
                     resumo: str = None, tags: str = None, traducao: str = None) -> int:
        self.conn.execute("""
            INSERT INTO videos (titulo, caminho, transricao, resumo, tags, traducao,
                              data_transricao, data_processamento_ia)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, [titulo, caminho, transricao, resumo, tags, traducao])
        
        return self.conn.execute(
            "SELECT id FROM videos WHERE titulo = ? ORDER BY id DESC LIMIT 1", [titulo]
        ).fetchone()[0]
    
    def search_videos(self, search_text: str, limit: int = 50) -> List[Dict]:
        result = self.conn.execute("""
            SELECT id, titulo, resumo, tags, traducao, data_cadastro
            FROM videos
            WHERE transricao LIKE ? OR titulo LIKE ? OR resumo LIKE ? OR tags LIKE ?
            ORDER BY data_cadastro DESC LIMIT ?
        """, [search_text, search_text, search_text, search_text, limit]).fetchall()
        
        return [{"id": r[0], "titulo": r[1], "resumo": r[2], "tags": r[3], 
                 "traducao": r[4], "data_cadastro": r[5]} for r in result]
    
    def get_all_videos(self, limit: int = 100) -> List[Dict]:
        result = self.conn.execute("""
            SELECT id, titulo, resumo, tags, data_cadastro
            FROM videos ORDER BY data_cadastro DESC LIMIT ?
        """, [limit]).fetchall()
        
        return [{"id": r[0], "titulo": r[1], "resumo": r[2], "tags": r[3], "data_cadastro": r[4]} for r in result]
    
    def close(self):
        self.conn.close()
EOF
