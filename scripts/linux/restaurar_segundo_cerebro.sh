#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
RESTORE_SCRIPT="$PROJECT_DIR/scripts/common/restaurar_segundo_cerebro.py"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERRO: ambiente virtual nao encontrado em: $PYTHON"
    read -r -p "Pressione Enter para sair"
    exit 1
fi

BACKUP_ZIP=""
if command -v zenity >/dev/null 2>&1; then
    BACKUP_ZIP="$(zenity --file-selection --title="Escolha o backup do Segundo Cerebro" --file-filter="Backup ZIP | *.zip" || true)"
else
    read -r -p "Caminho completo do arquivo ZIP: " BACKUP_ZIP
fi

[[ -n "$BACKUP_ZIP" ]] || exit 0

echo
echo "IMPORTANTE: feche o servidor e o worker antes de restaurar."
read -r -p "Digite SIM para continuar: " confirm
if [[ "$confirm" != "SIM" ]]; then
    echo "Restauracao cancelada."
    exit 0
fi

"$PYTHON" "$RESTORE_SCRIPT" "$BACKUP_ZIP"
"$PYTHON" manage.py migrate --noinput

echo
echo "Restauracao concluida. Agora voce pode abrir o Segundo Cerebro."
read -r -p "Pressione Enter para fechar"
