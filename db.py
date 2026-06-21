"""
Camada de persistência do Segundo Cérebro.
Usa SQLite (um único arquivo local, sem necessidade de servidor) para
guardar as notas do usuário — tanto notas manuais quanto notas geradas
a partir de vídeos importados e transcritos.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

DB_PATH = Path(__file__).parent / "notas.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Cria a tabela de notas e aplica migrações simples (novas colunas)."""
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

    # Migração: notas de vídeo precisam de colunas extras. Como o banco já
    # pode existir de uma versão anterior do app, adicionamos as colunas só
    # se ainda não existirem — assim ninguém perde notas já salvas.
    colunas_existentes = {row["name"] for row in conn.execute("PRAGMA table_info(notas)")}
    novas_colunas = {
        "tipo": "TEXT DEFAULT 'manual'",
        "fonte_url": "TEXT DEFAULT ''",
        "transcricao_completa": "TEXT DEFAULT ''",
    }
    for nome, definicao in novas_colunas.items():
        if nome not in colunas_existentes:
            conn.execute(f"ALTER TABLE notas ADD COLUMN {nome} {definicao}")

    conn.commit()
    conn.close()


def adicionar_nota(titulo: str, conteudo: str, tags: str = "") -> int:
    """Cria uma nota manual (escrita pelo usuário)."""
    conn = get_connection()
    agora = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO notas (titulo, conteudo, tags, criado_em, atualizado_em, tipo) "
        "VALUES (?, ?, ?, ?, ?, 'manual')",
        (titulo, conteudo, tags, agora, agora),
    )
    conn.commit()
    nota_id = cur.lastrowid
    conn.close()
    return nota_id


def adicionar_nota_video(
    titulo: str,
    conteudo: str,
    tags: str,
    fonte_url: str,
    transcricao_completa: str,
) -> int:
    """Cria uma nota a partir de um vídeo importado e transcrito."""
    conn = get_connection()
    agora = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO notas "
        "(titulo, conteudo, tags, criado_em, atualizado_em, tipo, fonte_url, transcricao_completa) "
        "VALUES (?, ?, ?, ?, ?, 'video', ?, ?)",
        (titulo, conteudo, tags, agora, agora, fonte_url, transcricao_completa),
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
    """Busca simples por substring no título, conteúdo, tags ou transcrição. Sem IA."""
    conn = get_connection()
    termo_like = f"%{termo}%"
    rows = conn.execute(
        "SELECT * FROM notas WHERE titulo LIKE ? OR conteudo LIKE ? OR tags LIKE ? "
        "OR transcricao_completa LIKE ? ORDER BY atualizado_em DESC",
        (termo_like, termo_like, termo_like, termo_like),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def exportar_notas() -> str:
    """Gera um backup em JSON de todas as notas (para baixar e guardar fora do app)."""
    notas = listar_notas()
    notas_export = [
        {
            "titulo": n["titulo"],
            "conteudo": n["conteudo"],
            "tags": n["tags"],
            "criado_em": n["criado_em"],
            "atualizado_em": n["atualizado_em"],
            "tipo": n.get("tipo", "manual"),
            "fonte_url": n.get("fonte_url", ""),
            "transcricao_completa": n.get("transcricao_completa", ""),
        }
        for n in notas
    ]
    return json.dumps({"versao": 1, "notas": notas_export}, ensure_ascii=False, indent=2)


def importar_notas(conteudo_json: str) -> Tuple[int, int]:
    """Importa notas de um backup JSON gerado por exportar_notas().

    Evita duplicar notas que já existem (mesmo título + mesma data de
    criação). Retorna (quantidade_importada, quantidade_ignorada)."""
    dados = json.loads(conteudo_json)
    notas_para_importar = dados.get("notas", []) if isinstance(dados, dict) else dados

    existentes = {(n["titulo"], n["criado_em"]) for n in listar_notas()}

    conn = get_connection()
    importadas = 0
    ignoradas = 0
    for nota in notas_para_importar:
        chave = (nota.get("titulo", ""), nota.get("criado_em", ""))
        if chave in existentes:
            ignoradas += 1
            continue

        agora = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO notas "
            "(titulo, conteudo, tags, criado_em, atualizado_em, tipo, fonte_url, transcricao_completa) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                nota.get("titulo", "Sem título"),
                nota.get("conteudo", ""),
                nota.get("tags", ""),
                nota.get("criado_em") or agora,
                nota.get("atualizado_em") or agora,
                nota.get("tipo", "manual"),
                nota.get("fonte_url", ""),
                nota.get("transcricao_completa", ""),
            ),
        )
        importadas += 1
        existentes.add(chave)

    conn.commit()
    conn.close()
    return importadas, ignoradas
