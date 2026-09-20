#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
BACKUP_SCRIPT="$PROJECT_DIR/scripts/common/backup_segundo_cerebro.py"
BACKUP_DIR="$HOME/Segundo Cerebro Backups"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERRO: ambiente virtual nao encontrado em: $PYTHON"
    read -r -p "Pressione Enter para sair"
    exit 1
fi

"$PYTHON" "$BACKUP_SCRIPT"

if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$BACKUP_DIR" >/dev/null 2>&1 &
fi

echo
read -r -p "Backup concluido. Pressione Enter para fechar"
