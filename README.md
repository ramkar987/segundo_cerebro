# 🧠 Segundo Cérebro V2

Uma reconstrução do conceito de “segundo cérebro” como aplicação web Django, sem Streamlit.

## O que já existe

- captura universal: texto, Instagram, YouTube e página web;
- detecção automática e normalização da origem;
- biblioteca com pesquisa e filtros por tipo/status/favorito;
- item detalhado com retorno à fonte original;
- Instagram preserva legenda, hashtags e metadados separadamente;
- posts e carrosséis de imagens do Instagram podem ter o texto dos slides lido por IA visual;
- transcrição opcional de Instagram/YouTube via Groq Whisper;
- análise automática com IA: essência, diferenças legenda/fala, insights, assunto e tags;
- timestamps da fala armazenados como chunks pesquisáveis;
- fila persistente de processamento no próprio banco, sem exigir Redis/Celery;
- worker separado (`process_jobs`) para não bloquear a página;
- estrutura pronta para tags, assuntos, projetos, chunks e relações;
- tela inicial de conexões;
- SQLite para desenvolvimento e PostgreSQL + pgvector preparado para produção.

## Rodar localmente

Requer Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Em outro terminal:

```bash
python manage.py process_jobs
```

Abra `http://127.0.0.1:8000/`.

Sem `DATABASE_URL`, o Django usa SQLite automaticamente.

## Inicializadores e manutenção

Os scripts utilitários ficam organizados por sistema operacional:

```text
scripts/
├── common/
│   ├── backup_segundo_cerebro.py
│   └── restaurar_segundo_cerebro.py
├── windows/
│   ├── Segundo Cerebro.bat
│   ├── iniciar_segundo_cerebro.ps1
│   ├── Backup Segundo Cerebro.bat
│   ├── backup_segundo_cerebro.ps1
│   ├── Restaurar Segundo Cerebro.bat
│   ├── restaurar_segundo_cerebro.ps1
│   └── instalar_atalhos_desktop.ps1
└── linux/
    ├── iniciar_segundo_cerebro.sh
    ├── backup_segundo_cerebro.sh
    ├── restaurar_segundo_cerebro.sh
    └── instalar_atalhos_desktop.sh
```

### Windows

Para instalar ou atualizar os atalhos da Área de Trabalho:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\instalar_atalhos_desktop.ps1
```

Isso cria:

- `Segundo Cerebro.bat`;
- `Backup Segundo Cerebro.bat`;
- `Restaurar Segundo Cerebro.bat`.

O inicializador abre servidor e worker em duas abas do Windows Terminal quando `wt.exe` estiver disponível e só abre o navegador quando o Django estiver respondendo.

Os atalhos não contêm nome de usuário fixo. Por padrão procuram o projeto em `%USERPROFILE%\segundo_cerebro`. Se o projeto estiver em outro local, defina a variável de ambiente `SEGUNDO_CEREBRO_DIR`.

### Linux / Zorin OS

Crie o ambiente normalmente:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

Depois instale os atalhos da Área de Trabalho:

```bash
chmod +x scripts/linux/*.sh
bash scripts/linux/instalar_atalhos_desktop.sh
```

O inicializador tenta usar `gnome-terminal` com duas abas (site e worker); se não estiver disponível, usa `x-terminal-emulator`. O navegador é aberto com `xdg-open` somente depois que o Django responder.

A restauração usa `zenity` para escolher o ZIP quando disponível; sem `zenity`, solicita o caminho no terminal.

### Backup

Os backups são gravados em:

```text
~/Segundo Cerebro Backups
```

Cada ZIP contém uma cópia consistente do `db.sqlite3`, a pasta `media/` quando existir e um arquivo de orientação. São mantidos os 30 backups mais recentes.

O `.env` não entra no backup porque pode conter chaves de API. Guarde-o separadamente em local seguro.

## Transcrição de Instagram e YouTube

Crie um arquivo `.env` na raiz do projeto:

```env
GROQ_API_KEY=sua-chave-aqui
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
TRANSCRIBE_MEDIA=1
TRANSCRIPTION_LANGUAGE=pt
GROQ_VISION_MODEL=qwen/qwen3.8-27b
GEMINI_API_KEY=sua-chave-do-google-ai-studio
GEMINI_VISION_MODEL=gemini-3.5-flash-lite
ANALYZE_IMAGES=1
GROQ_CHAT_MODEL=openai/gpt-oss-20b
ANALYZE_CONTENT=1
```

Novas capturas de vídeo do Instagram/YouTube serão transcritas automaticamente pelo worker.

Posts e carrosséis de imagens do Instagram usam Instaloader para obter os slides. O OCR visual tenta primeiro a Groq; se houver limite/erro e uma GEMINI_API_KEY estiver configurada, usa automaticamente o Gemini 3.5 Flash-Lite como contingência. Legenda e texto dos slides permanecem separados para a análise.

Para completar mídias que já estavam cadastradas antes da transcrição existir:

```bash
python manage.py transcribe_media
```

Para um item específico:

```bash
python manage.py transcribe_media --item 3
```

Para retranscrever:

```bash
python manage.py transcribe_media --item 3 --force
```

Para analisar com IA os itens já cadastrados:

```bash
python manage.py analyze_content
```

Ou um item específico:

```bash
python manage.py analyze_content --item 3
```

Legenda e transcrição ficam em campos diferentes. Os segmentos da transcrição guardam início e fim em segundos para futuras citações exatas.

A configuração padrão limita o arquivo enviado à transcrição a 24 MB para permanecer abaixo do limite do tier gratuito.

## PostgreSQL + pgvector

Para subir somente o banco local:

```bash
docker compose up -d db
```

No `.env`:

```env
DATABASE_URL=postgresql://segundo:segundo@localhost:5432/segundo_cerebro
```

O container já traz pgvector. Neste estágio os embeddings continuam como JSON para manter compatibilidade com SQLite; a coluna vetorial será ativada no marco de busca semântica.

## Arquitetura

```text
Navegador
   ↓
Django + HTML/HTMX
   ├── Captura universal
   ├── Biblioteca/filtros
   ├── Item
   └── Conexões
        ↓
Banco
   ├── SQLite
   └── PostgreSQL + pgvector
        ↑
Worker process_jobs
   ├── Instagram / YouTube via yt-dlp
   ├── transcrição Groq / Whisper
   └── Web via Requests + BeautifulSoup
```

## Próximos marcos

1. Chunking também de legenda, web e PDF.
3. Embeddings e busca híbrida.
4. RAG com citação de trecho exato.
5. Sugestões automáticas de relações.
6. Grafo interativo.
7. Upload e parsing de PDF.
8. Deploy gratuito/baixo custo.

## Segurança

Não coloque chaves de API no GitHub. O arquivo `.env` está no `.gitignore`.
