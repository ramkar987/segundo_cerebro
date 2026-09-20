from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "db.sqlite3"
MEDIA_DIR = PROJECT_DIR / "media"
BACKUP_DIR = Path.home() / "Segundo Cerebro Backups"
KEEP = 30


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERRO: banco nao encontrado: {DB_PATH}")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_base = BACKUP_DIR / f"Segundo_Cerebro_Backup_{stamp}"

    with tempfile.TemporaryDirectory(prefix="segundo_cerebro_backup_") as temp_dir:
        temp = Path(temp_dir)
        snapshot = temp / "db.sqlite3"

        print("Criando copia segura do banco...")
        source = sqlite3.connect(DB_PATH)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

        if MEDIA_DIR.exists() and any(MEDIA_DIR.iterdir()):
            print("Copiando arquivos de media...")
            shutil.copytree(MEDIA_DIR, temp / "media")

        readme = temp / "LEIA-ME.txt"
        readme.write_text(
            "Backup do Segundo Cerebro\n"
            f"Criado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
            "Conteudo:\n"
            "- db.sqlite3: itens, transcricoes, analises, tags, relacoes etc.\n"
            "- media/: arquivos locais, quando existirem.\n\n"
            "O arquivo .env NAO e incluido porque contem credenciais/chaves.\n"
            "Guarde uma copia separada e segura do .env se quiser migrar para outro PC.\n",
            encoding="utf-8",
        )

        print("Compactando backup...")
        zip_path = Path(shutil.make_archive(str(zip_base), "zip", temp))

    backups = sorted(
        BACKUP_DIR.glob("Segundo_Cerebro_Backup_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[KEEP:]:
        try:
            old.unlink()
        except OSError:
            pass

    print()
    print("BACKUP CONCLUIDO")
    print(f"Arquivo: {zip_path}")
    print(f"Backups mantidos: ate {KEEP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
