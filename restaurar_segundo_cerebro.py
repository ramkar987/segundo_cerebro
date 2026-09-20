from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "db.sqlite3"
MEDIA_DIR = PROJECT_DIR / "media"


def validate_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA schema_version").fetchone()
    finally:
        con.close()


def main() -> int:
    if len(sys.argv) < 2:
        print("ERRO: informe o arquivo ZIP do backup.")
        return 1

    backup_zip = Path(sys.argv[1]).expanduser().resolve()
    if not backup_zip.exists():
        print(f"ERRO: backup nao encontrado: {backup_zip}")
        return 1

    with tempfile.TemporaryDirectory(prefix="segundo_cerebro_restore_") as temp_dir:
        temp = Path(temp_dir)

        try:
            with zipfile.ZipFile(backup_zip, "r") as zf:
                names = set(zf.namelist())
                if "db.sqlite3" not in names:
                    print("ERRO: este ZIP nao contem db.sqlite3.")
                    return 1
                zf.extractall(temp)
        except zipfile.BadZipFile:
            print("ERRO: arquivo ZIP invalido.")
            return 1

        restored_db = temp / "db.sqlite3"
        try:
            validate_db(restored_db)
        except sqlite3.DatabaseError as exc:
            print(f"ERRO: db.sqlite3 do backup parece invalido: {exc}")
            return 1

        if DB_PATH.exists():
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safety = PROJECT_DIR / f"db_antes_da_restauracao_{stamp}.sqlite3"
            print(f"Guardando banco atual em: {safety.name}")
            shutil.copy2(DB_PATH, safety)

        print("Restaurando banco...")
        shutil.copy2(restored_db, DB_PATH)

        restored_media = temp / "media"
        if restored_media.exists():
            print("Restaurando pasta media...")
            if MEDIA_DIR.exists():
                shutil.rmtree(MEDIA_DIR)
            shutil.copytree(restored_media, MEDIA_DIR)

    print()
    print("RESTAURACAO CONCLUIDA")
    print(f"Backup usado: {backup_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
