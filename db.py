"""
Camada de persistência do Segundo Cérebro.
Usa SQLite (um único arquivo local, sem necessidade de servidor) para
guardar as notas do usuário.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).parent / "notas.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Cria a tabela de notas caso ainda não exista. Chamado uma vez no início do app."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            conteudo TEXT NOT NULL,
            tags TEXT DEFAULT '',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def adicionar_nota(titulo: str, conteudo: str, tags: str = "") -> int:
    conn = get_connection()
    agora = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO notas (titulo, conteudo, tags, criado_em, atualizado_em) "
        "VALUES (?, ?, ?, ?, ?)",
        (titulo, conteudo, tags, agora, agora),
    )
    conn.commit()
    nota_id = cur.lastrowid
    conn.close()
    return nota_id


def atualizar_nota(nota_id: int, titulo: str, conteudo: str, tags: str) -> None:
    conn = get_connection()
    agora = datetime.now().isoformat()
    conn.execute(
        "UPDATE notas SET titulo = ?, conteudo = ?, tags = ?, atualizado_em = ? WHERE id = ?",
        (titulo, conteudo, tags, agora, nota_id),
    )
    conn.commit()
    conn.close()


def excluir_nota(nota_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM notas WHERE id = ?", (nota_id,))
    conn.commit()
    conn.close()


def listar_notas() -> List[Dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM notas ORDER BY atualizado_em DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_por_palavra_chave(termo: str) -> List[Dict]:
    """Busca simples por substring no título, conteúdo ou tags. Sempre funciona, sem IA."""
    conn = get_connection()
    termo_like = f"%{termo}%"
    rows = conn.execute(
        "SELECT * FROM notas WHERE titulo LIKE ? OR conteudo LIKE ? OR tags LIKE ? "
        "ORDER BY atualizado_em DESC",
        (termo_like, termo_like, termo_like),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
