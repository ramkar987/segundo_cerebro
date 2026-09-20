#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP)"
else
    DESKTOP_DIR="$HOME/Desktop"
fi

mkdir -p "$DESKTOP_DIR"
chmod +x "$SCRIPT_DIR"/*.sh

create_launcher() {
    local name="$1"
    local script="$2"
    local file="$DESKTOP_DIR/$name.desktop"

    cat > "$file" <<EOF
[Desktop Entry]
Type=Application
Name=$name
Comment=Segundo Cerebro
Exec=bash "$SCRIPT_DIR/$script"
Terminal=true
Icon=applications-internet
Categories=Utility;
EOF
    chmod +x "$file"
    gio set "$file" metadata::trusted true >/dev/null 2>&1 || true
    echo "Criado: $file"
}

create_launcher "Segundo Cerebro" "iniciar_segundo_cerebro.sh"
create_launcher "Backup Segundo Cerebro" "backup_segundo_cerebro.sh"
create_launcher "Restaurar Segundo Cerebro" "restaurar_segundo_cerebro.sh"

echo
echo "Atalhos instalados na Area de Trabalho."
echo "Se o Zorin pedir confirmacao, escolha 'Permitir iniciar'."
