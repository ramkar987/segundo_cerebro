#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
URL="http://127.0.0.1:8000/"

cd "$PROJECT_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "ERRO: ambiente virtual nao encontrado em:"
    echo "  $PYTHON"
    echo
    echo "Crie o ambiente com:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    read -r -p "Pressione Enter para sair"
    exit 1
fi

echo "Segundo Cerebro"
echo "Projeto: $PROJECT_DIR"
echo
echo "Aplicando migrations pendentes..."
"$PYTHON" manage.py migrate --noinput

site_cmd="cd $(printf '%q' "$PROJECT_DIR"); $(printf '%q' "$PYTHON") manage.py runserver; exec bash"
worker_cmd="cd $(printf '%q' "$PROJECT_DIR"); $(printf '%q' "$PYTHON") manage.py process_jobs; exec bash"

if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal         --tab --title="Segundo Cerebro - Site" -- bash -lc "$site_cmd"         --tab --title="Segundo Cerebro - Worker" -- bash -lc "$worker_cmd"
elif command -v x-terminal-emulator >/dev/null 2>&1; then
    x-terminal-emulator -T "Segundo Cerebro - Site" -e bash -lc "$site_cmd" &
    x-terminal-emulator -T "Segundo Cerebro - Worker" -e bash -lc "$worker_cmd" &
else
    echo "ERRO: nenhum terminal grafico compativel encontrado."
    exit 1
fi

echo "Aguardando o servidor ficar pronto..."
ready=0
for _ in {1..40}; do
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('$URL', timeout=1).read(1)" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 0.5
done

if [[ "$ready" -eq 1 ]]; then
    echo "Servidor pronto. Abrindo $URL"
    xdg-open "$URL" >/dev/null 2>&1 &
else
    echo "O servidor ainda nao respondeu. Verifique a aba 'Segundo Cerebro - Site'."
fi
