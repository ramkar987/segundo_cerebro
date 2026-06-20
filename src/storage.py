from pathlib import Path
from typing import List, Dict, Optional
import duckdb

class SegundoCerebroStorage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or "./data/segundo_cerebro.duckdb")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(self.db_path))

    def initialize_schema(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            titulo TEXT NOT NULL,
            caminho TEXT NOT NULL,
            transricao TEXT,
            resumo TEXT,
            tags TEXT,
            traducao TEXT,
            idioma_original TEXT,
            idioma_traducao TEXT,
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_transricao TIMESTAMP,
            data_processamento_ia TIMESTAMP
        )
        """)

    def insert_video(self, titulo: str, caminho: str, transricao: str,
                     resumo: Optional[str] = None, tags: Optional[str] = None,
                     traducao: Optional[str] = None,
                     idioma_original: Optional[str] = None,
                     idioma_traducao: Optional[str] = None) -> int:
        self.conn.execute("""
            INSERT INTO videos (
                titulo, caminho, transricao, resumo, tags, traducao,
                idioma_original, idioma_traducao, data_transricao, data_processamento_ia
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, [titulo, caminho, transricao, resumo, tags, traducao, idioma_original, idioma_traducao])

        return self.conn.execute("SELECT MAX(id) FROM videos").fetchone()[0]

    def search_videos(self, search_text: str, limit: int = 50) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT id, titulo, caminho, resumo, tags, traducao, data_cadastro
            FROM videos
            WHERE transricao ILIKE ? OR titulo ILIKE ? OR resumo ILIKE ? OR tags ILIKE ?
            ORDER BY data_cadastro DESC
            LIMIT ?
        """, [f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", limit]).fetchall()

        return [
            {
                "id": r[0], "titulo": r[1], "caminho": r[2], "resumo": r[3],
                "tags": r[4], "traducao": r[5], "data_cadastro": r[6]
            }
            for r in rows
        ]

    def get_all_videos(self, limit: int = 100) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT id, titulo, caminho, resumo, tags, traducao, data_cadastro
            FROM videos
            ORDER BY data_cadastro DESC
            LIMIT ?
        """, [limit]).fetchall()

        return [
            {
                "id": r[0], "titulo": r[1], "caminho": r[2], "resumo": r[3],
                "tags": r[4], "traducao": r[5], "data_cadastro": r[6]
            }
            for r in rows
        ]

    def close(self):
        self.conn.close()
